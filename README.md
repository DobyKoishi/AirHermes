<div align="center">

# AirHermes

### 为 Hermes Agent 打造的原生 iMessage 离散气泡流与 iOS 交互套件

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-orange.svg?style=flat-square)](https://github.com/NousResearch/hermes-agent)
[![Platform](https://img.shields.io/badge/Platform-iMessage%20(Photon)-blue.svg?style=flat-square)](https://photon.sh)
[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

<br />

**简体中文** &nbsp;|&nbsp; [English](README_EN.md)

</div>

---

Hermes Agent 原生的 Photon 通道默认将整段响应一次性发送。在手机或 Mac 端使用 iMessage 时，单条长消息既缺少对话交互的即时反馈，也无法调用 iOS 系统的原生富文本卡片。

AirHermes 是一个面向 Hermes Agent 的扩展套件，专为 iMessage (Photon) 运行环境设计。它将大模型回复切分为离散的短气泡，引入拟人化的打字节奏，并全面打通 iOS 原生生态协议 —— 包括可点选的投票卡片、Apple 日历事件、Apple Maps 地标卡片、网页富媒体展开、全屏动效与 Tapback 表态。

---

## 演示效果

| 交互式原生投票 (`<poll>`) | 日历日程与 Apple Maps 地标 (`.ics` / `/place`) |
| :---: | :---: |
| <img src="assets/demo_poll.jpg" width="380" alt="iMessage Poll Demo" /> | <img src="assets/demo_calendar_maps.jpg" width="380" alt="Calendar and Maps Demo" /> |
| **富媒体链接展开 (LPLinkView) 与上下文记忆** | **全屏动效 (Balloons) 与语义 Tapback 表态** |
| <img src="assets/demo_rich_link.jpg" width="380" alt="Rich Link Preview Demo" /> | <img src="assets/demo_screen_effects.jpg" width="380" alt="Screen Effects Demo" /> |

---

## 体验对比

| 交互维度 | 默认表现 | AirHermes 优化 |
| :--- | :--- | :--- |
| **首字响应** | 深度思考或调用工具期间静止数秒，界面无响应 | 首句在 1 秒内给出即时口语反馈（如“收到，我来看下”），随后渐进推进 |
| **消息形态** | 一次性推送长篇 Markdown 排版文本 | 自动切分为 1~2 句话的离散短气泡，降低手机端长文本阅读压迫感 |
| **打字节奏** | 多条消息瞬间并发轰炸，触发通知堆叠 | 基于句长与标点提供拟人自适应间隔缓冲（基准 0.85s，动态 0.35s ~ 3.5s+），还原真实打字节奏 |
| **日程管理** | 纯文本时间信息，需手动复制录入 | 自动生成标准 RFC 5545 规范的 `.ics` 原生卡片，点击即可一键存入 Apple 日历 |
| **地理位置** | 纯文本地名或无预览链接 | 生成合法校验的 Apple Maps Unified Place URL，交由系统解析地标卡片，点击一键导航 |
| **互动测验** | 纯文本选择题 | 调用 iMessage 原生投票系统，支持多选项点选与头像标记 |
| **情绪互动** | 仅能输出常规文本 | 支持发送原生 Tapback（❤️、👍 等），可根据语境触发全屏气球、烟花、激光等动效 |

---

## 核心特性

- **离散气泡流式切分 (Bubble Parser)**  
  支持 `<bubble>` 标签式切分与无标签智能段落回退（Paragraph Fallback）。内置跨气泡代码块围栏状态机，防止代码块在流式切分时语法失衡或标记泄漏；自动修复中英文混排常见标点空格。

- **拟人化节奏队列 (Adaptive Pacer Queue)**  
  提供 5 态生命周期管理（Queued → Sending → Sent），在多气泡发送时实施基于语意长度的轻量节奏缓冲，兼顾即时性与阅读舒适度。包含断网重连保护与迟到 ACK 校验。

- **Apple Maps 统一地标规范 (/place)**  
  采用 Apple 官方最新的 Unified Place URL 规范 (`/place?coordinate=...&name=...&map=explore`)。校验合规地图链接，由客户端原生渲染地标微缩卡片；内置主流商圈城市坐标保底表，确保随时稳定触发卡片预览。

- **原生日历事件 (.ics)**  
  严格遵循 RFC 5545 规范，采用 75 字节安全折行、CRLF 行尾符与 UTF-8 无 BOM 编码，并彻底防御注入攻击。

- **交互式原生投票 (<poll>)**  
  在 Photon 驱动层打通 spectrum-ts 投票协议，无需第三方小程序或 Webview，直接在 iMessage 对话流内渲染原生选项与统计计数。

- **全屏系统动效与轻量表态**  
  支持 iMessage 原生全屏特效（气球、烟花、激光、彩带等）以及隐形墨水动效；支持不附带文本的纯 Tapback 表态。

---

## 协议标签规范

在系统提示词或自定义技能中，可直接输出以下轻量语义标签：

| 标签格式 | 功能说明 | 示例 |
| :--- | :--- | :--- |
| `<bubble>文本</bubble>` | 独立消息气泡 | `<bubble>下班去吃火锅不？</bubble>` |
| `<tapback>emoji</tapback>` | 原生 iMessage 表态 | `<tapback>❤️</tapback>`（支持 ❤️ 👍 👎 😆 ‼️ ❓） |
| `<poll title="...">` | 原生点选投票卡片 | `<poll title="周末去哪？"><option>海边</option><option>露营</option></poll>` |
| `<calendar title="..." start="..." />` | 原生 Apple 日历卡片 | `<calendar title="项目周会" start="2026-11-21 14:00" />` |
| `<map name="..." coordinate="..." />` | Apple Maps 地标卡片 | `<map name="旺角一兰拉面" coordinate="22.3193,114.1694" address="香港九龙旺角洗衣街88号" />` |
| `<contact name="..." phone="..." />` | 原生通讯录名片 (.vcf) | `<contact name="张三" phone="13800000000" />` |
| `<effect type="...">文本</effect>` | 全屏动效 | `<effect type="balloons">恭喜拿到了心仪的 offer！🎉</effect>` |
| `<invisible>文本</invisible>` | 隐形墨水气泡 | `<invisible>刮开查看答案</invisible>` |
| `<action title="..." shortcut="..." />` | 快捷指令跳转 | `<action title="记一笔账" shortcut="记账小助手" />` |

---

## 系统架构

```text
       LLM Incremental Delta Stream (Token 流)
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│                   BubbleParser                   │
│   • 严格标签语法树 (<bubble>, <poll>, <map> 等)    │
│   • 跨气泡代码块围栏 (Code Fence) 自动平衡保护      │
│   • Apple Maps Unified Place 坐标与地名自动组装   │
│   • 无标签纯文本智能段落回退 (Paragraph Fallback)   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│              StreamingBubbleQueue                │
│   • 5 态生命周期管理 (Queued -> Sending -> Sent)  │
│   • 基于句长的自适应阅读节奏节流器 (Adaptive Pacer) │
│   • 迟到 ACK 对账与断网保护机制                     │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│             Photon Platform Adapter              │
│   • 载荷分发：纯文本 / 投票 / 全屏动效 / 附件文件  │
│   • Node Sidecar 指数退避重试与 HEIC 原生转码     │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
           用户 iPhone / iPad / Mac iMessage
```

---

## 安装与配置

### 前置要求

1. 本地已安装 [Hermes Agent](https://github.com/NousResearch/hermes-agent)。
2. 已配置 iMessage (Photon) 账号：
   - 首次使用需在终端运行 `hermes photon setup` 扫码配对 Apple ID / 手机号。
   - 若本地已正常运行 Photon，可直接进行下一步。

### 快速安装与诊断

```bash
git clone https://github.com/DobyKoishi/AirHermes.git
cd AirHermes

# 1. 运行环境健康体检与兼容性诊断（可选）
python install.py --doctor

# 2. 沙盒模拟试运行，确认补丁与文件完全兼容（不修改任何文件）
python install.py --dry-run

# 3. 执行事务化原子安装（全自动备份、哈希校验、失败自动回滚）
python install.py
```

安装完成后，重启 Hermes 网关服务生效：

```bash
hermes gateway restart
```

### 卸载与安全恢复

如需完全恢复为 Hermes Agent 安装前的原始代码：

```bash
# 智能比对 SHA-256 哈希，安全还原被修改文件，清除注入模块
python install.py --uninstall

# 若安装后曾手动修改过文件，可加 --force 强制覆盖（会自动额外留存冲突备份）
# python install.py --uninstall --force

hermes gateway restart
```

### 配置选项与特性开关 (Feature Flags)

AirHermes 提供零侵入的配置系统。所有特性在默认状态下全部开启，完全保持原汁原味的最佳多气泡拟人流式体验。

你可以在 Hermes 的配置文件 `~/.hermes/config.yaml`（`platforms.photon` 节点下）自定义设置，亦可通过环境变量全局覆盖。

#### 1. 核心配置项索引

| 配置键名 (YAML) | 环境变量 (ENV) | 默认值 | 取值范围 / 说明 | 特性禁用后的平滑回退行为 |
| :--- | :--- | :---: | :--- | :--- |
| `bubble_streaming` | `AIRHERMES_BUBBLE_STREAMING` | `true` | `bool`: `true` / `false` | 完全跳过 `BubbleStreamConsumer`，直通 Hermes 原生单消息最终交付通道 |
| `bubble_min_interval` | `AIRHERMES_BUBBLE_MIN_INTERVAL` | `0.85` | `float`: `[0.2, 5.0]` (秒) | 气泡发送基础间隔/底线节奏，非法值或非有限数 (NaN/Inf) 自动回退默认值并告警 |
| `bubble_adaptive_pacing` | `AIRHERMES_BUBBLE_ADAPTIVE_PACING` | `true` | `bool`: `true` / `false` | 拟人认知自适应节奏开关；若关闭，固定使用 `bubble_min_interval` 间隔 |
| `enable_tapbacks` | `AIRHERMES_ENABLE_TAPBACKS` | `true` | `bool`: `true` / `false` | 原生轻触表态/反应；若关闭，不调用 Native Reaction API 也不发送表情气泡 |
| `enable_polls` | `AIRHERMES_ENABLE_POLLS` | `true` | `bool`: `true` / `false` | 原生交互式投票卡片；若关闭，平滑降级为格式化纯文本选项列表 |
| `enable_calendar` | `AIRHERMES_ENABLE_CALENDAR` | `true` | `bool`: `true` / `false` | 原生 Apple Calendar (.ics)；若关闭，平滑降级为可读日程详情文本 |
| `enable_maps` | `AIRHERMES_ENABLE_MAPS` | `true` | `bool`: `true` / `false` | 原生 Apple Maps 定位卡片；若关闭，降级为包含官方 Apple Maps 链接的可读文本 |
| `enable_effects` | `AIRHERMES_ENABLE_EFFECTS` | `true` | `bool`: `true` / `false` | 原生 iOS 全屏视效/气泡动效；若关闭，剥除动效指令仅交付纯文本消息 |

#### 2. YAML 配置示例 (`~/.hermes/config.yaml`)

```yaml
platforms:
  photon:
    project_id: "your_project_id"
    project_secret: "your_project_secret"
    # AirHermes 配置项（直接置于 platforms.photon 节点下）
    bubble_streaming: true
    bubble_min_interval: 0.85
    bubble_adaptive_pacing: true
    enable_tapbacks: true
    enable_polls: true
    enable_calendar: true
    enable_maps: true
    enable_effects: true
```

#### 3. 环境变量覆盖规则

优先级：`AIRHERMES_*` 环境变量 > `config.yaml` (`platforms.photon`) > 默认值。

```bash
# 示例：临时全局关闭投票与日程附件卡片
export AIRHERMES_ENABLE_POLLS=false
export AIRHERMES_ENABLE_CALENDAR=false
```

#### 4. 严苛类型校验与运行安全保障

- **严格布尔解析**：仅识别 `true`/`false`/`1`/`0`/`yes`/`no`/`on`/`off`（不区分大小写）。传入未知类型或非法字符串将输出 Warning 日志并安全回退到默认值。
- **数值边界保护**：拒绝 `NaN`、`+Inf`、`-Inf` 以及超出 `[0.2, 5.0]` 范围的异常数值。
- **Turn 级别不可变快照**：每次对话轮次建立独立的只读不可变快照（`frozen=True`），杜绝并发或运行时环境变量变更引发的半状态不一致。
- **隐私与凭据隔离**：配置解析与回退日志绝不包含用户会话私密文本或认证密钥。

---

## 目录结构

```text
AirHermes/
├── .github/workflows/             # GitHub Actions 自动化 CI 流程
│   ├── ci.yml                     # 跨平台多 Python 版本单元测试与 Lint 工作流
│   └── integration.yml            # 上游 Hermes Agent 联动集成测试工作流（可选手动触发）
├── assets/                        # 演示实测截图
│   ├── demo_poll.jpg
│   ├── demo_calendar_maps.jpg
│   ├── demo_rich_link.jpg
│   └── demo_screen_effects.jpg
├── gateway/
│   ├── airhermes_config.py        # 特性开关与不可变配置系统（YAML/ENV 双层加载）
│   ├── bubble_parser.py           # 离散多标签气泡解析器与段落回退引擎
│   ├── bubble_queue.py            # 5 态生命周期队列与抗断网自适应节奏引擎
│   └── bubble_stream_consumer.py  # Hermes 网关流式 Consumer 桥接器
├── plugins/platforms/photon/
│   ├── adapter.py                 # Photon 平台适配器（原生 iOS 动效/投票/表态）
│   └── sidecar/
│       ├── index.mjs              # 强化指数退避重试的 Node Sidecar
│       └── patch-spectrum-poll.mjs# spectrum-ts 投票鲁棒性补丁
├── patches/                       # 针对 Hermes 核心网关的标准 Git Patch
│   ├── hermes_all.patch           # 全量单文件补丁
│   ├── run_turn.patch
│   ├── run_turn_runner.patch
│   └── session.patch
├── tests/
│   ├── test_installer.py          # 安装器事务回滚、预写日志、崩溃恢复与沙箱测试套件
│   └── test_photon_bubble_streaming.py  # 气泡解析器、自适应节奏队列与流式生命周期测试套件
├── install.py                     # 事务化原子安装、健康诊断与安全卸载工具
├── README.md                      # 中文说明文档（默认）
└── README_EN.md                   # 英文说明文档
```

---

## 附件投递与安全架构 (Phase 5 Security & Compatibility)

AirHermes 在 Phase 5 引入了严格的**本地沙箱与声明式附件安全边界（Attachment Security & Lifecycle Containment）**，以防止不可信的模型输出或恶意指令泄露宿主敏感文件。

### 1. 行为变动与兼容性说明 (Behavioral Changes)
> [!IMPORTANT]
> 以下改动属于有意为之的安全加固边界，改变了部分原生无鉴权直接派发行为，并非完全向后兼容：

- **宿主裸路径提取中和**：`PhotonAdapter.extract_local_files()` 默认返回 `([], content)`。大模型回复中直接出现的宿主绝对路径或 Windows 盘符路径（如 `C:\docs\secret.pdf` 或 `/etc/hosts`）**不会**再被自动扫描提取并发送为附件。
- **直接适配器调用严格鉴权**：直接调用 `PhotonAdapter.send_document()`、`send_image_file()`、`send_voice()` 或 `send_video()` 时，目标路径必须是已在 `AttachmentRegistry` 中登记并暂存的受信任沙箱路径。直接传入未授权的任意宿主路径将被立即拒绝（返回 `SendResult(success=False, error="Attachment not authorized: ...")`），杜绝隐式自动授权回退。
- **支持的工作流与迁移方案**：
  - **内置生成器（继续全自动工作）**：`<calendar>`、`<contact>` 等原生卡片生成器已打通受信任沙箱，自动生成带有 producer 凭证的强类型动作并由适配器安全派发。
  - **网络图片**：`send_image(image_url)` 经过 URL 缓存下载后继续正常工作。
  - **自定义工具与外部脚本迁移**：若工具需要发送宿主文件，必须先显式调用：
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

### 2. 生命周期与取消防护 (Lifecycle & Bounded Quarantine)
- **取消与未知状态隔离**：当异步任务在原生发送中途被取消或超时，附件状态进入 `OUTCOME_UNKNOWN` 并开启 120 秒隔离保护窗口。在当前 Turn 结束时，文件**不会**被立即删除，确保外部 Node.js Sidecar 能安全完成对磁盘文件的读取和传输。
- **严禁自动重试**：处于 `OUTCOME_UNKNOWN` 的附件严禁再次兑现或重试，防止网络延迟导致的重复投递。
- **单次使用（Single-Use）**：每个暂存附件经由 Sidecar 确认送达（`SUCCEEDED`）后立即失效，防止跨 Chat 或跨 Turn 重放。

### 3. 跨进程隔离与崩溃恢复 (Crash Recovery & Orphan Cleanup)
- 暂存目录统一采用 `proc_<pid>_<opaque_token>` 格式隔离。
- `recover_abandoned_staging` 在扫描孤儿目录时，通过系统 API 实时验证属主 PID 存活性（Windows `OpenProcess`/Linux `kill(pid, 0)`），**绝对不删除其他正在运行中的进程的附件文件**。
- 严禁跟随符号链接（Symlinks）或 NTFS Junctions。

### 4. Windows 平台文件系统局限性 (Windows Filesystem Security Limitations)
- 在 Windows 环境下，`os.chmod(0o700)` 仅修改只读属性，不生效 NTFS DACL 权限控制。
- 默认 `%TEMP%` 暂存根目录依托 Windows 用户配置文件夹的继承 ACL 实现多用户隔离。
- **边界说明**：同一 Windows 用户账户下运行的其他进程具备等同的文件访问权限。AirHermes 防护边界针对的是 LLM 文本注入与未授权跨会话调用，不声称抵御同用户权限下已被完全攻破的恶意进程的直接内存或磁盘探测。

---

## 测试与 CI 架构

AirHermes 拥有独立且完备的跨平台自动化测试体系。

### 1. 本地独立单元测试 (无需安装 Hermes)

AirHermes 核心解析与队列算法已全面解耦，无需安装 Hermes Agent 即可在任何标准 Python 3.11+ 环境下直接运行：

```bash
# 运行安装器事务回滚与故障恢复测试（16 个测试用例）
python -m unittest -v tests/test_installer.py

# 运行离散气泡流、队列节奏与生命周期纯单元测试（62 个测试用例：59 项通过，3 项上游联动用例需 Hermes 环境）
python -m unittest -v tests/test_photon_bubble_streaming.py

# 或自动发现并运行全部独立单元测试（143 个用例：140 通过，3 跳过）
python -m unittest discover -s tests -p "test_*.py"

# 代码规范与语法编译检查
ruff check .
python -m py_compile install.py gateway/*.py tests/*.py
```

### 2. 真实上游 Hermes 集成测试

测试依赖于上游 Hermes 内部类（如 `PhotonAdapter` 属性、`TurnRunner` 工具提示）的集成测试：

```bash
# 方式 A：指定 Hermes 路径运行完整 45 项测试（包含 3 项上游联动用例）
PYTHONPATH="/path/to/hermes-agent:." python -m unittest -v tests/test_photon_bubble_streaming.py

# 方式 B：通过安装器的自动验证命令在已安装目标环境中运行
python install.py --verify --target /path/to/hermes-agent
```

### 3. CI 持续集成策略

- **矩阵覆盖**：在 GitHub Actions 中自动运行于 `Ubuntu`、`macOS`、`Windows` 以及 Python `3.11`、`3.12`。
- **离线与零依赖**：基础 CI 严格保证纯离线、零外部凭证、零私有服务依赖即可 100% 运行，杜绝因为外部 iMessage 账号或 Photon 服务故障导致构建不稳定。
- **可选上游联动**：提供 `.github/workflows/integration.yml`，支持通过 GitHub Actions `workflow_dispatch` 针对指定的上游 Hermes 版本自动拉取、安装并回归全部集成用例。

### 4. 已知局限性说明

- **平台真实连通性**：CI 与单元测试证明了气泡协议状态机、排版算法与文件系统事务的正确性；但真实的 iMessage 富文本卡片渲染最终依赖于 macOS 系统的 APNs 通信与 Photon 服务的实际登录状态。
- **极端断电一致性**：文件系统事务通过原子替换与预写日志保证崩溃恢复能力，但未执行强同步刷盘（fsync 屏障），在极端瞬间断电情况下不声称完全免受宿主系统元数据缓存延迟影响。

---

## 开源协议

本项目采用 [MIT License](LICENSE) 开源。
