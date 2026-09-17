<div align="center">

**中文** · [English](./README.en.md)

# 🧰 Baichuan Skills

#### 白川开源的 AI Skills 合集 — 个人操作系统 + 人生决策分析

[![License](https://img.shields.io/badge/License-MIT-3B82F6?style=for-the-badge)](./LICENSE)
[![Skills](https://img.shields.io/badge/Skills-3-10B981?style=for-the-badge)](#-skills)

![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-D97706?style=flat-square&logo=anthropic&logoColor=white)

</div>

都是自己实际在用的东西，跑通了才搬出来开源。

- **Skills** — Agent 能直接加载的结构化指令集，Claude Code 等工具可直接使用
- **Connectors** — 可直接部署的平台连接器，例如将飞书消息转发到 Agent 服务
- **Modules** — 可被多个项目组合使用的独立代码组件

---

## 📋 目录

### Skills

| 名字 | 一句话 | 讲解 |
|---|---|---|
| 🏠 [**life-agent-os-builder**](#-life-agent-os-builder个人操作系统构建器) | 帮你从零搭建一套基于文件系统的个人操作系统，先访谈再建系统 | [Life-Agent-OS 项目](https://github.com/pite1376/life-agent-os) |
| 🧠 [**masters**](#-masters人生智囊团) | 构建你的人生导师团 — 芒格、马斯克、王阳明、曾国藩用思维模型陪你做决策 | 内置 5 位导师 + 圆桌会议 + 反方挑战 |
| 🚀 [**agent-project-delivery**](#-agent-project-delivery智能体项目交付流程助手) | 端到端智能体项目交付管理 — 从甲方需求到PRD、TSD、实施计划的全流程管控 | 强制阶段门禁，防止跳阶段 |

---

## 📦 安装方式

在 Claude Code 里直接说：

```
帮我安装这个 skill：https://github.com/pite1376/baichuan-skills/tree/main/<skill-name>
```

把 `<skill-name>` 换成你想装的那个，比如 `life-agent-os-builder`、`masters`。

---

## ✨ Skills

<a id="-skills"></a>

<table>
<tr><td>

### 🏠 life-agent-os-builder（个人操作系统构建器）

> *"先了解你是什么人，再帮你搭系统。"*

帮你从零搭建一套 **Life-Agent-OS** —— 基于文件系统的 AI 驱动人生操作系统。

不是扔给你一个模板就完事。它会先做 **5 轮深度访谈**，了解你的身份、生活结构、信息习惯、目标痛点、偏好约束，然后根据你的回答**个性化生成**目录结构、CLAUDE.md、运行规则、模板。

**为什么需要这个**

大多数人的问题不是"没有工具"，而是"没有系统"。笔记散落在 Notion、备忘录、微信收藏里，复盘做了几次就断了，计划写了但从没回顾过。Life-Agent-OS 用最朴素的方式解决这个问题：**一个 git 仓库 + AI 助手 + 固定节奏**。

**它会帮你搭什么**

- 个性化目录结构（根据你的生活板块定制）
- CLAUDE.md（AI 在这个项目里的行为规则）
- 系统架构文档（七层架构 + 运行流程）
- 每日/每周/每月模板
- 隐私规则（根据你的敏感信息定制）

**怎么触发**

```
/life-agent-os-builder    # 直接命令
搭建 Life-Agent-OS        # 自然语言
构建个人操作系统           # 自然语言
建一套人生管理系统         # 自然语言
```

→ [SKILL.md](./life-agent-os-builder/SKILL.md) · [模板参考](./life-agent-os-builder/references/templates.md) · [目录映射规则](./life-agent-os-builder/references/directory-mapping.md)

</td></tr>
</table>

<table>
<tr><td>

### 🧠 masters（人生智囊团）

> *"你想成为谁，就让谁来当你的导师。"*

构建你自己的**人生导师团**。不是聊天机器人式的"大师角色扮演"，而是把芒格、马斯克、王阳明、曾国藩等人的**思维模型、判断标准、提问方式**固化下来，形成一个可以持续陪伴你做决策的导师系统。

内置 5 位导师，各有明确分工：

| 角色 | 代号 | 核心能力 |
|------|------|---------|
| 主持人 | 苏格拉底 | 追问真相、澄清问题、不让你糊弄自己 |
| 风险导师 | 芒格 | 反向思考、识别误判、告诉你哪里可能翻车 |
| 破局导师 | 马斯克 | 第一性原理、拆解约束、找 10 倍效率方案 |
| 行动导师 | 王阳明 | 看清内心、知行合一、找到你卡住的真正原因 |
| 长期导师 | 曾国藩 | 习惯养成、自省节奏、帮你做时间的朋友 |

**为什么需要这个**

大部分人生建议之所以没用，是因为只安慰不挑战。这个系统不扮演大师说话，而是使用他们背后的**思维模型**审视你的问题。每次分析必须落到行动：今日做什么、7 天做什么、30 天观察什么指标。

**三种模式**

- **单大师深度对话** — 有明确需求时，和一位导师深入聊
- **圆桌会议** — 复杂人生问题，多位导师从不同角度给建议
- **反方挑战** — 专门质疑你的判断，暴露你在自我合理化的地方

**怎么触发**

```
/masters 芒格 [你的人生记录]       # 单大师
/masters 圆桌 [你的人生记录]       # 多大师讨论
/masters 挑战 [你的人生记录]       # 反方挑战
```

→ [SKILL.md](./masters/SKILL.md) · [大师档案](./masters/) · [决策评分机制](./masters/decision-score.md)

</td></tr>
</table>

<table>
<tr><td>

### 🚀 agent-project-delivery（智能体项目交付流程助手）

> *"不跳阶段，不编内容，每一步都有交接包。"*

端到端智能体项目交付管理 —— 从甲方原始需求到需求澄清、PRD、TSD、实施计划的全流程管控。

不是直接出方案就完事。它会**先判断当前材料所处阶段**，再选择对应流程，并在每个阶段结束时生成交接包和下一阶段判断。

**为什么需要这个**

大部分智能体项目翻车，不是技术不行，是流程混乱：需求没澄清就写PRD，PRD没确认就出TSD，TSD没验证就上实施。这个skill强制阶段门禁，材料不足时返回上一阶段，不允许跳步。

**四个阶段**

| 阶段 | 输入 | 输出 | 门禁条件 |
|------|------|------|----------|
| 需求审辨与澄清 | 甲方原始需求/会议纪要 | 需求确认包、Agent适配度判断 | 业务目标、目标用户、核心场景基本明确 |
| PRD生成 | 已确认需求 | PRD正文、JTBD分析、用户旅程 | 一期范围、任务能力、用户旅程明确 |
| TSD生成 | 已确认PRD | TSD正文、架构设计、接口方案 | 技术架构、知识库方案、工具调用方案明确 |
| 实施计划 | 已确认TSD | 任务拆解、测试用例、上线检查表 | 部署方案、运维责任明确 |

**怎么触发**

```
/agent-project-delivery    # 直接命令
甲方给了需求，帮我看看    # 自然语言
写PRD                     # 自然语言
出技术方案                 # 自然语言
```

→ [SKILL.md](./agent-project-delivery/agent-project-delivery.md) · [需求澄清流程](./agent-project-delivery/references/01-agent-requirement-clarifier.md) · [PRD生成流程](./agent-project-delivery/references/02-agent-prd-writer.md) · [TSD生成流程](./agent-project-delivery/references/03-agent-tsd-writer.md)

</td></tr>
</table>

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 🔌 Connectors 与 Modules

仓库中可复用内容分为三类：

- `skills/`：给 AI 使用的知识、规则和工作流程；
- `modules/`：可被多个方案复用的独立代码组件；
- `connectors/`：可以直接运行和部署的完整平台连接方案。

每个 Connector 都提供 `README.md`、`manifest.yaml`、配置模板和部署说明。
建议先阅读 [CATALOG.yaml](./CATALOG.yaml) 和对应组件的 `manifest.yaml`，
再按需读取源码。

当前连接器：

- [feishu-agent-bridge](./connectors/feishu-agent-bridge) — 飞书 WebSocket 接收消息，
  通过 HTTPS 调用扣子或其他异步 Agent，再回复飞书。

## 📄 License

[MIT](./LICENSE)
