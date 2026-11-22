#!/usr/bin/env python3
"""Comprehensive unit and integration test suite for AirHermes Transactional Installer.

Tests preflight validation, ACID transactions, staging sandboxes, persistent
journaling, rollback on failure, conflict detection, and safe uninstallation.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure AirHermes root is in path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from install import (  # noqa: E402
    AIRHERMES_VERSION,
    InstallationManifest,
    TransactionalInstaller,
    atomic_copy,
    compute_sha256,
    doctor,
    resolve_safe_relpath,
)


class BaseInstallerTestCase(unittest.TestCase):
    """Sets up realistic mock Hermes Agent targets and AirHermes sources."""

    def setUp(self):
        self._temp_dir = tempfile.mkdtemp(prefix="airhermes_test_")
        self.temp_root = Path(self._temp_dir)
        self.mock_hermes = self.temp_root / "hermes-agent"
        self.mock_hermes.mkdir(parents=True, exist_ok=True)

        # Create standard Hermes directory structure
        (self.mock_hermes / "gateway").mkdir(parents=True, exist_ok=True)
        (self.mock_hermes / "plugins/platforms/photon/sidecar").mkdir(parents=True, exist_ok=True)
        (self.mock_hermes / "tests/gateway").mkdir(parents=True, exist_ok=True)

        # Populate original Hermes core files
        self.orig_run_turn_content = "# Original Hermes run_turn.py\ndef run_turn():\n    return 'original'\n"
        self.orig_run_turn_runner_content = "# Original Hermes run_turn_runner.py\nclass TurnRunner:\n    pass\n"
        self.orig_session_content = "# Original Hermes session.py\n_STATIC_PLATFORM_NOTES = {}\n"
        self.orig_adapter_content = "# Original Hermes adapter.py\nclass PhotonAdapter:\n    pass\n"

        self._write_file(self.mock_hermes / "gateway/run_turn.py", self.orig_run_turn_content)
        self._write_file(self.mock_hermes / "gateway/run_turn_runner.py", self.orig_run_turn_runner_content)
        self._write_file(self.mock_hermes / "gateway/session.py", self.orig_session_content)
        self._write_file(self.mock_hermes / "plugins/platforms/photon/adapter.py", self.orig_adapter_content)

    def tearDown(self):
        if hasattr(self, "_temp_dir") and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _read_file(self, path: Path) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


class TestTransactionalInstaller(BaseInstallerTestCase):
    """Test suite covering all 12 transactional installer requirements."""

    # 1. Successful Installation
    @patch("subprocess.run")
    def test_01_successful_installation(self, mock_subproc):
        # Mock git apply to succeed cleanly
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)

        self.assertTrue(success)
        manifest_file = self.mock_hermes / ".airhermes/manifest.json"
        self.assertTrue(manifest_file.is_file())

        manifest = InstallationManifest.load(self.mock_hermes)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest.state, "committed")
        self.assertEqual(manifest.step, "committed")
        self.assertEqual(manifest.version, AIRHERMES_VERSION)

        # Standalone files must exist in target
        self.assertTrue((self.mock_hermes / "gateway/bubble_parser.py").is_file())
        self.assertTrue((self.mock_hermes / "gateway/bubble_queue.py").is_file())
        self.assertTrue((self.mock_hermes / "gateway/bubble_stream_consumer.py").is_file())

        # Backups must exist in .airhermes/backup
        self.assertTrue((self.mock_hermes / ".airhermes/backup/gateway/run_turn.py").is_file())
        self.assertEqual(
            compute_sha256(self.mock_hermes / ".airhermes/backup/gateway/run_turn.py"),
            compute_sha256(self.mock_hermes / "gateway/run_turn.py"),
        )

    # 2. Preflight Failure Without Mutation
    def test_02_preflight_failure_without_mutation(self):
        # Remove a required core Hermes file
        (self.mock_hermes / "gateway/run_turn.py").unlink()

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)

        self.assertFalse(success)
        # Verify target was NOT mutated (no .airhermes folder, no bubble files created)
        self.assertFalse((self.mock_hermes / ".airhermes").exists())
        self.assertFalse((self.mock_hermes / "gateway/bubble_parser.py").exists())

    # 3. Patch Failure and Automatic Rollback
    @patch("subprocess.run")
    def test_03_patch_failure_and_rollback(self, mock_subproc):
        # Allow preflight stage to pass, but inject failure during target git apply
        def side_effect(cmd, *args, **kwargs):
            if "apply" in cmd and "--check" not in cmd:
                # Target apply fails
                return MagicMock(returncode=1, stdout="", stderr="error: patch failed: gateway/run_turn.py:562")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = side_effect

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)

        self.assertFalse(success)
        # Rollback must restore original content
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), self.orig_run_turn_content)
        # Created standalone files must be deleted by rollback
        self.assertFalse((self.mock_hermes / "gateway/bubble_parser.py").exists())
        # .airhermes directory must be cleaned up
        self.assertFalse((self.mock_hermes / ".airhermes/manifest.json").exists())

    # 4. Failure During File Copying and Rollback
    @patch("install.atomic_copy")
    @patch("subprocess.run")
    def test_04_failure_during_file_copying_and_rollback(self, mock_subproc, mock_copy):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Fail midway during atomic_copy
        call_count = [0]
        real_atomic_copy = atomic_copy

        def failing_copy(src, dst):
            call_count[0] += 1
            if call_count[0] > 2:
                raise OSError("Simulated disk write failure")
            real_atomic_copy(src, dst)

        mock_copy.side_effect = failing_copy

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)

        self.assertFalse(success)
        # Verify rollback preserved or restored the original files
        self.assertTrue((self.mock_hermes / "gateway/run_turn.py").is_file())

    # 5. Interrupted Installation Recovery (Crash Journal)
    @patch("subprocess.run")
    def test_05_interrupted_installation_recovery(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Simulate a previous crashed run that left state = "in_progress"
        manifest_dir = self.mock_hermes / ".airhermes"
        backup_dir = manifest_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_file = backup_dir / "gateway/run_turn.py"
        self._write_file(backup_file, self.orig_run_turn_content)
        # The target file had been partially overwritten
        self._write_file(self.mock_hermes / "gateway/run_turn.py", "CORRUPTED_INCOMPLETE_WRITE")

        dangling_manifest = InstallationManifest(
            state="in_progress",
            step="copying",
            modified_files={
                "gateway/run_turn.py": {
                    "pre_sha256": "fake_hash",
                    "post_sha256": "",
                    "backup_relpath": ".airhermes/backup/gateway/run_turn.py",
                }
            },
            created_files=["gateway/dangling_file.py"],
            hermes_root=str(self.mock_hermes),
        )
        dangling_manifest.save(self.mock_hermes)
        self._write_file(self.mock_hermes / "gateway/dangling_file.py", "# dangling")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        # Install must detect the crash journal, roll it back to clean state, and succeed
        success = installer.install(dry_run=False)

        self.assertTrue(success)
        self.assertFalse((self.mock_hermes / "gateway/dangling_file.py").exists())
        manifest = InstallationManifest.load(self.mock_hermes)
        self.assertEqual(manifest.state, "committed")

    # 6. Repeated Installation (Idempotency)
    @patch("subprocess.run")
    def test_06_repeated_installation_idempotency(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        # First install
        success1 = installer.install(dry_run=False)
        self.assertTrue(success1)

        # Second install over existing installation
        success2 = installer.install(dry_run=False)
        self.assertTrue(success2)

        manifest = InstallationManifest.load(self.mock_hermes)
        self.assertEqual(manifest.state, "committed")

    # 7. Safe Uninstall
    @patch("subprocess.run")
    def test_07_safe_uninstall(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        self.assertTrue(installer.install(dry_run=False))

        # Uninstall
        uninstalled = installer.uninstall()
        self.assertTrue(uninstalled)

        # Verify created files are gone
        self.assertFalse((self.mock_hermes / "gateway/bubble_parser.py").exists())
        self.assertFalse((self.mock_hermes / "gateway/bubble_queue.py").exists())
        self.assertFalse((self.mock_hermes / ".airhermes").exists())

        # Original files restored
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), self.orig_run_turn_content)

    # 8. User-Modified File Conflict Detection During Uninstall
    @patch("subprocess.run")
    def test_08_user_modified_file_conflict_detection(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        self.assertTrue(installer.install(dry_run=False))

        # Simulate user modifying run_turn.py after AirHermes installation
        modified_content = "# User custom modification after install\npass\n"
        self._write_file(self.mock_hermes / "gateway/run_turn.py", modified_content)

        # Safe uninstall should detect conflict and abort by default
        uninstalled = installer.uninstall(force=False)
        self.assertFalse(uninstalled)
        # User modifications must NOT have been destroyed
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), modified_content)

        # Now uninstall with force=True
        forced_uninstall = installer.uninstall(force=True)
        self.assertTrue(forced_uninstall)
        # Original file restored
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), self.orig_run_turn_content)
        # Conflicted copy saved to .airhermes_user_conflict_bak preserving relative structure
        self.assertTrue((self.mock_hermes / ".airhermes_user_conflict_bak/gateway/run_turn.py").is_file())

    # 9. Legacy Backup (.deluxe_backup) Compatibility
    def test_09_legacy_deluxe_backup_compatibility(self):
        legacy_dir = self.mock_hermes / ".deluxe_backup/gateway"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_run_turn = legacy_dir / "run_turn.py"
        self._write_file(legacy_run_turn, "# Legacy Original Version\n")

        # Create some added files
        self._write_file(self.mock_hermes / "gateway/bubble_parser.py", "# bubble")
        self._write_file(self.mock_hermes / "gateway/run_turn.py", "# Modified by legacy installer")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        uninstalled = installer.uninstall()
        self.assertTrue(uninstalled)

        # Legacy file should be restored
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), "# Legacy Original Version\n")
        self.assertFalse((self.mock_hermes / "gateway/bubble_parser.py").exists())
        self.assertFalse((self.mock_hermes / ".deluxe_backup").exists())

    # 10. Correct Exit Codes & Diagnostics (--doctor, --dry-run)
    @patch("subprocess.run")
    def test_10_exit_codes_and_diagnostics(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Doctor on healthy uninstalled target -> returns 0
        code = doctor(self.mock_hermes)
        self.assertEqual(code, 0)

        # Doctor on non-existent directory -> returns 1
        code_missing = doctor(self.temp_root / "non_existent_hermes")
        self.assertEqual(code_missing, 1)

        # Dry run install -> returns True (exit code 0) without modifying files
        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        dry_success = installer.install(dry_run=True)
        self.assertTrue(dry_success)
        self.assertFalse((self.mock_hermes / ".airhermes").exists())

    # 11. Paths Containing Spaces
    @patch("subprocess.run")
    def test_11_paths_containing_spaces(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        space_hermes = self.temp_root / "hermes agent with spaces"
        (space_hermes / "gateway").mkdir(parents=True, exist_ok=True)
        (space_hermes / "plugins/platforms/photon/sidecar").mkdir(parents=True, exist_ok=True)
        self._write_file(space_hermes / "gateway/run_turn.py", self.orig_run_turn_content)
        self._write_file(space_hermes / "plugins/platforms/photon/adapter.py", self.orig_adapter_content)

        installer = TransactionalInstaller(target_dir=space_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)
        self.assertTrue(success)

        manifest = InstallationManifest.load(space_hermes)
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest.state, "committed")

        uninstalled = installer.uninstall()
        self.assertTrue(uninstalled)

    # 12. Windows and POSIX Path Assumptions & Path Traversal Prevention
    def test_12_path_traversal_prevention(self):
        base = self.mock_hermes.resolve()
        safe_rel = resolve_safe_relpath(Path("gateway/run_turn.py"), base)
        self.assertEqual(str(safe_rel).replace("\\", "/"), "gateway/run_turn.py")

        # Attempt path traversal escaping base directory
        with self.assertRaises(ValueError):
            resolve_safe_relpath(Path("../../outside_hermes.py"), base)

    # 13. Rejection of Partially Patched Environment
    @patch("subprocess.run")
    def test_13_partially_patched_environment_rejected(self, mock_subproc):
        # Simulate partial patch state: run_turn.patch already applied (chk!=0, rev==0),
        # but run_turn_runner.patch unapplied (chk==0)
        def side_effect(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            if "run_turn.patch" in cmd_str:
                if "--reverse" in cmd:
                    return MagicMock(returncode=0, stdout="", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="already applied")
            # Other patches unapplied
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = side_effect

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install(dry_run=False)

        # Must fail preflight and NOT mutate target
        self.assertFalse(success)
        self.assertFalse((self.mock_hermes / ".airhermes").exists())
        self.assertFalse((self.mock_hermes / "gateway/bubble_parser.py").exists())

    # 14. Forced Uninstallation: No Silent Overwrite & Failure Halts Mutation
    @patch("subprocess.run")
    def test_14_conflict_backup_no_silent_overwrite_and_failure_halt(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        self.assertTrue(installer.install(dry_run=False))

        # User modifies run_turn.py
        user_mod_1 = "# User modification 1\n"
        self._write_file(self.mock_hermes / "gateway/run_turn.py", user_mod_1)

        # First forced uninstall: creates conflict backup
        self.assertTrue(installer.uninstall(force=True))
        bak_file_1 = self.mock_hermes / ".airhermes_user_conflict_bak/gateway/run_turn.py"
        self.assertTrue(bak_file_1.is_file())
        self.assertEqual(self._read_file(bak_file_1), user_mod_1)

        # Re-install and modify again with different content
        self.assertTrue(installer.install(dry_run=False))
        user_mod_2 = "# User modification 2 (different)\n"
        self._write_file(self.mock_hermes / "gateway/run_turn.py", user_mod_2)

        # Second forced uninstall: MUST NOT silently overwrite the previous conflict backup
        self.assertTrue(installer.uninstall(force=True))
        # Original backup 1 must still have user_mod_1
        self.assertEqual(self._read_file(bak_file_1), user_mod_1)
        # A second backup file with timestamp suffix must exist and contain user_mod_2
        conflict_dir = self.mock_hermes / ".airhermes_user_conflict_bak/gateway"
        all_backups = list(conflict_dir.glob("run_turn*.py"))
        self.assertGreaterEqual(len(all_backups), 2)
        contents = [self._read_file(p) for p in all_backups]
        self.assertIn(user_mod_1, contents)
        self.assertIn(user_mod_2, contents)

    # 15. Rollback Interruption Resumption & Preserves Backups on Error
    @patch("subprocess.run")
    def test_15_interrupted_rollback_resumption_and_preserves_backups_on_error(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        self.assertTrue(installer.install(dry_run=False))

        # Manifest exists and is committed. Now simulate a broken transaction
        m = InstallationManifest.load(self.mock_hermes)
        m.state = "in_progress"
        m.step = "patching"
        m.save(self.mock_hermes)

        # Inject failure during atomic_copy in rollback
        with patch("install.atomic_copy", side_effect=OSError("Disk write error")):
            rollback_ok = installer.rollback(m)
            self.assertFalse(rollback_ok)
            # CRITICAL: Backups must NOT be destroyed when rollback fails!
            self.assertTrue((self.mock_hermes / ".airhermes/backup").is_dir())
            m_failed = InstallationManifest.load(self.mock_hermes)
            self.assertEqual(m_failed.step, "rollback_failed")

        # Now resume rollback without errors: must succeed and clean up
        rollback_resumed = installer.rollback(m_failed)
        self.assertTrue(rollback_resumed)
        self.assertFalse((self.mock_hermes / ".airhermes").exists())

    # 16. Corrupted Manifest Detection
    def test_16_corrupted_manifest_handling(self):
        manifest_dir = self.mock_hermes / ".airhermes"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = manifest_dir / "manifest.json"
        # Write corrupted invalid JSON
        self._write_file(manifest_file, "{invalid_json: true, unterminated")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        # Install must refuse to proceed over corrupted manifest
        self.assertFalse(installer.install(dry_run=False))

        # Doctor must report error
        self.assertEqual(doctor(self.mock_hermes), 1)

        # Safe uninstall must refuse to proceed without force
        self.assertFalse(installer.uninstall(force=False))

    # 17. Repeated Installation Preserves Original Pre-AirHermes Backup
    @patch("subprocess.run")
    def test_17_repeated_install_preserves_original_pre_airhermes_backup(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        # 1st install
        self.assertTrue(installer.install(dry_run=False))
        backup_file = self.mock_hermes / ".airhermes/backup/gateway/run_turn.py"
        self.assertEqual(self._read_file(backup_file), self.orig_run_turn_content)

        # 2nd install over existing installation
        self.assertTrue(installer.install(dry_run=False))
        # Backup MUST still contain the original upstream content, not the patched content
        self.assertEqual(self._read_file(backup_file), self.orig_run_turn_content)

        # Uninstall must restore original upstream content
        self.assertTrue(installer.uninstall())
        self.assertEqual(self._read_file(self.mock_hermes / "gateway/run_turn.py"), self.orig_run_turn_content)

    # 18. Malicious Manifest Path Traversal Prevention
    def test_18_malicious_manifest_path_traversal_prevention(self):
        outside_file = self.temp_root / "outside_target.txt"
        self._write_file(outside_file, "SENSITIVE_OUTSIDE_DATA")

        # Create malicious manifest attempting to delete outside_target.txt
        malicious_manifest = InstallationManifest(
            state="committed",
            step="committed",
            modified_files={},
            created_files=["../../outside_target.txt"],
            hermes_root=str(self.mock_hermes),
        )
        malicious_manifest.save(self.mock_hermes)

        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        installer.uninstall()

        # Sensitive outside file MUST NOT be touched
        self.assertTrue(outside_file.is_file())
        self.assertEqual(self._read_file(outside_file), "SENSITIVE_OUTSIDE_DATA")

    # 19. AirHermes Config Module Deployment and Rollback
    @patch("subprocess.run")
    def test_19_airhermes_config_deployment_and_rollback(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")
        installer = TransactionalInstaller(target_dir=self.mock_hermes, source_root=ROOT)
        success = installer.install()
        self.assertTrue(success)

        # Verify gateway/airhermes_config.py was copied to target
        deployed_config = self.mock_hermes / "gateway" / "airhermes_config.py"
        self.assertTrue(deployed_config.is_file(), "gateway/airhermes_config.py must be deployed")

        # Verify recorded in manifest
        manifest = InstallationManifest.load(self.mock_hermes)
        self.assertIsNotNone(manifest)
        self.assertIn("gateway/airhermes_config.py", manifest.created_files)

        # Verify clean uninstallation removes it
        uninstalled = installer.uninstall()
        self.assertTrue(uninstalled)
        self.assertFalse(deployed_config.exists(), "gateway/airhermes_config.py must be removed upon uninstall")


if __name__ == "__main__":
    unittest.main()
