# AirHermes Security Architecture & Sandboxing

AirHermes operates as an intermediary between the Hermes Agent reasoning engine and the Apple Messages environment. This document describes the security controls governing attachments, file mutations, and runtime execution.

---

## 1. Attachment Security & Validation

All outbound media and document attachments undergo strict multi-layer preflight verification before transmission:

### Whitelist of Allowed Media Types
Only verified media and data types are accepted:
- **Images**: `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `image/heic`
- **Audio / Video**: `audio/m4a`, `audio/mp3`, `video/mp4`
- **System Records**: `text/calendar` (`.ics`), `text/vcard` (`.vcf`)

Any attachment with an unrecognized extension or unwhitelisted MIME type is rejected immediately with an audit log entry.

### Path Traversal Defense
- File paths provided in attachment tags are strictly resolved and checked against base directories using `resolve_safe_relpath()`.
- Directory escape sequences (e.g., `../../`, absolute root overrides) are intercepted and raise immediate security errors.

### Size Ceilings & Quarantine
- **Size Cap**: Attachments exceeding configured maximum size (default 25MB) are blocked from transmission.
- **Quarantine Window**: Generated temporary artifacts are isolated in a scoped quarantine directory and automatically pruned upon turn completion.

---

## 2. Transactional Mutation & Crash Recovery

The AirHermes installer and runtime file modifications implement journaled transactions to guarantee target system integrity:

- **Staged Sandbox Validation**: Patches and modifications are first validated in a temporary sandboxed directory structure before touching real files.
- **Journaled Manifest**: Every file creation, modification, and hash is recorded in `.airhermes/manifest.json`.
- **Atomic Replacements**: File copies use temporary sidecar files followed by atomic `os.replace` operations.
- **Crash Recovery**: If an installation or update is interrupted mid-way, subsequent runs detect the incomplete step and trigger an automatic rollback to the verified baseline.

---

## 3. Platform & Filesystem Hardening

### Windows File Locking & Case Sensitivity
- Windows file systems hold strict locks on active file descriptors. AirHermes ensures all file handles, streams, and subprocess pipes are explicitly closed before rename or unlink operations.
- Path comparisons normalize case and separators (`/` vs `\`) to eliminate cross-platform bypasses.

### Restricted Console Encodings
- Console logging routes through `safe_print()`, avoiding `UnicodeEncodeError` crashes on restricted terminal codepages (e.g. `cp1252`, `ascii`) by utilizing lossless backslash replacements.
