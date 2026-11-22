# AirHermes Interaction Protocol Specification

AirHermes extends Hermes Agent with an XML-based tag protocol that instructs the Photon adapter and native sidecars to execute Apple iMessage platform capabilities.

---

## 1. Discrete Bubble Streaming

When `bubble_streaming` is enabled (default: `true`), the agent emits response fragments demarcated by `<bubble>` tags or automatic sentence boundaries:

```xml
<bubble>
Got your query! Let me pull the calendar records.
</bubble>
<bubble>
Found the event: Team Sync at 3:00 PM tomorrow in Meeting Room B.
</bubble>
```

### Punctuation & CJK Splitting
- **Latin / Western**: Splits on sentence terminators (`. `, `! `, `? `) followed by whitespace.
- **CJK (Chinese, Japanese, Korean)**: Splits on full-width punctuation marks (`。`, `！`, `？`) and multi-char ellipsis (`……`).
- **Pacing Engine**: When `bubble_adaptive_pacing` is enabled, computes delivery delays dynamically between `bubble_min_interval` (default 0.85s) and a 4.5s ceiling based on bubble character count, reading time, and typing cadence. Inter-bubble pauses exceeding 0.45s automatically pulse native typing indicators.

---

## 2. Native iMessage Interactions

### A. Polls (`<poll>`)
Renders native interactive multi-option polls in group and direct chats:

```xml
<poll title="Preferred meeting time?" options="10:00 AM, 2:00 PM, 4:30 PM" />
```

### B. Tapback Reactions (`<tapback>`)
Applies native iOS message reactions to the user's incoming message or preceding bubble:

```xml
<tapback action="love" target="last" />
```

- Supported actions: `love`, `like`, `dislike`, `laugh`, `emphasize`, `question`.

### C. Screen & Bubble Effects (`<effect>`)
Triggers native Apple full-screen or bubble animation effects:

```xml
<bubble>Happy birthday! Here's to another wonderful year!</bubble>
<effect name="balloons" />
```

- **Screen Effects**: `balloons`, `confetti`, `lasers`, `fireworks`, `shooting-star`, `celebration`.
- **Bubble Effects**: `slam`, `loud`, `gentle`, `invisible-ink`.

### D. Calendar Events (`<calendar>`)
Generates RFC 5545 compliant `.ics` calendar invites delivered as native attachments:

```xml
<calendar title="Project Review" start="2026-11-25T14:00:00" end="2026-11-25T15:00:00" location="Design Lab" summary="Q4 Architecture & Security Review" />
```

- **RFC 5545 Compliance**: UTF-8 encoding without BOM, CRLF line endings, 75-octet content line folding, standard `SUMMARY` property.

### E. Apple Maps Locations (`<map>`)
Emits validated Apple Maps deep links with native rich preview metadata:

```xml
<map query="Apple Park, Cupertino, CA" lat="37.3346" lon="-122.0090" label="Apple Park" />
```

### F. Contacts (`<contact>`)
Generates compliant vCard (`.vcf`) files delivered as native attachments:

```xml
<contact name="Hermes Agent" phone="+1-800-555-0199" email="agent@hermes.local" />
```

---

## 3. Graceful Fallback & Protocol Sanitization

If an XML tag is incomplete, malformed, or emitted by an upstream model without required attributes:

1. **Tag Stripping**: Raw protocol tags are never leaked as plain text to recipients.
2. **Text Preservation**: Inner text content within malformed tags is safely preserved and emitted as regular bubbles.
3. **Sidecar Safety**: Node.js sidecar validation rejects invalid attributes before sending payloads to the Apple Messages service.
