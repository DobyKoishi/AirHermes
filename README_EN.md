# AirHermes

**Conversations, not text walls.**  
[ English ](README_EN.md) • [ 中文说明 ](README.md)

<p align="left">
  <a href="https://github.com/DobyKoishi/AirHermes/releases"><img src="https://img.shields.io/badge/Release-v1.0.0--rc.2-blue?style=flat-square" alt="Release" /></a>
  <a href="#"><img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=flat-square" alt="Python Version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License" /></a>
</p>

<p align="center">
  <img src="assets/airhermes-hero.gif" alt="AirHermes Discrete Multi-Bubble Streaming Motion" width="100%" />
</p>

---

## Key Capabilities

AirHermes brings native Apple messaging UX and declarative system integration to Hermes Agent:

- **Discrete Bubbles & Human Pacing**: Segments long responses at semantic boundaries (Latin & CJK punctuation) with adaptive delays and native typing indicators.
- **Native Polls & Instant Reactions**: Delivers interactive multi-option poll components directly into threads, with contextual Tapbacks and full-screen effects.
- **System Integration & Safe Dispatch**: Generates RFC 5545 calendar invites (`.ics`), verified Apple Maps deep links, and sandboxed rich link preview cards.

<details>
<summary><strong>View Native Interaction Screenshots</strong></summary>

<br/>

- **Native Interactive Polls**: [View full resolution (assets/demo_poll.jpg)](assets/demo_poll.jpg)  
  <a href="assets/demo_poll.jpg"><img src="assets/demo_poll.jpg" alt="Native iMessage Polls" width="460" /></a>

- **Full-Screen Effects & Tapbacks**: [View full resolution (assets/demo_screen_effects.jpg)](assets/demo_screen_effects.jpg)  
  <a href="assets/demo_screen_effects.jpg"><img src="assets/demo_screen_effects.jpg" alt="Screen Effects & Tapbacks" width="460" /></a>

- **Calendar & Apple Maps Integration**: [View full resolution (assets/demo_calendar_maps.jpg)](assets/demo_calendar_maps.jpg)  
  <a href="assets/demo_calendar_maps.jpg"><img src="assets/demo_calendar_maps.jpg" alt="Calendar & Maps" width="460" /></a>

- **Rich Link Previews**: [View full resolution (assets/demo_rich_link.jpg)](assets/demo_rich_link.jpg)  
  <a href="assets/demo_rich_link.jpg"><img src="assets/demo_rich_link.jpg" alt="Rich Media Previews" width="460" /></a>

</details>

---

## Quick Start

AirHermes integrates into Hermes Agent using a tested transactional installer.

### Verified Baselines
AirHermes is verified against specific pinned commits of Hermes Agent:
- Official Upstream: `NousResearch/hermes-agent@242315ce571cde721e717a544cf8ae6c343315cf`
- Development Fork: `hermes-agent-fork@959902f4826b7efce4b79c181d5a2426c08287a0`

### Installation & Diagnostics
```bash
# 1. Sandboxed dry-run (validates files and patch applicability; zero mutations)
python install.py --target /path/to/hermes-agent --dry-run

# 2. Execute transactional installation
python install.py --target /path/to/hermes-agent

# 3. Environment health check
python install.py --target /path/to/hermes-agent --doctor

# 4. Clean uninstall & rollback (reverts target to pre-install state)
python install.py --target /path/to/hermes-agent --uninstall
```

---

## Configuration

Tune streaming flags directly in your Hermes configuration file (`~/.hermes/config.yaml`):

```yaml
photon:
  airhermes:
    bubble_streaming: true        # Enable multi-bubble discrete streaming (default: true)
    bubble_min_interval: 0.85     # Minimum delay between bubbles in seconds (default: 0.85, range: 0.2~5.0)
    bubble_adaptive_pacing: true  # Natural typing delays based on bubble length (default: true)
```

> **Per-Turn Immutability**: Configuration is snapshot at the beginning of each turn. Mid-turn edits will not cause pacing jitter or streaming instability. For full environment variable mappings and parameters, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Interaction Protocol

Upstream models emit lightweight XML tags to trigger native iOS capabilities:

```xml
<!-- 1. Discrete Bubble Segmentation -->
<bubble>Architecture review complete. Generating your calendar invite.</bubble>
<bubble>Invite synced to system calendar. Details attached below.</bubble>

<!-- 2. Native Interactions (Tapback & Polls) -->
<tapback action="love" target="last" />
<poll title="Team Lunch Spot" options="Sushi, Ramen, Cafe" />
```

For full protocol specification, all supported XML tags (`<effect>`, `<calendar>`, `<map>`, `<link>`), and fault-tolerant stripping rules, see [docs/PROTOCOL.md](docs/PROTOCOL.md).

---

## Compatibility & Verification

1. **Pinned Upstream Alignment**: Compatibility is tested and guaranteed for the specific git commits listed above. Unverified future upstream commits may require updated patches.
2. **Live Delivery Notice**: All tests and validations run with hermetic sidecar mocking. Actual live message delivery to iOS devices requires an active, authenticated Photon account.
3. **Security Details**: Refer to [docs/SECURITY.md](docs/SECURITY.md) for attachment quotas, path isolation, and platform filesystem behaviors.

---

## Documentation & License

- [Configuration Reference (`docs/CONFIGURATION.md`)](docs/CONFIGURATION.md)
- [Protocol Specification (`docs/PROTOCOL.md`)](docs/PROTOCOL.md)
- [Security Architecture (`docs/SECURITY.md`)](docs/SECURITY.md)
- [Vector Master Hero (`assets/airhermes-hero.svg`)](assets/airhermes-hero.svg)
- [Releases](https://github.com/DobyKoishi/AirHermes/releases)

Licensed under the [MIT License](LICENSE).
