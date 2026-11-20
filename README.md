# Hermes-iMessage-Photon-Deluxe

An extension suite for Hermes Agent that enables discrete multi-bubble streaming and native iOS ecosystem parity over iMessage (via Photon).

---

## Overview

Default chat agent integrations send whole-turn responses as a single monolithic block. On mobile platforms like Apple iMessage, this results in awkward delays followed by oversized walls of text.

**Hermes-iMessage-Photon-Deluxe** transforms this behavior into natural, human-paced messaging:

1. **Discrete Multi-Bubble Streaming**: Delivers thoughts incrementally as short, individual message bubbles (`<bubble>...</bubble>`) with cognitive pacing.
2. **Tool Heartbeats**: Automatically emits debounced, spoken status bubbles when tools (searches, code runs, file reads) take longer than 2.5 seconds.
3. **Native iOS Parity**:
   - **Tapback Reactions**: Semantic tapbacks (`❤️`, `👍`, `👎`, `😆`, `‼️`, `❓`) with zero-text reaction support.
   - **iMessage Screen & Bubble Effects**: Fullscreen confetti, fireworks, lasers, balloons, or invisible ink.
   - **Interactive Polls**: Native 1-tap voting cards (`<poll>`).
   - **Apple Calendar (`.ics`)**: Structured calendar invite cards with clean UTF-8 filenames.
   - **Apple Maps**: Native location cards (`<map>`).
   - **Apple Contacts (`.vcf`)**: Contact cards (`<contact>`).
   - **iOS Shortcuts**: 1-tap deep links (`<action>`).
4. **Resilient Queue Architecture**: 5-state lifecycle (`QUEUED` -> `SENDING` -> `SENT | FAILED | UNKNOWN_DELIVERY | CANCELLED`), late ACK reconciliation, circuit breaker, and CJK punctuation CommonMark formatting fixes.

---

## Architecture Flow

```text
  LLM Delta Stream
         │
         ▼
┌──────────────────┐
│   BubbleParser   │ ◄─── Extracts <bubble>, <tapback>, <poll>, <effect>, etc.
└────────┬─────────┘      (Preserves code fences, isolates URLs, paragraph fallback)
         │
         ▼
┌──────────────────┐
│  StreamingQueue  │ ◄─── 5-state lifecycle tracking (QUEUED -> SENDING -> SENT)
└────────┬─────────┘      (400ms idle pacing, circuit breaker, late ACK reconciliation)
         │
         ▼
┌──────────────────┐
│  Photon Adapter  │ ◄─── Dispatches to Node Sidecar via HTTP JSON
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ iMessage Devices │ ◄─── Discrete bubbles, interactive poll cards, full-screen effects
└──────────────────┘
```

---

## Directory Structure

```text
Hermes-iMessage-Photon-Deluxe/
├── gateway/
│   ├── bubble_parser.py           # Multi-tag parser with paragraph fallback
│   ├── bubble_queue.py            # 5-state lifecycle queue and pacing engine
│   └── bubble_stream_consumer.py  # Gateway streaming consumer bridge
├── plugins/platforms/photon/
│   ├── adapter.py                 # Photon platform adapter with native iOS features
│   └── sidecar/
│       ├── index.mjs              # Sidecar with retry logic on inbound media
│       ├── package.json
│       └── patch-spectrum-poll.mjs
├── patches/                       # Unified diffs for core gateway hooks
│   ├── hermes_all.patch           # All-in-one patch
│   ├── run_turn.patch
│   ├── run_turn_runner.patch
│   └── session.patch
├── tests/
│   └── test_photon_bubble_streaming.py  # Test suite (34 test cases)
├── install.py                     # One-click installer / patch manager
└── README.md
```

---

## Prerequisites

Hermes-iMessage-Photon-Deluxe upgrades the official Hermes Photon integration. You will need:

1. A working [Hermes Agent](https://github.com/NousResearch/hermes-agent) repository.
2. iMessage paired via Photon:
   - If you **already configured Photon** (`hermes photon setup`): running `python install.py` immediately elevates your bot to Deluxe upon launching `hermes gateway`.
   - If this is a **fresh setup**: run `hermes photon setup` (to pair your phone number / Apple ID) before or after running `install.py`.

---

## Installation

### Method 1: Using the Installer

Point `install.py` to your local `hermes-agent` directory:

```bash
# Auto-detects local Hermes installation
python install.py

# Or specify the path explicitly
python install.py --target /path/to/hermes-agent
```

The installer will:
1. Create a safe backup in `.deluxe_backup/`.
2. Copy the streaming modules and platform adapter.
3. Apply the gateway integration patches.
4. Run the 34-case unit test suite to verify.

To revert back to stock Hermes:

```bash
python install.py --target /path/to/hermes-agent --uninstall
```

### Method 2: Manual Git Patch

```bash
cd /path/to/hermes-agent
git apply /path/to/Hermes-iMessage-Photon-Deluxe/patches/hermes_all.patch
```

---

## Protocol Tag Reference

| XML Tag | Description | Example |
| :--- | :--- | :--- |
| `<bubble>text</bubble>` | Individual discrete message bubble | `<bubble>On my way!</bubble>` |
| `<tapback>emoji</tapback>` | React to previous message | `<tapback>❤️</tapback>` |
| `<effect type="...">text</effect>` | Fullscreen iMessage effect | `<effect type="confetti">Congrats!</effect>` |
| `<invisible>text</invisible>` | Bubble with invisible ink effect | `<invisible>Secret spoiler</invisible>` |
| `<poll title="...">` | Interactive poll with 1-tap choices | `<poll title="Dinner?"><option>Sushi</option><option>Pizza</option></poll>` |
| `<calendar title="..." start="..." />` | Apple Calendar `.ics` event card | `<calendar title="Flight" start="2026-11-21 09:00" />` |
| `<map query="..." title="..." />` | Apple Maps location card | `<map query="Shanghai Disney Resort" title="Disney" />` |
| `<contact name="..." phone="..." />` | vCard `.vcf` contact card | `<contact name="Alice" phone="+1234567890" />` |
| `<action title="..." shortcut="..." />` | iOS Shortcuts launch link | `<action title="Log Water" shortcut="Hydrate" />` |

---

## Running Tests

Verify the integration inside your Hermes repository:

```bash
python -m unittest tests/gateway/test_photon_bubble_streaming.py
```

---

## License

MIT
