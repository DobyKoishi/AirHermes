#!/usr/bin/env python3
"""AirHermes - Transactional Installer, Diagnostic & Lifecycle Manager.

Injects discrete multi-bubble streaming and native iOS ecosystem parity
into Hermes Agent with ACID-like transactional guarantees, persistent
journaling, staged preflight validation, and safe uninstallation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AIRHERMES_VERSION = "0.1.0"
MANIFEST_DIR = ".airhermes"
MANIFEST_FILE = "manifest.json"
BACKUP_DIR = "backup"
LEGACY_BACKUP_DIR = ".deluxe_backup"

ROOT = Path(__file__).resolve().parent


# -----------------------------------------------------------------------------
# Utility & Integrity Helpers
# -----------------------------------------------------------------------------

def compute_sha256(path: Path) -> str:
    """Compute hex SHA-256 hash of a file."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def find_default_hermes() -> Path | None:
    """Auto-detect local Hermes Agent installation path."""
    candidates = [
        Path.cwd(),
        Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "hermes-agent",
        Path.home() / ".local" / "hermes" / "hermes-agent",
        Path.home() / "hermes-agent",
        Path.home() / "hermes",
    ]
    for c in candidates:
        if c.is_dir() and (c / "gateway" / "run_turn.py").is_file():
            return c.resolve()
    return None


