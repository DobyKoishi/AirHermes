<div align="center">

# 💬 AirHermes
### 为 Hermes Agent 打造的原生 iMessage 离散流式短气泡与 iOS 生态套件

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-orange.svg?style=flat-square)](https://github.com/NousResearch/hermes-agent)
[![Platform](https://img.shields.io/badge/Platform-iMessage%20(Photon)-blue.svg?style=flat-square)](https://photon.sh)
[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-34%20Passed%20(100%25)-success.svg?style=flat-square)](tests/)

<br />

**[ 简体中文 ]** &nbsp;•&nbsp; **[English](README_EN.md)**

<br />

> 告别传统 AI 机器人“憋大招几十秒、一次性吐出一大坨万字排版长文”的机械人质感。  
> 还原真人发微信、发 iMessage 的即时短句、拟人思考与舒适的打字呼吸感。

</div>

---

## ⚡️ 为什么需要它？(痛点对比)

| 交互维度 | 传统 AI 聊天机器人 🤖 | AirHermes 进阶体验 📱 |
| :--- | :--- | :--- |
| **首句响应** | 深度思考或调用工具时，界面静止 5~15 秒，如同死机 | **1 秒内秒弹口语化即时气泡**（如“让我想想哈”、“收到！我来看下”） |
| **消息形态** | 一次性喷出数千字 Markdown 粗体、项目符号清单 | **离散短气泡逐条弹出**，单条 1~2 句话，自适应阅读停顿节奏 |
| **耗时操作** | 搜索网络/查日程时在后台静默假死 | **工具执行心跳**：查库/搜网页超过 2.5s 自动同步动态进展 |
| **情绪反馈** | 只能回复文字，无法表态 | **语义 Tapback 秒回**：支持零文本纯表情点赞/哈哈/爱心原生表态 |
| **原生卡片** | 复制粘贴纯文本，手动输入日程与通讯录 | **原生 iOS 卡片**：可点选投票、.ics 日历、.vcf 名片、Apple 地图一键入库 |
| **氛围感** | 冷冰冰的纯文本 | **全屏 iMessage 特效**：支持大烟花、激光、气球、隐形墨水动效 |

---

## 📐 系统架构链路 (Architecture)

```text
       LLM Incremental Delta Stream (Token 流)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│                   BubbleParser                   │
│   • 严格标签语法树 (<bubble>, <tapback>, <poll> 等) │
│   • 跨气泡代码块围栏 (Code Fence) 自动平衡保护      │
│   • CJK 中文标点 CommonMark 边界空格自适应修复    │
│   • 无标签纯文本智能段落回退 (Paragraph Fallback)   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│              StreamingBubbleQueue                │
│   • 5 态生命周期管理 (Queued -> Sending -> Sent)  │
│   • 400ms 人类阅读节奏节流器 (Adaptive Pacer)    │
│   • 断网延迟保护、迟到 ACK 对账与熔断器机制        │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│             Photon Platform Adapter              │
│   • 智能分发：纯文本 / 投票 / 特效 / 文件附件     │
│   • Node Sidecar 指数退避重试与 HEIC 原生转码     │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
           用户 iPhone / Mac 原生 iMessage
```

---

## 📁 目录结构 (Directory Structure)

```text
AirHermes/
├── gateway/
│   ├── bubble_parser.py           # 离散多标签气泡解析器与段落回退引擎
│   ├── bubble_queue.py            # 5 态生命周期队列与抗断网自适应节奏引擎
│   └── bubble_stream_consumer.py  # Hermes 网关流式 Consumer 桥接器
├── plugins/platforms/photon/
│   ├── adapter.py                 # Photon 平台适配器（原生 iOS 动效/投票/表态/HEIC）
│   └── sidecar/
│       ├── index.mjs              # 强化指数退避重试的 Node Sidecar
│       ├── package.json
│       └── patch-spectrum-poll.mjs# spectrum-ts 投票鲁棒性热补丁
├── patches/                       # 对应 Hermes Agent 核心挂钩的标准化补丁
│   ├── hermes_all.patch           # 全量单文件补丁
│   ├── run_turn.patch
│   ├── run_turn_runner.patch
│   └── session.patch
├── tests/
│   └── test_photon_bubble_streaming.py  # 34 项完整自动化测试套件
├── install.py                     # 一键智能安装/验证/卸载脚本（带自动备份）
├── .gitignore
├── README.md                      # 中文说明文档（默认）
└── README_EN.md                   # English Documentation
```

---

## 📋 原生 iOS 协议标签速查表

在你的提示词或 Agent 回复中，可直接输出以下轻量语义标签：

| XML 协议标签 | 功能说明 | 渲染效果 / 示例 |
| :--- | :--- | :--- |
| `<bubble>文本</bubble>` | 离散独立气泡 | `<bubble>下班去吃火锅不？</bubble>` |
| `<tapback>emoji</tapback>` | 原生 iMessage 表态 | `<tapback>❤️</tapback>`（支持 ❤️ 👍 👎 😆 ‼️ ❓） |
| `<poll title="...">` | 原生可点选投票卡片 | `<poll title="周末去哪？"><option>海边</option><option>露营</option></poll>` |
| `<calendar title="..." start="..." />` | 原生 Apple 日历卡片 | `<calendar title="项目周会" start="2026-11-21 14:00" />`（生成干净 .ics） |
| `<map name="..." coordinate="..." address="..." />` | 原生 Apple 地图卡片（带即时视网膜预览） | `<map name="旺角一兰拉面" coordinate="22.3193,114.1694" address="香港九龙旺角洗衣街88号" />` |
| `<contact name="..." phone="..." />` | 原生通讯录名片 | `<contact name="张三" phone="13800000000" />`（生成标准 .vcf） |
| `<effect type="...">文本</effect>` | 全屏 iMessage 特效 | `<effect type="fireworks">考试全过！🎉</effect>` |
| `<invisible>文本</invisible>` | 隐形墨水气泡 | `<invisible>刮开看惊喜答案</invisible>` |
| `<action title="..." shortcut="..." />` | 快捷指令深层跳转 | `<action title="记一笔账" shortcut="记账小助手" />` |

---

## 🛠 前置条件 (Prerequisites)

AirHermes 扩展基于 Hermes Agent 官方 Photon 驱动打造：

1. 本地已安装 [Hermes Agent](https://github.com/NousResearch/hermes-agent)。
2. 配对 iMessage 账号通道：
   - **已有 Photon 账号**：直接运行下方的安装命令，启动 `hermes gateway` 即可直接享受 Deluxe 体验。
   - **全新配置**：需在 Hermes 中执行一次 `hermes photon setup` 扫码配对手机号/Apple ID。

---

## 🚀 极速安装与部署

### 途径 A：使用自动化一键安装器（推荐）

```bash
# 克隆本扩展仓库
git clone https://github.com/<your-username>/AirHermes.git
cd AirHermes

# 自动定位本地 Hermes 并一键注入安装（自动备份原文件）
python install.py

# 启动 Hermes Gateway，尽情体验！
hermes gateway
```

> **提示**：如需一键无残留还原至官方原版，只需执行：
> ```bash
> python install.py --uninstall
> ```

### 途径 B：使用 Git 标准补丁

```bash
cd /path/to/hermes-agent
git apply /path/to/AirHermes/patches/hermes_all.patch
```

---

## 🧪 单元测试验证

项目包含 34 项针对流式断句、代码块防截断、重试容错与时序防并发的自动化测试：

```bash
python -m unittest tests/gateway/test_photon_bubble_streaming.py
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
