"""Isolated Security Audit Reproduction Scenarios (Phase 5 Stage 2B).

Tests the 10 scenarios requested by the security review:
1. Untrusted MEDIA reference with streaming enabled
2. Untrusted MEDIA reference with streaming disabled
3. Untrusted MEDIA / bare path passed through direct attachment methods
4. Cross-chat staged path replay
5. Cross-Turn staged path replay
6. Direct authorized attachment delivery
7. Internal calendar and contact attachments
8. Generated image and card delivery
9. Concurrent duplicate redemption
10. Cancellation and unknown delivery status
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Tuple

cur_dir = Path(__file__).resolve().parent.parent
fork_root = Path("d:/Gemini Works/hermes-agent-fork")
sys.path.insert(0, str(fork_root))
sys.path.insert(0, str(cur_dir))

import gateway

if hasattr(gateway, "__path__") and str(cur_dir / "gateway") not in gateway.__path__:
    gateway.__path__.insert(0, str(cur_dir / "gateway"))

import plugins
import plugins.platforms
import plugins.platforms.photon

photon_pkg = str(fork_root / "plugins" / "platforms" / "photon")
if photon_pkg not in plugins.platforms.photon.__path__:
    plugins.platforms.photon.__path__.append(photon_pkg)

spec = importlib.util.spec_from_file_location(
    "plugins.platforms.photon.adapter", str(cur_dir / "plugins" / "platforms" / "photon" / "adapter.py")
)
mod = importlib.util.module_from_spec(spec)
sys.modules["plugins.platforms.photon.adapter"] = mod
spec.loader.exec_module(mod)
PhotonAdapter = mod.PhotonAdapter
SendResult = mod.SendResult

from gateway.airhermes_config import AirHermesConfig
from gateway.attachment_registry import registry
from gateway.bubble_actions import FileAttachmentAction, ImageAttachmentAction
from gateway.bubble_parser import BubbleParser
from gateway.bubble_stream_consumer import BubbleStreamConsumer


class AuditHarness:
    def __init__(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="airhermes_audit_scenarios_")
        self.dispatched: list[tuple[str, str, dict[str, Any]]] = []

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_file(self, name: str, content: str = "CONFIDENTIAL HOST DATA") -> str:
        p = os.path.join(self.temp_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def build_adapter(self, streaming: bool = True) -> Any:
        adapter = object.__new__(PhotonAdapter)
        adapter.airhermes_config = AirHermesConfig(bubble_streaming=streaming)
        self.dispatched = []

        async def mock_sidecar_send_attachment(space_id: str, path: str, **kwargs: Any) -> SendResult:
            self.dispatched.append((space_id, path, kwargs))
            return SendResult(success=True)

        async def mock_sidecar_send(space_id: str, text: str, **kwargs: Any) -> SendResult:
            return SendResult(success=True)

        adapter._sidecar_send_attachment = mock_sidecar_send_attachment
        adapter._sidecar_send = mock_sidecar_send
        return adapter


def test_scenario_01_untrusted_media_streaming() -> Tuple[bool, str]:
    """1. Untrusted MEDIA reference with streaming enabled."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter(streaming=True)
        victim = h.make_file("secret1.txt")
        response = f"Analysis complete. See data: MEDIA:{victim}"

        # Upstream streamed final media delivery calls adapter.extract_media()
        extracted, cleaned = adapter.extract_media(response)

        async def deliver():
            for p, _ in extracted:
                await adapter.send_document("victim_chat", p)

        asyncio.run(deliver())
        if len(h.dispatched) == 0 and victim in cleaned:
            return True, "Protected: Untrusted MEDIA tag ignored, not extracted, 0 dispatches"
        return False, f"VULNERABLE: Dispatched {h.dispatched}"
    finally:
        h.cleanup()


def test_scenario_02_untrusted_media_non_streaming() -> Tuple[bool, str]:
    """2. Untrusted MEDIA reference with streaming disabled."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter(streaming=False)
        victim = h.make_file("secret2.txt")
        response = f"Non-streamed summary: MEDIA:{victim}"

        extracted, cleaned = adapter.extract_media(response)

        async def deliver():
            for p, _ in extracted:
                await adapter.send_document("victim_chat", p)

        asyncio.run(deliver())
        if len(h.dispatched) == 0 and victim in cleaned:
            return True, "Protected: Untrusted MEDIA tag ignored, not extracted, 0 dispatches"
        return False, f"VULNERABLE: Dispatched {h.dispatched}"
    finally:
        h.cleanup()


def test_scenario_03_untrusted_direct_attachment_calls() -> Tuple[bool, str]:
    """3. Untrusted MEDIA / bare path passed through direct attachment methods."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        victim = h.make_file("secret3_passwords.txt", "passwords=123456")

        # Caller (e.g. tool, upstream extract_local_files, or direct call) calls send_document
        async def direct():
            await adapter.send_document("victim_chat", victim, file_name="notes.txt")

        asyncio.run(direct())
        if len(h.dispatched) > 0:
            staged_p = h.dispatched[0][1]
            return False, f"VULNERABLE BYPASS: send_document automatically staged and dispatched host file: {staged_p}"
        return True, "Protected: Direct call with unregistered file was rejected"
    finally:
        h.cleanup()


