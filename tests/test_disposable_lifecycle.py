"""Disposable Hermes Installation and Security Lifecycle Verification (Stage 2C)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

airhermes_dir = Path(__file__).resolve().parent.parent
fork_src = Path(os.environ.get("HERMES_AGENT_PATH", airhermes_dir.parent / "hermes-agent-fork"))
temp_hermes = tempfile.mkdtemp(prefix="hermes_stage2c_lifecycle_")
os.chdir(str(airhermes_dir))

try:
    print("=== STEP 0: Preparing disposable Hermes tree ===")
    for item in ["gateway", "plugins", "tests"]:
        s = os.path.join(fork_src, item)
        d = os.path.join(temp_hermes, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)

    before_hashes = {}
    for rel in [
        "gateway/run_turn.py",
        "gateway/run_turn_runner.py",
        "gateway/session.py",
        "plugins/platforms/photon/adapter.py",
        "gateway/bubble_queue.py",
    ]:
        fp = os.path.join(temp_hermes, rel)
        with open(fp, "rb") as f:
            before_hashes[rel] = f.read()

    print("=== STEP 1: Install ===")
    p1 = subprocess.run([sys.executable, "install.py", "--target", temp_hermes], capture_output=True, text=True)
    print("Install rc:", p1.returncode)
    assert p1.returncode == 0, p1.stderr

    print("=== STEP 2: Verify ===")
    p2 = subprocess.run([sys.executable, "install.py", "--target", temp_hermes, "--verify"], capture_output=True, text=True)
    print("Verify rc:", p2.returncode)
    assert p2.returncode == 0, p2.stderr

    print("=== STEP 3: Doctor ===")
    p3 = subprocess.run([sys.executable, "install.py", "--target", temp_hermes, "--doctor"], capture_output=True, text=True)
    print("Doctor rc:", p3.returncode)
    assert p3.returncode == 0, p3.stderr

    print("=== STEP 4: Exercise registered attachments with mocked Sidecar in installed tree ===")
    test_script = os.path.join(temp_hermes, "exercise_attachment.py")
    with open(test_script, "w", encoding="utf-8") as f:
        f.write(f'''
import sys, os, asyncio
from gateway.attachment_registry import registry
from plugins.platforms.photon.adapter import PhotonAdapter, SendResult

adapter = object.__new__(PhotonAdapter)
dispatched = []
async def mock_send(space_id, path, **kwargs):
    dispatched.append((space_id, path, kwargs))
    return SendResult(success=True)

adapter._sidecar_send_attachment = mock_send

# 1. Unregistered file -> REJECTED
victim = r"{temp_hermes}/gateway/run_turn.py"
res_unreg = asyncio.run(adapter.send_document("chat_test", victim))
assert not res_unreg.success, "Unregistered call must fail"
assert len(dispatched) == 0, "Must not dispatch unregistered file"

# 2. Registered file -> DISPATCHED
rec, err = registry.stage_and_authorize("chat_test", victim, producer="test_disposable")
assert rec is not None and not err
res_reg = asyncio.run(adapter.send_document("chat_test", rec.staged_path))
assert res_reg.success, "Registered call must succeed"
assert len(dispatched) == 1, "Must dispatch registered file"
print("SUCCESS: Installed tree correctly rejected un-staged and accepted staged attachment!")
''')

    p4 = subprocess.run([sys.executable, test_script], cwd=temp_hermes, capture_output=True, text=True)
    print("Exercise rc:", p4.returncode)
    print("Exercise output:", p4.stdout.strip())
    if p4.returncode != 0:
        print("Exercise stderr:", p4.stderr)
    assert p4.returncode == 0

    print("=== STEP 5: Uninstall ===")
    p5 = subprocess.run([sys.executable, "install.py", "--target", temp_hermes, "--uninstall"], capture_output=True, text=True)
    print("Uninstall rc:", p5.returncode)
    assert p5.returncode == 0, p5.stderr

    print("=== STEP 6: Confirm original files are restored ===")
    for rel, orig_bytes in before_hashes.items():
        fp = os.path.join(temp_hermes, rel)
        with open(fp, "rb") as f:
            curr_bytes = f.read()
        assert curr_bytes == orig_bytes, f"File mismatch after uninstall: {rel}"

    # Pre-existing files in fork (e.g. bubble_queue.py) should be restored to their pre-install content
    if "gateway/bubble_queue.py" in before_hashes:
        with open(os.path.join(temp_hermes, "gateway/bubble_queue.py"), "rb") as f:
            assert f.read() == before_hashes["gateway/bubble_queue.py"]

    # Newly created files that did not exist before AirHermes installation must be completely removed
    for rel in [
        "gateway/airhermes_config.py",
        "gateway/attachment_registry.py",
        "gateway/bubble_actions.py",
    ]:
        assert not os.path.exists(os.path.join(temp_hermes, rel)), f"File not removed: {rel}"
    print("Original files 100% matched byte-for-byte, all newly deployed AirHermes modules removed!")

    print("=== STEP 7: Exercise failed-install rollback ===")
    with open(os.path.join(temp_hermes, "gateway/run_turn.py"), "w", encoding="utf-8") as f:
        f.write("corrupted content to force patch failure")

    p7 = subprocess.run([sys.executable, "install.py", "--target", temp_hermes], capture_output=True, text=True)
    print("Failed-install rc:", p7.returncode)
    assert p7.returncode != 0, "Installation must abort when patch validation fails"
    assert "validation failed" in (p7.stderr + p7.stdout).lower(), "Preflight failure message missing"
    print("Rollback/preflight abort succeeded cleanly!")

    print("=== ALL 7 LIFECYCLE STEPS PASSED SUCCESSFULLY! ===")
finally:
    shutil.rmtree(temp_hermes, ignore_errors=True)
