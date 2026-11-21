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

AirHermes is an extension suite for Hermes Agent designed specifically for the iMessage (Photon) platform. It splits LLM output into progressive discrete bubbles, introduces human typing cadences, and integrates native iOS features—interactive polls, Apple Calendar events, Apple Maps Unified Place cards with Retina snapshots, rich link previews, fullscreen screen effects, and semantic Tapbacks.

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
| **Message Pacing** | Instant burst dumping all bubbles simultaneously | Adaptive pacing delay (300ms–600ms) proportional to bubble length to simulate natural typing |
| **Scheduling** | Plain text requiring manual copy-pasting | Clean `.ics` native card with UTF-8 BOM; one tap adds directly to Apple Calendar |
| **Location & Maps** | Plain text address or unrendered link | Apple Maps Unified Place URL (`/place`) with offline Retina map snapshot and 1-tap navigation |
| **Quizzes & Polls** | Plain text multi-choice lists | Native iMessage interactive poll cards with real-time voter avatars and count updates |
| **Expressive Reactions** | Standard text responses only | Native Tapback reactions (❤️, 👍, etc.) and context-aware fullscreen effects (balloons, fireworks, lasers) |

---

## Key Features

- **Streaming Discrete Bubble Parser**  
  Supports explicit `<bubble>` tags as well as intelligent paragraph fallback (`\n\n`) for untagged text. Maintains an internal state machine across bubble boundaries to keep Markdown code fences balanced and prevent tag leakage. Automatically handles CJK punctuation spacing.

- **Adaptive Pacing Queue**  
  Implements a 5-state lifecycle queue (`Queued` → `Sending` → `Sent`) with adaptive delays between consecutive bubbles. Includes network drop protection and late ACK reconciliation.

- **Apple Maps Unified Place URLs (`/place`)**  
  Generates standard Apple Maps unified place links (`/place?coordinate=...&name=...&map=explore`). iMessage natively renders high-DPI vector map tiles from coordinates, allowing users to start navigation in one tap. Built-in coordinate lookup table acts as an instant fallback when coordinates are omitted.

- **Native Calendar Cards (`.ics`)**  
  Generates RFC 5545 compliant `.ics` attachments without ugly random hashes. Encoded with UTF-8 BOM and explicit charset declarations to prevent mojibake across Apple platforms.

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

### Automated Installation

```bash
git clone https://github.com/<your-username>/AirHermes.git
cd AirHermes

# Automatically locates local Hermes Agent, backs up original files, and applies patches
python install.py
```

Restart the Hermes gateway to apply changes:

```bash
hermes gateway restart
```

### Uninstallation

To cleanly roll back Hermes Agent to its original unpatched state:

```bash
python install.py --uninstall
hermes gateway restart
```

---

## Directory Structure

```text
AirHermes/
├── assets/                        # Showcase demo screenshots
│   ├── demo_poll.jpg
│   ├── demo_calendar_maps.jpg
│   ├── demo_rich_link.jpg
│   └── demo_screen_effects.jpg
├── gateway/
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
│   └── test_photon_bubble_streaming.py  # Comprehensive automated test suite
├── install.py                     # Installer, verifier, and uninstaller tool
├── README.md                      # Chinese Documentation (Default)
└── README_EN.md                   # English Documentation
```

---

## Testing

Run the automated test suite to verify parser and protocol behaviors:

```bash
python -m unittest tests/test_photon_bubble_streaming.py
```

---

## License

This project is licensed under the [MIT License](LICENSE).