def test_scenario_04_cross_chat_replay() -> Tuple[bool, str]:
    """4. Cross-chat staged path replay."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        alice_file = h.make_file("alice_private.txt", "Alice sensitive notes")
        # Alice legitimately stages a file in chat_alice
        record, _ = registry.stage_and_authorize("chat_alice", alice_file, producer="calendar_generator")
        staged_p = record.staged_path

        # Bob in chat_bob calls send_document with Alice's staged path
        async def attack():
            await adapter.send_document("chat_bob", staged_p)

        asyncio.run(attack())
        # Check if chat_bob received Alice's file
        bob_dispatches = [d for d in h.dispatched if d[0] == "chat_bob"]
        if bob_dispatches:
            return False, f"VULNERABLE BYPASS: Bob in chat_bob redeemed Alice's staged attachment: {bob_dispatches}"
        return True, "Protected: Cross-chat redemption rejected"
    finally:
        h.cleanup()


def test_scenario_05_cross_turn_replay() -> Tuple[bool, str]:
    """5. Cross-Turn staged path replay."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        sample = h.make_file("turn1_file.txt", "Turn 1 ephemeral data")
        record, _ = registry.stage_and_authorize("chat_charlie", sample, producer="test", turn_id="turn_1")
        staged_p = record.staged_path

        # Next turn calls send_document with turn_id="turn_2"
        async def turn2_send():
            await adapter.send_document("chat_charlie", staged_p, metadata={"turn_id": "turn_2"})

        asyncio.run(turn2_send())
        if len(h.dispatched) > 0:
            return False, f"VULNERABLE BYPASS: Attachment bound to turn_1 was re-staged and sent in turn_2: {h.dispatched}"
        return True, "Protected: Cross-turn replay rejected"
    finally:
        h.cleanup()


def test_scenario_06_direct_authorized_delivery() -> Tuple[bool, str]:
    """6. Direct authorized attachment delivery."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        sample = h.make_file("legit.txt", "Legitimate content")
        record, _ = registry.stage_and_authorize("chat_auth", sample, producer="calendar_generator", turn_id="t1")

        async def deliver():
            return await adapter.send_document("chat_auth", record.staged_path, metadata={"turn_id": "t1"})

        res = asyncio.run(deliver())
        if res.success and len(h.dispatched) == 1 and h.dispatched[0][0] == "chat_auth":
            return True, "Working: Authorized attachment correctly verified and dispatched"
        return False, f"Failed: Delivery failed {res.error}"
    finally:
        h.cleanup()


def test_scenario_07_internal_calendar_contact() -> Tuple[bool, str]:
    """7. Internal calendar and contact attachments."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        parser = BubbleParser(paragraph_fallback=False, chat_id="chat_cal", turn_id="t_cal")
        actions = parser.feed_actions('<calendar title="Team Sync" start="2026-11-25 10:00" end="2026-11-25 11:00" location="Room 1"/>') + parser.finish_actions()

        if not (actions and isinstance(actions[0], FileAttachmentAction)):
            return False, f"Failed: Parser did not emit FileAttachmentAction: {actions}"

        consumer = BubbleStreamConsumer(adapter, "chat_cal", metadata={"turn_id": "t_cal"})

        async def send():
            await consumer._send_bubble(actions[0])

        asyncio.run(send())
        if len(h.dispatched) == 1 and h.dispatched[0][0] == "chat_cal":
            return True, "Working: Calendar generator staged and sent .ics via typed FileAttachmentAction"
        return False, f"Failed: Dispatch failed {h.dispatched}"
    finally:
        h.cleanup()


def test_scenario_08_generated_image_card() -> Tuple[bool, str]:
    """8. Generated image and card delivery."""
    h = AuditHarness()
    dummy_png = h.make_file("chart_test.png", "\x89PNG\r\n\x1a\n" + "\x00" * 1024)
    try:
        adapter = h.build_adapter()
        record, err = registry.stage_and_authorize(
            chat_id="chat_img",
            source_path=dummy_png,
            producer="chart_generator",
            turn_id="t_img",
        )
        if not record or err:
            return False, f"Failed: Could not stage and authorize image: {err}"

        action = ImageAttachmentAction(
            staged_path=record.staged_path,
            token=record.token,
            caption="Sample Chart",
        )

        consumer = BubbleStreamConsumer(adapter, "chat_img", metadata={"turn_id": "t_img"})

        async def send():
            await consumer._send_bubble(action)

        asyncio.run(send())
        if len(h.dispatched) == 1 and h.dispatched[0][0] == "chat_img":
            return True, "Working: Staged and sent .png via typed ImageAttachmentAction"
        return False, f"Failed: Dispatch failed {h.dispatched}"
    finally:
        h.cleanup()


