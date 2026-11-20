<div align="center">

# 💬 AirHermes
### Discrete Multi-Bubble Streaming & Native iOS Ecosystem Suite for Hermes Agent

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-orange.svg?style=flat-square)](https://github.com/NousResearch/hermes-agent)
[![Platform](https://img.shields.io/badge/Platform-iMessage%20(Photon)-blue.svg?style=flat-square)](https://photon.sh)
[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-34%20Passed%20(100%25)-success.svg?style=flat-square)](tests/)

<br />

**[ [简体中文](README.md) ]** &nbsp;•&nbsp; **[ English ]**

<br />

> Say goodbye to robotic bots freezing for 15 seconds before dumping an overwhelming wall of text.  
> Enjoy conversational pacing, instant feedback, and natural cognitive breathing room directly on iMessage.

</div>

---

## ⚡️ Why AirHermes? (Experience Comparison)

| Dimension | Standard AI Chatbot 🤖 | AirHermes Experience 📱 |
| :--- | :--- | :--- |
| **First Response** | Freezes for 5–15 seconds during reasoning or tool calls | **Instant spoken reaction within 1s** (e.g. "Let me check that for you!") |
| **Message Shape** | Monolithic essay dump with rigid bullet points | **Discrete short bubbles popping up progressively**, 1–2 sentences each |
| **Long Tasks** | Appears frozen/unresponsive during web search or code exec | **Tool Heartbeats**: Automatically sends progress hints if a tool exceeds 2.5s |
| **Emotional Feedback** | Text-only replies | **Semantic Tapbacks**: Reacts with ❤️, 👍, 👎, 😆, ‼️, ❓ (zero-text replies supported) |
| **Native Rich Cards** | Plain text requiring manual copy-pasting | **Native iOS Cards**: 1-tap polls, `.ics` calendar events, `.vcf` contacts, Apple Maps |
| **Visual Effects** | Flat static text | **Fullscreen iMessage Effects**: Confetti, fireworks, lasers, balloons, invisible ink |

---

## 📐 Architecture Flow

```text
       LLM Incremental Delta Stream (Token stream)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│                   BubbleParser                   │
│   • Semantic XML tag parsing (<bubble>, <poll>)  │
│   • Cross-bubble Markdown code fence balancing   │
│   • CJK delimiter spacing auto-normalization     │
│   • Plain text paragraph fallback splitting      │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│              StreamingBubbleQueue                │
│   • 5-State lifecycle tracking (Queued -> Sent)  │
│   • 400ms human cognitive pacing (Pacer)         │
│   • Late ACK reconciliation & circuit breaking   │
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
             User iPhone / Mac iMessage
```

---

## 📁 Directory Structure

```text
AirHermes/
├── gateway/
│   ├── bubble_parser.py           # Streaming delimiter parser with paragraph fallback
│   ├── bubble_queue.py            # 5-state lifecycle queue and pacing engine
│   └── bubble_stream_consumer.py  # Gateway streaming consumer bridge
├── plugins/platforms/photon/
│   ├── adapter.py                 # Photon platform adapter with native iOS features
│   └── sidecar/
│       ├── index.mjs              # Sidecar with exponential backoff on inbound media
│       ├── package.json
│       └── patch-spectrum-poll.mjs# spectrum-ts poll robustness patch
├── patches/                       # Unified diffs for Hermes Agent core hooks
│   ├── hermes_all.patch           # All-in-one patch
│   ├── run_turn.patch
│   ├── run_turn_runner.patch
│   └── session.patch
├── tests/
│   └── test_photon_bubble_streaming.py  # Full 34-case automated test suite
├── install.py                     # One-click installer / patch manager with auto-backup
├── .gitignore
├── README.md                      # Chinese Documentation (Default)
└── README_EN.md                   # English Documentation
```

---

## 📋 XML Protocol Tag Reference

Output these lightweight tags in your agent's system prompt or tool responses:

| XML Tag | Description | Example / Rendered Outcome |
| :--- | :--- | :--- |
| `<bubble>text</bubble>` | Individual discrete message bubble | `<bubble>On my way!</bubble>` |
| `<tapback>emoji</tapback>` | Native Apple Tapback reaction | `<tapback>❤️</tapback>` (supports ❤️ 👍 👎 😆 ‼️ ❓) |
| `<poll title="...">` | Interactive 1-tap poll card | `<poll title="Lunch?"><option>Sushi</option><option>Tacos</option></poll>` |
| `<calendar title="..." start="..." />` | Native Apple Calendar event | `<calendar title="Flight" start="2026-11-21 09:00" />` (clean `.ics`) |
| `<map query="..." title="..." />` | Native Apple Maps location card | `<map query="Shanghai Disney Resort" title="Disney" />` |
| `<contact name="..." phone="..." />` | Native vCard contact card | `<contact name="Alice" phone="+1234567890" />` (clean `.vcf`) |
| `<effect type="...">text</effect>` | Fullscreen iMessage effect | `<effect type="confetti">You passed! 🎉</effect>` |
| `<invisible>text</invisible>` | Invisible ink bubble effect | `<invisible>Secret spoiler</invisible>` |
| `<action title="..." shortcut="..." />` | iOS Shortcuts deep link | `<action title="Log Water" shortcut="Hydrate" />` |

---

## 🛠 Prerequisites

AirHermes builds upon Hermes Agent's official Photon integration:

1. A working [Hermes Agent](https://github.com/NousResearch/hermes-agent) repository.
2. An active iMessage Photon channel:
   - **If you already use Photon**: simply run the installer below and start `hermes gateway`.
   - **Fresh setup**: run `hermes photon setup` once to link your phone number / Apple ID.

---

## 🚀 Quickstart & Installation

### Option A: Using the Automated Installer (Recommended)

```bash
# Clone this repository
git clone https://github.com/<your-username>/AirHermes.git
cd AirHermes

# Auto-detects local Hermes and injects the suite (auto-backup included)
python install.py

# Start your gateway
hermes gateway
```

> **Note**: To cleanly restore your Hermes installation back to stock at any time:
> ```bash
> python install.py --uninstall
> ```

### Option B: Using Git Patch

```bash
cd /path/to/hermes-agent
git apply /path/to/AirHermes/patches/hermes_all.patch
```

---

## 🧪 Test Verification

Run the comprehensive 34-case test suite to verify code fence balancing, pacing, and edge cases:

```bash
python -m unittest tests/gateway/test_photon_bubble_streaming.py
```

---

## 📄 License

[MIT License](LICENSE)