def atomic_copy(src: Path, dst: Path) -> None:
    """Atomically copy file to destination via temporary file and replace."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(f".{dst.name}.tmp_{int(time.time() * 1000)}")
    try:
        shutil.copy2(src, tmp_dst)
        os.replace(tmp_dst, dst)
    except Exception:
        if tmp_dst.exists():
            try:
                tmp_dst.unlink()
            except OSError:
                pass
        raise


def clean_stale_temps(directory: Path) -> None:
    """Clean up any leftover temporary files matching .*.tmp*."""
    try:
        for p in directory.rglob(".*.tmp*"):
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
    except Exception:
        pass


def resolve_safe_relpath(path: Path, base: Path) -> Path:
    """Resolve path relative to base and verify it does not escape base."""
    resolved_base = base.resolve()
    resolved_path = path.resolve() if path.is_absolute() else (base / path).resolve()
    try:
        rel = resolved_path.relative_to(resolved_base)
    except ValueError as e:
        raise ValueError(f"Security error: path {path} escapes base directory {base}") from e
    return rel


# -----------------------------------------------------------------------------
# Manifest & Transaction Journal
# -----------------------------------------------------------------------------

@dataclass
class FileModificationRecord:
    pre_sha256: str
    post_sha256: str
    backup_relpath: str


@dataclass
class InstallationManifest:
    version: str = AIRHERMES_VERSION
    installed_at: float = field(default_factory=time.time)
    state: str = "in_progress"  # "in_progress", "committed", "rolled_back"
    step: str = "init"          # "init", "staged", "backed_up", "copied", "patched", "committed"
    modified_files: Dict[str, Dict[str, str]] = field(default_factory=dict)
    created_files: List[str] = field(default_factory=list)
    hermes_root: str = ""

    def save(self, target_dir: Path) -> None:
        manifest_path = target_dir / MANIFEST_DIR / MANIFEST_FILE
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        tmp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, manifest_path)

    @classmethod
    def load(cls, target_dir: Path) -> Optional[InstallationManifest]:
        manifest_path = target_dir / MANIFEST_DIR / MANIFEST_FILE
        if not manifest_path.is_file():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return cls(
                version=data.get("version", AIRHERMES_VERSION),
                installed_at=data.get("installed_at", 0.0),
                state=data.get("state", "unknown"),
                step=data.get("step", "unknown"),
                modified_files=data.get("modified_files", {}),
                created_files=data.get("created_files", []),
                hermes_root=data.get("hermes_root", ""),
            )
        except Exception:
            return None

    @classmethod
    def has_corrupted_manifest(cls, target_dir: Path) -> bool:
        """Check if manifest file exists but is corrupted or unparseable."""
        manifest_path = target_dir / MANIFEST_DIR / MANIFEST_FILE
        if not manifest_path.is_file():
            return False
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return not isinstance(data, dict)
        except Exception:
            return True


# -----------------------------------------------------------------------------
# Preflight & Staged Validation
# -----------------------------------------------------------------------------

class PreflightValidator:
    """Preflight checks and sandbox staging verification."""

    REQUIRED_TARGET_FILES = [
        Path("gateway/run_turn.py"),
        Path("plugins/platforms/photon/adapter.py"),
    ]

    STANDALONE_COPIES: List[Tuple[Path, Path]] = [
        (Path("gateway/airhermes_config.py"), Path("gateway/airhermes_config.py")),
        (Path("gateway/attachment_registry.py"), Path("gateway/attachment_registry.py")),
        (Path("gateway/bubble_actions.py"), Path("gateway/bubble_actions.py")),
        (Path("gateway/bubble_parser.py"), Path("gateway/bubble_parser.py")),
        (Path("gateway/bubble_queue.py"), Path("gateway/bubble_queue.py")),
        (Path("gateway/bubble_stream_consumer.py"), Path("gateway/bubble_stream_consumer.py")),
        (Path("plugins/platforms/photon/adapter.py"), Path("plugins/platforms/photon/adapter.py")),
        (Path("plugins/platforms/photon/sidecar/index.mjs"), Path("plugins/platforms/photon/sidecar/index.mjs")),
        (Path("plugins/platforms/photon/sidecar/package.json"), Path("plugins/platforms/photon/sidecar/package.json")),
        (Path("plugins/platforms/photon/sidecar/package-lock.json"), Path("plugins/platforms/photon/sidecar/package-lock.json")),
        (Path("plugins/platforms/photon/sidecar/patch-spectrum-poll.mjs"), Path("plugins/platforms/photon/sidecar/patch-spectrum-poll.mjs")),
        (Path("plugins/platforms/photon/sidecar/patch-spectrum-mixed-attachments.mjs"), Path("plugins/platforms/photon/sidecar/patch-spectrum-mixed-attachments.mjs")),
        (Path("plugins/platforms/photon/sidecar/send-format.mjs"), Path("plugins/platforms/photon/sidecar/send-format.mjs")),
        (Path("plugins/platforms/photon/sidecar/stream-staleness.mjs"), Path("plugins/platforms/photon/sidecar/stream-staleness.mjs")),
        (Path("plugins/platforms/photon/sidecar/.npmrc"), Path("plugins/platforms/photon/sidecar/.npmrc")),
        (Path("plugins/platforms/photon/sidecar/README.md"), Path("plugins/platforms/photon/sidecar/README.md")),
        (Path("tests/test_photon_bubble_streaming.py"), Path("tests/gateway/test_photon_bubble_streaming.py")),
    ]

    PATCH_FILES: List[Tuple[Path, Path]] = [
        (Path("patches/run_turn.patch"), Path("gateway/run_turn.py")),
        (Path("patches/run_turn_runner.patch"), Path("gateway/run_turn_runner.py")),
        (Path("patches/session.patch"), Path("gateway/session.py")),
    ]

    @classmethod
    def check_git_executable(cls) -> Optional[str]:
        return shutil.which("git")

    @classmethod
    def validate_target_structure(cls, target_dir: Path) -> List[str]:
        errors = []
        if not target_dir.is_dir():
            return [f"Target path does not exist or is not a directory: {target_dir}"]
        for req in cls.REQUIRED_TARGET_FILES:
            if not (target_dir / req).is_file():
                errors.append(f"Required Hermes core file missing: {req}")
        if not os.access(target_dir, os.W_OK):
            errors.append(f"Target directory is not writable: {target_dir}")
        return errors

    @classmethod
    def stage_and_validate(cls, target_dir: Path, source_root: Path) -> Tuple[bool, List[str]]:
        """Validate complete planned installation inside an isolated staging directory.

        Simulates file copies and patch application in sandbox to ensure zero
        partial-mutation risk on the real target directory.
        """
        errors = []
        git_bin = cls.check_git_executable()
        if not git_bin:
            errors.append("Git executable not found in PATH. 'git' is required to apply patches.")
            return False, errors

        # Pre-check target patch states to detect partially patched environment
        applied_count = 0
        unapplied_count = 0
        for patch_rel, target_rel in cls.PATCH_FILES:
            patch_file = source_root / patch_rel
            if not patch_file.is_file():
                continue
            target_file = target_dir / target_rel
            if not target_file.is_file():
                continue

            chk = subprocess.run(
                [git_bin, "apply", "--ignore-whitespace", "--check", str(patch_file)],
                cwd=target_dir, capture_output=True, text=True,
            )
            if chk.returncode == 0:
                unapplied_count += 1
            else:
                rev = subprocess.run(
                    [git_bin, "apply", "--ignore-whitespace", "--reverse", "--check", str(patch_file)],
                    cwd=target_dir, capture_output=True, text=True,
                )
                if rev.returncode == 0:
                    applied_count += 1

        if applied_count > 0 and unapplied_count > 0:
            errors.append(
                f"Partially patched environment detected ({applied_count} applied, {unapplied_count} unapplied). "
                "Cannot safely establish pre-installation backups. Revert existing patches or restore clean Hermes files."
            )
            return False, errors

        # Create isolated temporary staging sandbox
        with tempfile.TemporaryDirectory(prefix="airhermes_stage_") as stage_tmp:
            stage_dir = Path(stage_tmp)

            # 1. Mirror target's key files that will be read or patched
            files_to_mirror = [
                Path("gateway/run_turn.py"),
                Path("gateway/run_turn_runner.py"),
                Path("gateway/session.py"),
                Path("plugins/platforms/photon/adapter.py"),
                Path("plugins/platforms/photon/sidecar/index.mjs"),
                Path("plugins/platforms/photon/sidecar/package.json"),
            ]
            for f in files_to_mirror:
                src_file = target_dir / f
                if src_file.is_file():
                    dst_file = stage_dir / f
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

            # 2. Copy planned standalone modules into staging
            for src_rel, dst_rel in cls.STANDALONE_COPIES:
                src_file = source_root / src_rel
                if not src_file.is_file():
                    errors.append(f"AirHermes source package missing required file: {src_rel}")
                    continue
                dst_file = stage_dir / dst_rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)

            if errors:
                return False, errors

            # 3. Apply patches sequentially in staging
            for patch_rel, target_rel in cls.PATCH_FILES:
                patch_file = source_root / patch_rel
                if not patch_file.is_file():
                    continue

                # Run git apply --check in staging
                res_check = subprocess.run(
                    [git_bin, "apply", "--ignore-whitespace", "--check", str(patch_file)],
                    cwd=stage_dir, capture_output=True, text=True,
                )
                if res_check.returncode != 0:
                    # Check if patch is already applied in target
                    res_rev = subprocess.run(
                        [git_bin, "apply", "--ignore-whitespace", "--reverse", "--check", str(patch_file)],
                        cwd=stage_dir, capture_output=True, text=True,
                    )
                    if res_rev.returncode == 0:
                        # Patch is already applied, safe to continue
                        continue

                    err_msg = res_check.stderr.strip() or res_check.stdout.strip()
                    errors.append(
                        f"Patch validation failed for {patch_rel.name} on {target_rel}: {err_msg}"
                    )
                    continue

                # Apply patch to staging to allow subsequent dependent patches to validate
                res_apply = subprocess.run(
                    [git_bin, "apply", "--ignore-whitespace", str(patch_file)],
                    cwd=stage_dir, capture_output=True, text=True,
                )
                if res_apply.returncode != 0:
                    errors.append(f"Failed applying staged patch {patch_rel.name}: {res_apply.stderr.strip()}")

            if errors:
                return False, errors

            # 4. Verify syntax compilation of staged Python files
            for py_path in stage_dir.rglob("*.py"):
                try:
                    py_compile.compile(str(py_path), doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"Staged file failed syntax check: {py_path.name}: {e}")

        return (len(errors) == 0), errors


# -----------------------------------------------------------------------------
# Transactional Installer Engine
# -----------------------------------------------------------------------------

class TransactionalInstaller:
    """Executes safe, atomic, recoverable installation and uninstallation."""

    def __init__(self, target_dir: Path, source_root: Path):
        self.target_dir = target_dir.resolve()
        self.source_root = source_root.resolve()
        self.manifest_dir = self.target_dir / MANIFEST_DIR
        self.backup_dir = self.manifest_dir / BACKUP_DIR
        self.manifest = InstallationManifest(hermes_root=str(self.target_dir))
        self.git_bin = PreflightValidator.check_git_executable() or "git"

    def detect_interrupted_transaction(self) -> Optional[InstallationManifest]:
        """Detect if an earlier installation crashed or terminated mid-flight."""
        existing = InstallationManifest.load(self.target_dir)
        if existing and existing.state == "in_progress":
            return existing
        return None

    def rollback(self, manifest: Optional[InstallationManifest] = None) -> bool:
        """Roll back all changes recorded in manifest to restore original state."""
        print("[*] Initiating rollback to restore original state...")
        m = manifest or self.manifest or InstallationManifest.load(self.target_dir)
        if not m:
            print("[!] No manifest available for rollback.")
            return False

        # Mark rollback in-progress
        m.step = "rolling_back"
        try:
            m.save(self.target_dir)
        except Exception:
            pass

        success = True
        # 1. Restore modified files from backup
        for rel_str, record in m.modified_files.items():
            try:
                safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                target_file = self.target_dir / safe_rel
                backup_rel = record.get("backup_relpath")
                if not backup_rel:
                    continue
                safe_backup_rel = resolve_safe_relpath(Path(backup_rel), self.target_dir)
                backup_file = self.target_dir / safe_backup_rel
                if backup_file.is_file():
                    atomic_copy(backup_file, target_file)
                    print(f"    [Rollback] Restored {safe_rel}")
            except Exception as e:
                print(f"    [!] Failed restoring {rel_str}: {e}")
                success = False

        # 2. Delete created standalone files
        for rel_str in m.created_files:
            try:
                safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                target_file = self.target_dir / safe_rel
                if target_file.is_file():
                    target_file.unlink()
                    print(f"    [Rollback] Removed created file {safe_rel}")
            except Exception as e:
                print(f"    [!] Failed removing {rel_str}: {e}")
                success = False

        # Clean leftover temporary files
        clean_stale_temps(self.target_dir)

        # 3. Clean up manifest only if rollback succeeded 100%
        if success:
            try:
                m.state = "rolled_back"
                m.step = "rolled_back"
                m.save(self.target_dir)
                if self.manifest_dir.exists():
                    shutil.rmtree(self.manifest_dir, ignore_errors=True)
                print("[+] Rollback completed.")
            except Exception as e:
                print(f"[!] Error cleaning manifest directory: {e}")
                success = False
        else:
            print("[!] Rollback incomplete due to errors. Manifest and backups preserved for manual recovery.")
            try:
                m.step = "rollback_failed"
                m.save(self.target_dir)
            except Exception:
                pass

        return success

    def install(self, dry_run: bool = False) -> bool:
        """Execute transactional installation with preflight validation."""
        print(f"[*] Target Hermes root: {self.target_dir}")

        # Check for corrupted manifest
        if InstallationManifest.has_corrupted_manifest(self.target_dir):
            print("[!] Error: An existing manifest file was found at .airhermes/manifest.json, but it is corrupted.")
            print("[!] Installation aborted to prevent data loss or overwriting unrecoverable backups.")
            print("[*] Please inspect .airhermes/ or pass --uninstall --force if you wish to reset.")
            return False

        # 0. Check for interrupted transaction from previous crash
        interrupted = self.detect_interrupted_transaction()
        if interrupted:
            print(f"[!] Warning: An interrupted installation was detected (step: {interrupted.step}).")
            print("[*] Automatically recovering prior state before proceeding...")
            self.rollback(interrupted)

        # 1. Structural preflight check
        struct_errors = PreflightValidator.validate_target_structure(self.target_dir)
        if struct_errors:
            print("[!] Preflight structure validation failed:")
            for err in struct_errors:
                print(f"    - {err}")
            return False

        # 2. Staged sandbox validation (checks files, git apply, compilation)
        print("[*] Running staged sandbox validation...")
        stage_ok, stage_errors = PreflightValidator.stage_and_validate(self.target_dir, self.source_root)
        if not stage_ok:
            print("[!] Staged preflight validation failed. No target files were modified:")
            for err in stage_errors:
                print(f"    - {err}")
            return False
        print("[+] Staged sandbox validation passed.")

        # If dry run, print plan and exit cleanly without mutations
        if dry_run:
            print("\n[--dry-run] Planned operations (Simulation only):")
            print("  Files to backup:")
            for patch_rel, target_rel in PreflightValidator.PATCH_FILES:
                if (self.target_dir / target_rel).is_file():
                    print(f"    - {target_rel}")
            print("  Files to copy/overwrite:")
            for src_rel, dst_rel in PreflightValidator.STANDALONE_COPIES:
                print(f"    - {dst_rel} (from {src_rel})")
            print("  Patches to apply:")
            for patch_rel, target_rel in PreflightValidator.PATCH_FILES:
                print(f"    - {patch_rel.name} -> {target_rel}")
            print("\n[+] Dry run successful: File structure, patch applicability, and Python syntax checks passed.")
            print("[*] Note: Dry run validates file and patch compatibility. Run '--doctor' or test in your environment to verify runtime packages and gateway execution.")
            return True

        # Existing committed manifest if any (e.g. repeated install / update)
        existing_manifest = InstallationManifest.load(self.target_dir)

        # 3. Begin Transaction
        self.manifest.state = "in_progress"
        self.manifest.step = "init"
        self.manifest.save(self.target_dir)

        try:
            # 3.1 Backup files that will be modified
            self.manifest.step = "backing_up"
            self.manifest.save(self.target_dir)
            files_to_backup: List[Path] = []
            for _, target_rel in PreflightValidator.PATCH_FILES:
                p = self.target_dir / target_rel
                if p.is_file():
                    files_to_backup.append(target_rel)
            for _, dst_rel in PreflightValidator.STANDALONE_COPIES:
                p = self.target_dir / dst_rel
                if p.is_file():
                    files_to_backup.append(dst_rel)

            for rel in set(files_to_backup):
                src_path = self.target_dir / rel
                rel_str = str(rel).replace("\\", "/")
                backup_rel = Path(MANIFEST_DIR) / BACKUP_DIR / rel
                backup_dst = self.target_dir / backup_rel

                # Preserve existing clean backup if already committed in a prior install
                if backup_dst.is_file() and existing_manifest and rel_str in existing_manifest.modified_files:
                    orig_pre_sha = existing_manifest.modified_files[rel_str].get("pre_sha256", compute_sha256(backup_dst))
                    self.manifest.modified_files[rel_str] = {
                        "pre_sha256": orig_pre_sha,
                        "post_sha256": "",
                        "backup_relpath": str(backup_rel).replace("\\", "/"),
                    }
                else:
                    pre_hash = compute_sha256(src_path)
                    backup_dst.parent.mkdir(parents=True, exist_ok=True)
                    atomic_copy(src_path, backup_dst)
                    self.manifest.modified_files[rel_str] = {
                        "pre_sha256": pre_hash,
                        "post_sha256": "",
                        "backup_relpath": str(backup_rel).replace("\\", "/"),
                    }
                # Flush journal after each backup
                self.manifest.save(self.target_dir)

            # 3.2 Copy standalone modules
            self.manifest.step = "copying"
            self.manifest.save(self.target_dir)
            for src_rel, dst_rel in PreflightValidator.STANDALONE_COPIES:
                src_file = self.source_root / src_rel
                dst_file = self.target_dir / dst_rel
                is_new = not dst_file.is_file()
                rel_str = str(dst_rel).replace("\\", "/")

                # Write-Ahead Logging: record intent before mutating target
                if is_new and rel_str not in self.manifest.created_files:
                    self.manifest.created_files.append(rel_str)
                    self.manifest.save(self.target_dir)

                atomic_copy(src_file, dst_file)

                if rel_str in self.manifest.modified_files:
                    self.manifest.modified_files[rel_str]["post_sha256"] = compute_sha256(dst_file)
                    self.manifest.save(self.target_dir)

            # 3.3 Apply patches
            self.manifest.step = "patching"
            self.manifest.save(self.target_dir)
            for patch_rel, target_rel in PreflightValidator.PATCH_FILES:
                patch_file = self.source_root / patch_rel
                if not patch_file.is_file():
                    continue
                # Check if patch is already applied in target
                res_check = subprocess.run(
                    [self.git_bin, "apply", "--ignore-whitespace", "--check", str(patch_file)],
                    cwd=self.target_dir, capture_output=True, text=True,
                )
                if res_check.returncode != 0:
                    res_rev = subprocess.run(
                        [self.git_bin, "apply", "--ignore-whitespace", "--reverse", "--check", str(patch_file)],
                        cwd=self.target_dir, capture_output=True, text=True,
                    )
                    if res_rev.returncode == 0:
                        # Already applied, record post-hash and skip
                        rel_str = str(target_rel).replace("\\", "/")
                        patched_file = self.target_dir / target_rel
                        if rel_str in self.manifest.modified_files:
                            self.manifest.modified_files[rel_str]["post_sha256"] = compute_sha256(patched_file)
                            self.manifest.save(self.target_dir)
                        continue

                res = subprocess.run(
                    [self.git_bin, "apply", "--ignore-whitespace", str(patch_file)],
                    cwd=self.target_dir, capture_output=True, text=True,
                )
                if res.returncode != 0:
                    raise RuntimeError(f"git apply failed on {patch_rel.name}: {res.stderr.strip()}")

                rel_str = str(target_rel).replace("\\", "/")
                patched_file = self.target_dir / target_rel
                if rel_str in self.manifest.modified_files:
                    self.manifest.modified_files[rel_str]["post_sha256"] = compute_sha256(patched_file)
                    self.manifest.save(self.target_dir)

            # 3.4 Patch sidecar node_modules if present
            poll_patcher = self.target_dir / "plugins/platforms/photon/sidecar/patch-spectrum-poll.mjs"
            sidecar_dir = self.target_dir / "plugins/platforms/photon/sidecar"
            if (sidecar_dir / "node_modules").is_dir() and poll_patcher.is_file():
                node_bin = shutil.which("node")
                if node_bin:
                    print("[*] Applying spectrum-ts poll patch to sidecar...")
                    subprocess.run([node_bin, "patch-spectrum-poll.mjs"], cwd=sidecar_dir, capture_output=True)

            # 3.5 Commit transaction
            self.manifest.state = "committed"
            self.manifest.step = "committed"
            self.manifest.save(self.target_dir)
            print("\n[+] AirHermes installed successfully!")
            print("[*] Note: If you haven't linked iMessage yet, run 'hermes photon setup'.")
            print("[*] Launch your bot anytime with: hermes gateway")
            return True

        except Exception as e:
            print(f"\n[!] Installation failed with error: {e}")
            self.rollback()
            return False

    def uninstall(self, force: bool = False) -> bool:
        """Safely uninstall AirHermes and restore original files."""
        print(f"[*] Uninstalling AirHermes from: {self.target_dir}")

        if InstallationManifest.has_corrupted_manifest(self.target_dir):
            print("[!] Error: Installation manifest is corrupted. Cannot safely determine files to restore/remove.")
            if not force:
                print("[*] Aborting uninstallation to protect files. Pass --force to attempt cleanup.")
                return False

        manifest = InstallationManifest.load(self.target_dir)
        legacy_backup = self.target_dir / LEGACY_BACKUP_DIR

        if not manifest and not legacy_backup.is_dir():
            print(f"[!] No installation manifest or backup found at {self.target_dir}. Nothing to uninstall.")
            return False

        success = True

        # Mode A: Modern Manifest-based uninstallation
        if manifest:
            # 1. Conflict detection on user-modified files
            conflicts = []
            for rel_str, record in manifest.modified_files.items():
                try:
                    safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                    target_file = self.target_dir / safe_rel
                except ValueError:
                    continue
                if not target_file.is_file():
                    continue
                current_hash = compute_sha256(target_file)
                post_hash = record.get("post_sha256")
                pre_hash = record.get("pre_sha256")
                if post_hash and current_hash != post_hash and current_hash != pre_hash:
                    conflicts.append((rel_str, target_file))

            if conflicts and not force:
                print("[!] Conflict detected: The following files were modified by user after AirHermes installation:")
                for rel_str, _ in conflicts:
                    print(f"    - {rel_str}")
                print("[*] Uninstallation aborted to protect your modifications. Pass --force to backup and overwrite user modifications.")
                return False

            # If force is enabled, backup user's modified conflicting files before restoring
            if conflicts and force:
                conflict_bak_dir = self.target_dir / ".airhermes_user_conflict_bak"
                conflict_bak_dir.mkdir(parents=True, exist_ok=True)
                print(f"[*] Backing up user-modified conflicting files to {conflict_bak_dir}...")
                for rel_str, target_file in conflicts:
                    try:
                        safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                        dest_bak = conflict_bak_dir / safe_rel
                        dest_bak.parent.mkdir(parents=True, exist_ok=True)
                        if dest_bak.exists():
                            timestamp = int(time.time() * 1000)
                            dest_bak = dest_bak.with_name(f"{dest_bak.stem}.bak_{timestamp}{dest_bak.suffix}")
                        atomic_copy(target_file, dest_bak)
                    except Exception as e:
                        print(f"[!] Failed to backup conflicting file {rel_str}: {e}")
                        print("[!] Aborting uninstallation to protect user modifications.")
                        return False

            # 2. Restore modified files
            for rel_str, record in manifest.modified_files.items():
                try:
                    safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                    target_file = self.target_dir / safe_rel
                    backup_rel = record.get("backup_relpath")
                    if not backup_rel:
                        continue
                    safe_backup_rel = resolve_safe_relpath(Path(backup_rel), self.target_dir)
                    backup_file = self.target_dir / safe_backup_rel
                    if backup_file.is_file():
                        atomic_copy(backup_file, target_file)
                        print(f"    Restored {safe_rel}")
                except ValueError as e:
                    print(f"    [!] Skipping unsafe path in manifest: {rel_str} ({e})")
                    continue
                except Exception as e:
                    print(f"    [!] Error restoring {rel_str}: {e}")
                    success = False

            # 3. Remove created standalone files
            for rel_str in manifest.created_files:
                try:
                    safe_rel = resolve_safe_relpath(Path(rel_str), self.target_dir)
                    target_file = self.target_dir / safe_rel
                    if target_file.is_file():
                        target_file.unlink()
                        print(f"    Removed {safe_rel}")
                except ValueError as e:
                    print(f"    [!] Skipping unsafe path in manifest: {rel_str} ({e})")
                    continue
                except Exception as e:
                    print(f"    [!] Error removing {rel_str}: {e}")
                    success = False

            clean_stale_temps(self.target_dir)

            if success:
                shutil.rmtree(self.manifest_dir, ignore_errors=True)
            else:
                print("[!] Uninstallation encountered errors. Manifest and backups preserved.")

        # Mode B: Fallback for legacy .deluxe_backup
        elif legacy_backup.is_dir():
            print("[*] Found legacy backup directory (.deluxe_backup), performing legacy restore...")
            for root, _, files in os.walk(legacy_backup):
                for f in files:
                    full_src = Path(root) / f
                    rel_to_bak = full_src.relative_to(legacy_backup)
                    clean_parts = [p for p in rel_to_bak.parts if p not in (":", "\\", "/")]
                    while clean_parts and (":" in clean_parts[0] or clean_parts[0] in ("home", "Users", "var", "tmp")):
                        if any(clean_parts[0].startswith(k) for k in ("gateway", "plugins", "tests")):
                            break
                        clean_parts.pop(0)

                    rel_path = Path(*clean_parts) if clean_parts else rel_to_bak
                    try:
                        safe_rel = resolve_safe_relpath(rel_path, self.target_dir)
                        dest = self.target_dir / safe_rel
                        atomic_copy(full_src, dest)
                        print(f"    Restored legacy {safe_rel}")
                    except Exception as e:
                        print(f"    [!] Failed legacy restore for {rel_path}: {e}")
                        success = False

            if success:
                # Remove known added files
                known_added = [
                    self.target_dir / "gateway/bubble_parser.py",
                    self.target_dir / "gateway/bubble_queue.py",
                    self.target_dir / "gateway/bubble_stream_consumer.py",
                    self.target_dir / "plugins/platforms/photon/sidecar/patch-spectrum-poll.mjs",
                    self.target_dir / "tests/gateway/test_photon_bubble_streaming.py",
                ]
                for a in known_added:
                    if a.is_file():
                        try:
                            a.unlink()
                            print(f"    Removed {a.name}")
                        except Exception:
                            pass
                clean_stale_temps(self.target_dir)
                shutil.rmtree(legacy_backup, ignore_errors=True)
            else:
                print("[!] Legacy restore encountered errors. Preserving .deluxe_backup.")

        print("\n[+] Uninstalled and reverted to pre-AirHermes state." if success else "\n[!] Uninstallation failed or incomplete.")
        return success


# -----------------------------------------------------------------------------
# Diagnostics (--doctor) & Verification (--verify)
# -----------------------------------------------------------------------------

def doctor(target_dir: Path) -> int:
    """Run comprehensive environment diagnostics and health checks."""
    print("=" * 60)
    print(" AirHermes Health & Diagnostics Report")
    print("=" * 60)
    print(f"Target Directory: {target_dir}")

    has_errors = False

    # 1. Target Directory & Hermes Core
    if not target_dir.is_dir():
        print("  [x] Target directory does not exist.")
        return 1
    run_turn = target_dir / "gateway/run_turn.py"
    adapter = target_dir / "plugins/platforms/photon/adapter.py"
    if run_turn.is_file() and adapter.is_file():
        print("  [✓] Hermes Agent core structure: OK")
    else:
        print("  [x] Hermes Agent core structure: MISSING required files")
        has_errors = True

    # 2. Git & Node toolchains
    git_bin = PreflightValidator.check_git_executable()
    if git_bin:
        print(f"  [✓] Git executable: {git_bin}")
    else:
        print("  [x] Git executable: NOT FOUND (Required for patch validation)")
        has_errors = True

    node_bin = shutil.which("node")
    if node_bin:
        print(f"  [✓] Node.js executable: {node_bin}")
    else:
        print("  [!] Node.js executable: Not in PATH (Optional, needed for iMessage sidecar)")

    # 3. AirHermes Installation Status
    manifest = InstallationManifest.load(target_dir)
    legacy_backup = target_dir / LEGACY_BACKUP_DIR
    if InstallationManifest.has_corrupted_manifest(target_dir):
        print("  [x] AirHermes Installation: Manifest file (.airhermes/manifest.json) is CORRUPTED.")
        has_errors = True
    elif manifest:
        print(f"  [✓] AirHermes Installation: Installed (v{manifest.version})")
        print(f"      Status: {manifest.state} (Step: {manifest.step})")
        # Verify file integrity
        corruptions = []
        for rel_str, record in manifest.modified_files.items():
            f_path = target_dir / Path(rel_str)
            if not f_path.is_file():
                corruptions.append(f"Missing file: {rel_str}")
                continue
            post_hash = record.get("post_sha256")
            if post_hash and compute_sha256(f_path) != post_hash:
                corruptions.append(f"Hash mismatch (user modified): {rel_str}")
        if corruptions:
            print("      Integrity issues found:")
            for c in corruptions:
                print(f"      - {c}")
        else:
            print("      File Integrity: 100% Match with Manifest")
    elif legacy_backup.is_dir():
        print("  [!] AirHermes Installation: Legacy installation (.deluxe_backup detected)")
    else:
        print("  [-] AirHermes Installation: Not installed")

    # 4. Target Python Environment
    python_bin, venv_type = find_target_python(target_dir)
    print(f"  [✓] Target Python runtime: {python_bin} ({venv_type})")

    print("=" * 60)
    if has_errors:
        print("Result: Issues detected. Please resolve errors before running.")
        return 1
    print("Result: All essential preflight checks passed.")
    return 0


def find_target_python(target_dir: Path) -> Tuple[str, str]:
    """Find appropriate Python executable for target environment."""
    for cand, label in [
        (target_dir / ".venv/Scripts/python.exe", "local .venv"),
        (target_dir / ".venv/bin/python", "local .venv"),
        (target_dir / "venv/Scripts/python.exe", "local venv"),
        (target_dir / "venv/bin/python", "local venv"),
    ]:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand), label
    return sys.executable, "system/invoking python"


def verify(target_dir: Path) -> bool:
    """Run test suite in target directory."""
    test_file = target_dir / "tests/gateway/test_photon_bubble_streaming.py"
    if not test_file.is_file():
        print(f"[!] Test file not found in target: {test_file}")
        return False

    print(f"[*] Running test suite in: {target_dir}")
    python_bin, _ = find_target_python(target_dir)
    env = os.environ.copy()
    cur_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(target_dir) + (os.pathsep + cur_pypath if cur_pypath else "")
    res = subprocess.run(
        [python_bin, "-m", "unittest", "tests/gateway/test_photon_bubble_streaming.py"],
        cwd=target_dir,
        env=env,
    )
    return res.returncode == 0


# -----------------------------------------------------------------------------
# CLI Entrypoint
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AirHermes - Transactional Installer, Diagnostic & Lifecycle Manager"
    )
    parser.add_argument(
        "--target", "-t", type=Path, default=None,
        help="Path to hermes-agent root directory"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Perform complete staged preflight validation without making changes"
    )
    parser.add_argument(
        "--doctor", action="store_true",
        help="Run comprehensive health and compatibility diagnostics"
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Run test suite to verify installation"
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="Safely uninstall AirHermes and restore original files"
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="Force operation (e.g. override conflict during uninstallation)"
    )

    args = parser.parse_args()
    target = args.target or find_default_hermes()
    if not target:
        print("[!] Could not auto-detect hermes-agent directory. Please pass --target /path/to/hermes-agent")
        sys.exit(1)

    target = target.resolve()
    installer = TransactionalInstaller(target_dir=target, source_root=ROOT)

    if args.doctor:
        sys.exit(doctor(target))

    if args.uninstall:
        success = installer.uninstall(force=args.force)
        sys.exit(0 if success else 1)

    if args.verify:
        success = verify(target)
        sys.exit(0 if success else 1)

    # Default action: install (or dry-run install)
    success = installer.install(dry_run=args.dry_run)
    if success and not args.dry_run:
        verify(target)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
