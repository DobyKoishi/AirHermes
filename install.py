#!/usr/bin/env python3
"""AirHermes - Automated Installer & Patch Manager.

Injects discrete multi-bubble streaming and native iOS ecosystem parity into Hermes Agent.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def find_default_hermes() -> Path | None:
    candidates = [
        Path.cwd(),
        Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent",
        Path.home() / ".local" / "hermes" / "hermes-agent",
        Path.home() / "hermes-agent",
    ]
    for c in candidates:
        if c.exists() and (c / "gateway" / "run_turn.py").exists():
            return c
    return None


def backup_file(src: Path, backup_dir: Path) -> None:
    if src.exists():
        rel = src.relative_to(src.anchor) if src.is_absolute() else src
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src, dest)


def apply_patch(target_dir: Path, patch_file: Path) -> bool:
    try:
        res = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=target_dir, capture_output=True, text=True,
        )
        if res.returncode == 0:
            subprocess.run(["git", "apply", str(patch_file)], cwd=target_dir, check=True)
            return True
    except Exception:
        pass
    return False


def install(target_dir: Path) -> bool:
    print(f"[*] Installing AirHermes into: {target_dir}")
    if not (target_dir / "gateway" / "run_turn.py").exists():
        print(f"[!] Error: {target_dir} does not appear to be a valid hermes-agent root.")
        return False

    backup_dir = target_dir / ".deluxe_backup"
    backup_dir.mkdir(exist_ok=True)

    # 1. Backup key files
    for f in [
        target_dir / "gateway" / "run_turn.py",
        target_dir / "gateway" / "run_turn_runner.py",
        target_dir / "gateway" / "session.py",
        target_dir / "plugins" / "platforms" / "photon" / "adapter.py",
        target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "index.mjs",
        target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "package.json",
    ]:
        if f.exists():
            backup_file(f, backup_dir)

    # 2. Copy standalone gateway & plugin files
    print("[*] Copying discrete streaming & iOS modules...")
    shutil.copy2(ROOT / "gateway" / "bubble_parser.py", target_dir / "gateway" / "bubble_parser.py")
    shutil.copy2(ROOT / "gateway" / "bubble_queue.py", target_dir / "gateway" / "bubble_queue.py")
    shutil.copy2(ROOT / "gateway" / "bubble_stream_consumer.py", target_dir / "gateway" / "bubble_stream_consumer.py")

    shutil.copy2(ROOT / "plugins" / "platforms" / "photon" / "adapter.py", target_dir / "plugins" / "platforms" / "photon" / "adapter.py")
    shutil.copy2(ROOT / "plugins" / "platforms" / "photon" / "sidecar" / "index.mjs", target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "index.mjs")
    shutil.copy2(ROOT / "plugins" / "platforms" / "photon" / "sidecar" / "package.json", target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "package.json")
    shutil.copy2(ROOT / "plugins" / "platforms" / "photon" / "sidecar" / "patch-spectrum-poll.mjs", target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "patch-spectrum-poll.mjs")

    # Copy tests
    test_target = target_dir / "tests" / "gateway"
    test_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests" / "test_photon_bubble_streaming.py", test_target / "test_photon_bubble_streaming.py")

    # 3. Apply patches to core gateway files
    print("[*] Patching gateway integration hooks...")
    patches = [
        ROOT / "patches" / "run_turn.patch",
        ROOT / "patches" / "run_turn_runner.patch",
        ROOT / "patches" / "session.patch",
    ]
    all_patched = True
    for p in patches:
        if p.exists():
            if not apply_patch(target_dir, p):
                print(f"[!] Warning: git apply failed for {p.name}. You may need manual review.")
                all_patched = False

    # 4. Patch sidecar if node_modules installed
    poll_patcher = target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "patch-spectrum-poll.mjs"
    sidecar_dir = target_dir / "plugins" / "platforms" / "photon" / "sidecar"
    if (sidecar_dir / "node_modules").exists() and poll_patcher.exists():
        print("[*] Applying spectrum-ts poll patch...")
        subprocess.run(["node", "patch-spectrum-poll.mjs"], cwd=sidecar_dir)

    print("\n[+] AirHermes installed successfully!")
    print("[*] Note: If you haven't linked iMessage yet, run 'hermes photon setup'.")
    print("[*] Launch your bot anytime with: hermes gateway")
    return all_patched


def verify(target_dir: Path) -> bool:
    print(f"[*] Running test suite in: {target_dir}")
    res = subprocess.run(
        [sys.executable, "-m", "unittest", "tests/gateway/test_photon_bubble_streaming.py"],
        cwd=target_dir,
    )
    return res.returncode == 0


def uninstall(target_dir: Path) -> bool:
    print(f"[*] Uninstalling AirHermes from: {target_dir}")
    backup_dir = target_dir / ".deluxe_backup"
    if not backup_dir.exists():
        print(f"[!] No backup directory found at {backup_dir}. Cannot auto-restore.")
        return False

    # Restore backed up files
    for root, _, files in os.walk(backup_dir):
        for f in files:
            full_src = Path(root) / f
            rel = full_src.relative_to(backup_dir)
            dest = Path(target_dir.anchor) / rel if target_dir.anchor else target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full_src, dest)
            print(f"    Restored {rel}")

    # Remove added standalone files
    added = [
        target_dir / "gateway" / "bubble_parser.py",
        target_dir / "gateway" / "bubble_queue.py",
        target_dir / "gateway" / "bubble_stream_consumer.py",
        target_dir / "plugins" / "platforms" / "photon" / "sidecar" / "patch-spectrum-poll.mjs",
        target_dir / "tests" / "gateway" / "test_photon_bubble_streaming.py",
    ]
    for a in added:
        if a.exists():
            a.unlink()
            print(f"    Removed {a.name}")

    shutil.rmtree(backup_dir, ignore_errors=True)
    print("\n[+] Uninstalled and reverted to pre-Deluxe state.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="AirHermes Installer")
    parser.add_argument("--target", "-t", type=Path, default=None, help="Path to hermes-agent root directory")
    parser.add_argument("--verify", action="store_true", help="Run tests to verify installation")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall Deluxe and restore backups")

    args = parser.parse_args()
    target = args.target or find_default_hermes()
    if not target or not target.exists():
        print("[!] Could not auto-detect hermes-agent directory. Please pass --target /path/to/hermes-agent")
        sys.exit(1)

    if args.uninstall:
        success = uninstall(target)
    elif args.verify:
        success = verify(target)
    else:
        success = install(target)
        if success:
            verify(target)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
