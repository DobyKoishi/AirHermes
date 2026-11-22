# AirHermes Configuration Reference

AirHermes provides immutable, strictly validated configuration for discrete bubble streaming, adaptive pacing, and native iOS semantic features.

---

## 1. Configuration Sources & Precedence

AirHermes evaluates runtime configuration in the following order of precedence (highest to lowest):

1. **Environment Variables**: Overrides all other configuration sources (prefixed with `AIRHERMES_`).
2. **Hermes Configuration File**: Specified under the `photon:` or `airhermes:` dictionary in `~/.hermes/config.yaml`.
3. **Hardened Factory Defaults**: Default baseline values tuned for stable iMessage delivery.

---

## 2. Configuration Parameters

| Parameter | Environment Variable | Type | Default | Valid Range | Description |
|:---|:---|:---|:---|:---|:---|
| `bubble_streaming` | `AIRHERMES_BUBBLE_STREAMING` | `bool` | `true` | `true`, `false` | Enables discrete multi-bubble streaming. When disabled, the full response emits as a single message. |
| `bubble_min_interval` | `AIRHERMES_BUBBLE_MIN_INTERVAL`<br/>`AIRHERMES_MIN_INTERVAL` | `float` | `0.85` | `0.2` – `5.0` | Minimum delay floor in seconds between consecutive bubbles. Clamped if outside range. |
| `bubble_adaptive_pacing` | `AIRHERMES_BUBBLE_ADAPTIVE_PACING`<br/>`AIRHERMES_ADAPTIVE_PACING` | `bool` | `true` | `true`, `false` | Enables dynamic inter-bubble delay calculation based on character count and typing cadence. |
| `enable_tapbacks` | `AIRHERMES_ENABLE_TAPBACKS` | `bool` | `true` | `true`, `false` | Enables native iMessage Tapback reactions (`<tapback>`). |
| `enable_polls` | `AIRHERMES_ENABLE_POLLS` | `bool` | `true` | `true`, `false` | Enables interactive native polls (`<poll>`). |
| `enable_calendar` | `AIRHERMES_ENABLE_CALENDAR` | `bool` | `true` | `true`, `false` | Enables RFC 5545 compliant `.ics` calendar invite generation (`<calendar>`). |
| `enable_maps` | `AIRHERMES_ENABLE_MAPS` | `bool` | `true` | `true`, `false` | Enables coordinate-verified Apple Maps location deep links (`<map>`). |
| `enable_effects` | `AIRHERMES_ENABLE_EFFECTS` | `bool` | `true` | `true`, `false` | Enables native screen and bubble animation effects (`<effect>`). |

---

## 3. Configuration Example (`config.yaml`)

Add the following section to your Hermes configuration file (`~/.hermes/config.yaml`):

```yaml
photon:
  airhermes:
    bubble_streaming: true
    bubble_min_interval: 0.85
    bubble_adaptive_pacing: true
    enable_tapbacks: true
    enable_polls: true
    enable_calendar: true
    enable_maps: true
    enable_effects: true
```

---

## 4. Per-Turn Immutability

To prevent pacing jitter, race conditions, or configuration drift during an active response:

- At the start of each LLM turn execution (`gateway/run_turn.py`), an immutable `AirHermesConfig` snapshot is instantiated.
- All background consumer and queue tasks (`BubbleStreamConsumer`, `StreamingBubbleQueue`, `ChatPacer`) bind to this snapshot for the entire turn.
- Mid-turn changes to environment variables or `config.yaml` take effect only on subsequent turns.

---

## 5. Defensive Validation & Fallbacks

- **Strict Boolean Parsing**: Boolean values accept `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` (case-insensitive). Invalid values trigger a log warning and fall back to the safe default.
- **Strict Float Validation**: Floating point intervals reject `NaN`, `+Inf`, and `-Inf`. Out-of-bounds numbers outside `[0.2, 5.0]` fall back to default with a warning.
- **Graceful Feature Degradation**: If a feature flag (such as `enable_polls` or `enable_effects`) is disabled, the corresponding XML tag is safely ignored or emitted as regular text without throwing exceptions.
