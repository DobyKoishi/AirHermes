<div align="center">

# AirHermes

### Discrete bubble streaming and native iOS ecosystem integration for Hermes Agent on iMessage.

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-orange.svg?style=flat-square)](https://github.com/NousResearch/hermes-agent)
[![Platform](https://img.shields.io/badge/Platform-iMessage%20(Photon)-blue.svg?style=flat-square)](https://photon.sh)
[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

<br />

[简体中文](README.md) &nbsp;|&nbsp; **English**

</div>

---

Hermes Agent's built-in Photon transport delivers responses as monolithic messages. When interacting on iOS or macOS via iMessage, single walls of text provide no conversational pacing and cannot leverage Apple's native rich UI cards.

AirHermes is an extension suite for Hermes Agent designed specifically for the iMessage (Photon) platform. It splits LLM output into progressive discrete bubbles, introduces human typing cadences, and integrates native iOS features like interactive polls, Apple Calendar events, Apple Maps place cards, rich link previews, fullscreen screen effects, and semantic Tapbacks.

---

## Showcase

| Interactive Native Polls (`<poll>`) | Calendar Events & Apple Maps (`.ics` / `/place`) |
| :---: | :---: |
| <img src="assets/demo_poll.jpg" width="380" alt="iMessage Poll Demo" /> | <img src="assets/demo_calendar_maps.jpg" width="380" alt="Calendar and Maps Demo" /> |
| **Rich Link Previews (LPLinkView) & Context Memory** | **Fullscreen Effects (Balloons) & Semantic Tapbacks** |
| <img src="assets/demo_rich_link.jpg" width="380" alt="Rich Link Preview Demo" /> | <img src="assets/demo_screen_effects.jpg" width="380" alt="Screen Effects Demo" /> |

---

## Experience Comparison

| Interaction | Default Behavior | AirHermes Enhancement |
| :--- | :--- | :--- |
| **First Response** | Freezes for seconds during reasoning or tool calls | Dispatches an immediate spoken acknowledgment within 1s ("Got it, checking now"), then streams progressively |
| **Message Layout** | Single monolithic wall of text | Splits into natural 1–2 sentence bubbles, eliminating reading strain on mobile |
| **Message Pacing** | Instant burst dumping all bubbles simultaneously | Adaptive pacing delay (baseline 0.85s, dynamic 0.35s–3.5s+) proportional to bubble length and punctuation |
| **Scheduling** | Plain text requiring manual copy-pasting | RFC 5545 compliant `.ics` calendar card; one tap adds directly to Apple Calendar |
| **Location & Maps** | Plain text address or unrendered link | Validated Apple Maps Unified Place URL (`/place`) for native card rendering and 1-tap navigation |
| **Quizzes & Polls** | Plain text multi-choice lists | Native iMessage interactive poll cards with real-time voter avatars and count updates |
| **Expressive Reactions** | Standard text responses only | Native Tapback reactions (❤️, 👍, etc.) and context-aware fullscreen effects (balloons, fireworks, lasers) |

---

## Key Features

- **Streaming Discrete Bubble Parser**  
  Supports explicit `<bubble>` tags as well as intelligent paragraph fallback (`\n\n`) for untagged text. Maintains an internal state machine across bubble boundaries to keep Markdown code fences balanced and prevent tag leakage. Automatically handles CJK punctuation spacing.

- **Adaptive Pacing Queue**  
  Implements a 5-state lifecycle queue (`Queued` → `Sending` → `Sent`) with adaptive delays between consecutive bubbles. Includes network drop protection and late ACK reconciliation.

- **Apple Maps Unified Place URLs (`/place`)**  
  Generates validated Apple Maps unified place links (`/place?coordinate=...&name=...&map=explore`). iMessage natively renders interactive place cards from coordinates, allowing users to start navigation in one tap. Built-in coordinate lookup table acts as an instant fallback when coordinates are omitted.

- **Native Calendar Cards (`.ics`)**  
  Generates RFC 5545 compliant `.ics` attachments with 75-octet line folding, CRLF endings, and UTF-8 encoding without nonstandard charset parameters.

- **Interactive Native Polls (`<poll>`)**  
  Integrates directly with spectrum-ts at the transport layer, rendering native multi-option poll widgets directly inside the iMessage conversation stream.

- **Fullscreen Screen Effects & Tapbacks**  
  Enables the agent to trigger fullscreen celebrations (balloons, fireworks, confetti, lasers, spotlight) and bubble effects (invisible ink), along with zero-text standalone Tapbacks.

---

## XML Protocol Tag Reference

You can output these lightweight semantic tags in system prompts or agent responses:

| Tag | Description | Example |
| :--- | :--- | :--- |
| `<bubble>text</bubble>` | Discrete message bubble | `<bubble>Are we still on for dinner tonight?</bubble>` |
| `<tapback>emoji</tapback>` | Native Apple Tapback reaction | `<tapback>❤️</tapback>` (supports ❤️ 👍 👎 😆 ‼️ ❓) |
| `<poll title="...">` | Interactive native poll card | `<poll title="Where to?"><option>Beach</option><option>Cabin</option></poll>` |
| `<calendar title="..." start="..." />` | Native Apple Calendar event | `<calendar title="Flight" start="2026-11-21 09:00" />` |
| `<map name="..." coordinate="..." />` | Apple Maps place card | `<map name="Apple Park" coordinate="37.3348,-122.0090" address="1 Apple Park Way" />` |
| `<contact name="..." phone="..." />` | Native vCard contact card (.vcf) | `<contact name="Alice" phone="+1234567890" />` |
| `<effect type="...">text</effect>` | Fullscreen effect | `<effect type="balloons">Congratulations on the offer! 🎉</effect>` |
| `<invisible>text</invisible>` | Invisible ink bubble effect | `<invisible>Tap to reveal</invisible>` |
| `<action title="..." shortcut="..." />` | Deep link / Shortcuts trigger | `<action title="Log Expense" shortcut="QuickExpense" />` |

---

## Architecture Flow

```text
       LLM Incremental Delta Stream (Token stream)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│                   BubbleParser                   │
│   • Semantic XML tags (<bubble>, <poll>, <map>)  │
│   • Cross-bubble Markdown code fence balancing   │
│   • Apple Maps Unified Place URL assembly        │
│   • Plain text paragraph fallback splitting      │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│              StreamingBubbleQueue                │
│   • 5-State lifecycle tracking (Queued -> Sent)  │
│   • Length-based adaptive pacing delay           │
│   • Late ACK reconciliation & network tolerance  │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│             Photon Platform Adapter              │
│   • Multi-payload dispatch (Text/Poll/Effect)    │
│   • Node Sidecar retry logic & HEIC conversion   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
           User iPhone / iPad / Mac iMessage
```

---

## Installation & Setup

### Prerequisites

1. An existing installation of [Hermes Agent](https://github.com/NousResearch/hermes-agent).
2. A configured Photon (iMessage) provider:
   - Run `hermes photon setup` if configuring for the first time.
   - If Photon is already connected and working, you can proceed directly.

### Automated Installation & Diagnostics

```bash
git clone https://github.com/DobyKoishi/AirHermes.git
cd AirHermes

# 1. Run health check & compatibility diagnostic (optional)
python install.py --doctor

# 2. Dry-run simulation in sandbox without mutating any files
python install.py --dry-run

# 3. Execute transactional installation with automatic backups & rollback safety
python install.py
```

Restart the Hermes gateway to apply changes:

```bash
hermes gateway restart
```

### Safe Uninstallation

To cleanly roll back Hermes Agent to its original unpatched state:

```bash
# Verifies SHA-256 hashes, restores modified files, and deletes injected modules
python install.py --uninstall

# If you edited files after installing, append --force to overwrite (conflict backup created)
# python install.py --uninstall --force

hermes gateway restart
```

### Configuration & Feature Flags

AirHermes features a zero-overhead configuration system. All features are enabled by default, preserving the out-of-the-box multi-bubble streaming experience.

You can configure AirHermes inside `~/.hermes/config.yaml` under `platforms.photon`, or override settings globally via environment variables.

#### 1. Core Settings Reference

| Key (YAML) | Environment Variable (ENV) | Default | Value Range / Description | Fallback Behavior When Disabled |
| :--- | :--- | :---: | :--- | :--- |
| `bubble_streaming` | `AIRHERMES_BUBBLE_STREAMING` | `true` | `bool`: `true` / `false` | Skips `BubbleStreamConsumer`, uses Hermes's original single-message final delivery |
| `bubble_min_interval` | `AIRHERMES_BUBBLE_MIN_INTERVAL` | `0.85` | `float`: `[0.2, 5.0]` (sec) | Base bubble cadence; invalid or non-finite numbers (NaN/Inf) fall back to default with a warning |
| `bubble_adaptive_pacing` | `AIRHERMES_BUBBLE_ADAPTIVE_PACING` | `true` | `bool`: `true` / `false` | Human-like adaptive pacing; if disabled, uses constant `bubble_min_interval` |
| `enable_tapbacks` | `AIRHERMES_ENABLE_TAPBACKS` | `true` | `bool`: `true` / `false` | Native reactions; if disabled, never invokes reaction API and sends no emoji bubble |
| `enable_polls` | `AIRHERMES_ENABLE_POLLS` | `true` | `bool`: `true` / `false` | Interactive poll cards; if disabled, degrades gracefully to readable plain-text options |
| `enable_calendar` | `AIRHERMES_ENABLE_CALENDAR` | `true` | `bool`: `true` / `false` | Native Apple Calendar (.ics); if disabled, degrades to readable event description text |
| `enable_maps` | `AIRHERMES_ENABLE_MAPS` | `true` | `bool`: `true` / `false` | Native Apple Maps cards; if disabled, degrades to readable text with official Apple Maps URL |
| `enable_effects` | `AIRHERMES_ENABLE_EFFECTS` | `true` | `bool`: `true` / `false` | Full-screen & bubble effects; if disabled, strips effect directives and delivers plain text |

#### 2. YAML Configuration Example (`~/.hermes/config.yaml`)

```yaml
platforms:
  photon:
    project_id: "your_project_id"
    project_secret: "your_project_secret"
    # AirHermes Settings (placed directly under platforms.photon)
    bubble_streaming: true
    bubble_min_interval: 0.85
    bubble_adaptive_pacing: true
    enable_tapbacks: true
    enable_polls: true
    enable_calendar: true
    enable_maps: true
    enable_effects: true
```

#### 3. Environment Variable Precedence

Precedence: `AIRHERMES_*` Environment Variables > `config.yaml` (`platforms.photon`) > Defaults.

```bash
# Example: Temporarily disable native polls and calendar invites
export AIRHERMES_ENABLE_POLLS=false
export AIRHERMES_ENABLE_CALENDAR=false
```

#### 4. Type Safety & Reliability Safeguards

- **Strict Boolean Parsing**: Only accepts `true`/`false`/`1`/`0`/`yes`/`no`/`on`/`off` (case-insensitive). Invalid values warn and fall back safely to defaults.
- **Numeric Boundary Validation**: Strictly rejects `NaN`, `+Inf`, `-Inf`, and numbers outside `[0.2, 5.0]`.
- **Per-Turn Immutable Snapshot**: Every turn establishes a frozen configuration snapshot (`frozen=True`), preventing concurrent races or mid-turn environment mutation.
- **Privacy & Security**: Configuration parsing and warning logs never expose conversation messages, tokens, or credentials.

---

## Directory Structure

```text
AirHermes/
├── .github/workflows/             # GitHub Actions CI automation
│   ├── ci.yml                     # Cross-platform multi-Python unit testing and linting
│   └── integration.yml            # Upstream Hermes Agent integration workflow (optional dispatch)
├── assets/                        # Showcase demo screenshots
│   ├── demo_poll.jpg
│   ├── demo_calendar_maps.jpg
│   ├── demo_rich_link.jpg
│   └── demo_screen_effects.jpg
├── gateway/
│   ├── airhermes_config.py        # Immutable configuration & feature flags (YAML & ENV)
│   ├── bubble_parser.py           # Multi-tag bubble parser with paragraph fallback
│   ├── bubble_queue.py            # 5-state lifecycle queue with adaptive pacing
│   └── bubble_stream_consumer.py  # Gateway streaming consumer bridge
├── plugins/platforms/photon/
│   ├── adapter.py                 # Photon adapter (effects, polls, tapbacks)
│   └── sidecar/
│       ├── index.mjs              # Node sidecar with exponential backoff
│       └── patch-spectrum-poll.mjs# spectrum-ts poll robustness patch
├── patches/                       # Standard git patches for Hermes gateway
│   ├── hermes_all.patch           # Consolidated single patch
│   ├── run_turn.patch
│   ├── run_turn_runner.patch
│   └── session.patch
├── tests/
│   ├── test_installer.py          # Installer transactional rollback, WAL, crash recovery & sandbox tests
│   └── test_photon_bubble_streaming.py  # Bubble parser, adaptive pacer & streaming lifecycle unit suite
├── install.py                     # Transactional installer, health diagnostics & uninstaller
├── README.md                      # Chinese Documentation (Default)
└── README_EN.md                   # English Documentation
```

---

## Attachment Delivery & Security Model (Phase 5 Security & Compatibility)

AirHermes implements a strict **local sandboxing and declarative attachment security containment boundary** to prevent untrusted model-generated text or malicious directives from exfiltrating sensitive host files.

### 1. Behavioral Changes & Compatibility Notice
> [!IMPORTANT]
> The following security safeguards represent intentional behavioral changes from upstream unconstrained dispatch and are not completely backward-compatible:

- **Neutralization of Bare Host Path Extraction**: `PhotonAdapter.extract_local_files()` returns `([], content)`. Bare host paths (e.g. `C:\docs\secret.pdf` or `/etc/hosts`) appearing in model-generated prose are **no longer** automatically scanned and delivered as native attachments on Photon.
- **Strict Authorization for Direct Adapter Calls**: Direct calls to `PhotonAdapter.send_document()`, `send_image_file()`, `send_voice()`, or `send_video()` strictly require the target path to be a pre-authorized, staged copy in `AttachmentRegistry`. Passing arbitrary unregistered host paths is immediately rejected (`SendResult(success=False, error="Attachment not authorized: ...")`), eliminating automatic authorization fallbacks.
- **Supported Workflows & Migration**:
  - **Internal Generators (Fully Supported)**: Built-in contact and calendar generators (`<calendar>`, `<contact>`, etc.) automatically stage files through `stage_and_authorize()` with dedicated producer credentials and deliver via typed actions.
  - **Remote Images**: `send_image(image_url)` continues to work as expected via local caching.
  - **Custom Tools & Extensions**: Tools wishing to send host files must explicitly register them first:
    ```python
    from gateway.attachment_registry import registry
    record, err = registry.stage_and_authorize(
        chat_id=chat_id,
        source_path="/path/to/file.pdf",
        producer="my_tool",
        turn_id=turn_id,
    )
    if record:
        await adapter.send_document(chat_id, record.staged_path, metadata={"turn_id": turn_id})
    ```

### 2. Lifecycle & Cancellation Safeguards (Bounded Quarantine)
- **Unknown Outcome Quarantine**: When an asynchronous dispatch task is cancelled or times out while native transmission is in progress, the attachment enters `OUTCOME_UNKNOWN` with a 120-second quarantine window. Turn cleanup will **not** delete the file immediately, allowing external native senders (e.g., Node.js Sidecar) to complete opening and reading from disk without premature deletion.
- **Strict No-Retry Rule**: Artifacts in `OUTCOME_UNKNOWN` cannot be automatically retried or re-authorized, preventing duplicate message delivery over high-latency networks.
- **Single-Use Enforcement**: Every staged artifact expires immediately upon confirmed delivery (`SUCCEEDED`), preventing cross-chat or cross-turn replay attacks.

### 3. Cross-Process Isolation & Crash Recovery
- Staging subdirectories follow the format `proc_<pid>_<opaque_token>`.
- `recover_abandoned_staging` verifies creator PID liveness via operating system APIs (Windows `OpenProcess` / POSIX `kill(pid, 0)`), **never deleting artifacts belonging to active, running processes**.
- Recovery strictly unlinks symbolic links and NTFS junction points without traversing into target directories.

### 4. Windows Filesystem Security Limitations
- On Windows, `os.chmod(0o700)` toggles only the read-only attribute and does not enforce NTFS DACL isolation.
- The default `%TEMP%` staging directory relies on Windows user profile ACL inheritance for multi-user isolation.
- **Boundary Notice**: Other processes running under the same Windows user account possess equal filesystem permissions. AirHermes defends against LLM text injection and cross-session privilege escalation, not compromised local processes executing under the same user privileges.

---

## Testing & CI Architecture

AirHermes maintains an independent, cross-platform automated test infrastructure.

### 1. Local Standalone Unit Tests (Hermes Not Required)

Core parser, queue, and installer algorithms are completely decoupled from Hermes Agent and can run in any standard Python 3.11+ environment without external dependencies:

```bash
# Run installer transactional rollback and crash recovery tests (16 tests)
python -m unittest -v tests/test_installer.py

# Run bubble parser, adaptive pacing, and streaming lifecycle unit tests (62 tests: 59 passed, 3 require Hermes environment)
python -m unittest -v tests/test_photon_bubble_streaming.py

# Or discover and run all standalone unit tests automatically (143 tests: 140 passed, 3 skipped)
python -m unittest discover -s tests -p "test_*.py"

# Linting and bytecode compilation checks
ruff check .
python -m py_compile install.py gateway/*.py tests/*.py
```

### 2. Full Upstream Hermes Integration Tests

To run integration tests that verify interactions with upstream Hermes Agent internal classes (`PhotonAdapter` flags, `TurnRunner` tool progress hints):

```bash
# Method A: Specify Hermes directory in PYTHONPATH to execute all 45 tests
PYTHONPATH="/path/to/hermes-agent:." python -m unittest -v tests/test_photon_bubble_streaming.py

# Method B: Use installer verification inside an installed target environment
python install.py --verify --target /path/to/hermes-agent
```

### 3. CI Strategy & Behavior

- **Matrix Coverage**: Automatically tested via GitHub Actions on `Ubuntu`, `macOS`, and `Windows` across Python `3.11` and `3.12`.
- **Hermetic & Offline**: Repository CI runs pure unit and transactional tests completely offline without requiring live iMessage credentials or Photon servers.
- **Optional Upstream Integration**: `.github/workflows/integration.yml` provides a manually triggered workflow (`workflow_dispatch`) to clone upstream Hermes Agent, inject AirHermes, and run the complete 45-test integration suite.

### 4. Known Limitations

- **Live Service Connectivity**: Unit and CI tests verify software state machines, protocol parsers, and transactional integrity; live iMessage rich link rendering ultimately depends on macOS APNs and active Photon bridge authentication.
- **Power-Loss Durability**: Filesystem transactions leverage atomic replacements and write-ahead journaling for crash recovery, but do not issue fsync barrier flushes; resilience against catastrophic kernel panics or sudden power loss is bounded by OS cache flush semantics.

---

## License

This project is licensed under the [MIT License](LICENSE).