def test_scenario_09_concurrent_duplicate_redemption() -> Tuple[bool, str]:
    """9. Concurrent duplicate redemption."""
    h = AuditHarness()
    try:
        adapter = h.build_adapter()
        sample = h.make_file("concurrent.txt", "Single-use payload")
        record, _ = registry.stage_and_authorize("chat_conc", sample, producer="test", turn_id="t_conc")

        # Launch two concurrent sends of the same staged attachment
        async def concurrent_run():
            return await asyncio.gather(
                adapter.send_document("chat_conc", record.staged_path, metadata={"turn_id": "t_conc"}),
                adapter.send_document("chat_conc", record.staged_path, metadata={"turn_id": "t_conc"}),
                return_exceptions=True,
            )

        _ = asyncio.run(concurrent_run())
        # Inspect how many reached the sidecar
        if len(h.dispatched) > 1:
            return False, f"VULNERABLE: Both concurrent requests reached sidecar (dispatched={len(h.dispatched)})"
        return True, f"Protected: Only 1 reached sidecar (dispatched={len(h.dispatched)})"
    finally:
        h.cleanup()


def test_scenario_10_cancellation_unknown_status() -> Tuple[bool, str]:
    """10. Cancellation and unknown delivery status."""
    h = AuditHarness()
    try:
        adapter = object.__new__(PhotonAdapter)
        adapter.airhermes_config = AirHermesConfig()
        sample = h.make_file("cancel_test.txt", "Cancel data")
        record, _ = registry.stage_and_authorize("chat_cancel", sample, producer="test", turn_id="t_cancel")

        # Mock sidecar hanging until cancelled
        async def hanging_sidecar(*a, **k):
            await asyncio.sleep(10.0)
            return SendResult(success=True)

        adapter._sidecar_send_attachment = hanging_sidecar

        async def run_cancel():
            task = asyncio.create_task(
                adapter.send_document("chat_cancel", record.staged_path, metadata={"turn_id": "t_cancel"})
            )
            await asyncio.sleep(0.02)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run_cancel())

        # Inspect lifecycle state
        # Does record.in_flight remain True?
        in_flight = record.in_flight
        # Run cleanup_turn
        registry.cleanup_turn("chat_cancel", "t_cancel")
        file_remains = os.path.isfile(record.staged_path)

        if in_flight and file_remains:
            return False, f"DEFECT CONFIRMED: Cancellation left record.in_flight=True; file leaked on disk ({record.staged_path})"
        return True, "Protected: Cancellation handled and state recovered"
    finally:
        h.cleanup()


if __name__ == "__main__":
    scenarios = [
        ("Scenario 1: Untrusted MEDIA Streaming", test_scenario_01_untrusted_media_streaming),
        ("Scenario 2: Untrusted MEDIA Non-Streaming", test_scenario_02_untrusted_media_non_streaming),
        ("Scenario 3: Untrusted Direct Attachment Call", test_scenario_03_untrusted_direct_attachment_calls),
        ("Scenario 4: Cross-Chat Staged Path Replay", test_scenario_04_cross_chat_replay),
        ("Scenario 5: Cross-Turn Staged Path Replay", test_scenario_05_cross_turn_replay),
        ("Scenario 6: Direct Authorized Attachment Delivery", test_scenario_06_direct_authorized_delivery),
        ("Scenario 7: Internal Calendar/Contact Attachments", test_scenario_07_internal_calendar_contact),
        ("Scenario 8: Generated Image/Card Delivery", test_scenario_08_generated_image_card),
        ("Scenario 9: Concurrent Duplicate Redemption", test_scenario_09_concurrent_duplicate_redemption),
        ("Scenario 10: Cancellation & Lifecycle Leak", test_scenario_10_cancellation_unknown_status),
    ]

    print("=" * 70)
    print("AIRHERMES PHASE 5 STAGE 2B — 10 SCENARIO SECURITY AUDIT MATRIX")
    print("=" * 70)
    passes = 0
    failures = 0
    for name, func in scenarios:
        ok, msg = func()
        status = "[ PASS ]" if ok else "[ FAIL / BYPASS ]"
        if ok:
            passes += 1
        else:
            failures += 1
        print(f"{status:18} | {name}")
        print(f"                   | Detail: {msg}")
        print("-" * 70)

    print(f"\nAudit Summary: {passes} Passed, {failures} Failed/Bypassed out of {len(scenarios)} Scenarios")
