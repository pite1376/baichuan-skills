<div align="center">

**中文** · [English](./README.en.md)

# 🧰 Baichuan Skills

#### 白川开源的 AI Skills 合集 — 个人操作系统 + 人生决策分析

[![License](https://img.shields.io/badge/License-MIT-3B82F6?style=for-the-badge)](./LICENSE)
[![Skills](https://img.shields.io/badge/Skills-2-10B981?style=for-the-badge)](#-skills)

![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-D97706?style=flat-square&logo=anthropic&logoColor=white)

</div>

都是自己实际在用的东西，跑通了才搬出来开源。

- **Skills** — Agent 能直接加载的结构化指令集，Claude Code 等工具可直接使用

---

## 📋 目录

### Skills

| 名字 | 一句话 | 讲解 |
|---|---|---|
| 🏠 [**life-agent-os-builder**](#-life-agent-os-builder个人操作系统构建器) | 帮你从零搭建一套基于文件系统的个人操作系统，先访谈再建系统 | [Life-Agent-OS 项目](https://github.com/pite1376/life-agent-os) |
| 🧠 [**masters**](#-masters人生智囊团) | 用芒格、马斯克、王阳明、曾国藩的思维模型分析你的人生记录和决策 | 内置 5 位大师 + 圆桌讨论 + 反方挑战 |

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

> *"不是角色扮演，而是思维模型代理。"*

用不同思维模型分析你的人生记录和决策。内置 5 位大师，各有明确分工：

| 角色 | 代号 | 职责 |
|------|------|------|
| 主持人 | 苏格拉底 | 提炼问题、追问澄清、控制流程 |
| 风险官 | 芒格 | 反向思考、识别误判、评估风险 |
| 破局官 | 马斯克 | 第一性原理、拆解约束、高效方案 |
| 行动官 | 王阳明 | 内心动机、知行合一、行动阻塞 |
| 长期官 | 曾国藩 | 习惯、自省、长期主义、耐力 |

**为什么需要这个**

大部分人生建议之所以没用，是因为只安慰不挑战。这个系统不扮演大师说话，而是使用他们背后的**思维模型**分析你的问题。输出必须落到行动：今日做什么、7 天做什么、30 天观察什么指标。

**三种模式**

- **单大师分析** — 有明确需求时，深度优先
- **圆桌讨论** — 复杂人生问题，多维度互补
- **反方挑战** — 专门质疑你的判断，暴露自我合理化

**怎么触发**

```
/masters 芒格 [你的人生记录]       # 单大师
/masters 圆桌 [你的人生记录]       # 多大师讨论
/masters 挑战 [你的人生记录]       # 反方挑战
```

→ [SKILL.md](./masters/SKILL.md) · [大师档案](./masters/) · [决策评分机制](./masters/decision-score.md)

</td></tr>
</table>

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📄 License

[MIT](./LICENSE)
