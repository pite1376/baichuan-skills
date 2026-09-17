<div align="center">

[中文](./README.md) · **English**

# 🧰 Baichuan Skills

#### Open-source AI Skills by Baichuan — Life Operating System + Decision Analysis

[![License](https://img.shields.io/badge/License-MIT-3B82F6?style=for-the-badge)](./LICENSE)
[![Skills](https://img.shields.io/badge/Skills-2-10B981?style=for-the-badge)](#-skills)

![Claude Code](https://img.shields.io/badge/Claude_Code-Skill-D97706?style=flat-square&logo=anthropic&logoColor=white)

</div>

Things I actually use every day. Only open-sourced after they proved useful.

- **Skills** — Structured instruction sets that agents can load directly

---

## 📋 Catalog

### Skills

| Name | One-liner | Details |
|---|---|---|
| 🏠 [**life-agent-os-builder**](#-life-agent-os-builder) | Build a file-system-based personal life operating system from scratch. Interview first, then build. | [Life-Agent-OS](https://github.com/pite1376/life-agent-os) |
| 🧠 [**masters**](#-masters) | Build your life mentor board — Munger, Musk, Wang Yangming, Zeng Guofan use thinking models to guide your decisions | 5 built-in mentors + roundtable + devil's advocate |

---

## 📦 Installation

In Claude Code, just say:

```
Install this skill: https://github.com/pite1376/baichuan-skills/tree/main/<skill-name>
```

Replace `<skill-name>` with the one you want, e.g. `life-agent-os-builder` or `masters`.

---

## ✨ Skills

<a id="-skills"></a>

<table>
<tr><td>

### 🏠 life-agent-os-builder (Life OS Builder)

> *"Understand who you are first, then build the system."*

Helps you build a **Life-Agent-OS** from scratch — a file-system-based, AI-driven personal life operating system.

It doesn't just hand you a template. It runs a **5-round deep interview** covering your identity, daily structure, information habits, goals, pain points, and constraints. Then it **personally generates** your directory structure, CLAUDE.md, operating rules, and templates based on your answers.

**What it builds**

- Personalized directory structure (based on your life sectors)
- CLAUDE.md (AI behavior rules for this project)
- System architecture docs (7-layer architecture + operating flow)
- Daily / weekly / monthly templates
- Privacy rules (customized for your sensitive info)

**How to trigger**

```
/life-agent-os-builder
```

→ [SKILL.md](./life-agent-os-builder/SKILL.md) · [Template Reference](./life-agent-os-builder/references/templates.md) · [Directory Mapping](./life-agent-os-builder/references/directory-mapping.md)

</td></tr>
</table>

<table>
<tr><td>

### 🧠 masters (Life Advisory Board)

> *"Whoever you want to become, let them be your mentor."*

Build your own **personal board of life mentors**. Not chatbot-style "master roleplay" — instead, it crystallizes the **thinking models, judgment criteria, and questioning methods** of Munger, Musk, Wang Yangming, Zeng Guofan, and others into a mentor system that continuously accompanies your decision-making.

Built-in mentors with clear responsibilities:

| Role | Code Name | Core Ability |
|------|-----------|-------------|
| Moderator | Socrates | Pursue truth, clarify questions, won't let you fool yourself |
| Risk Mentor | Munger | Inverse thinking, spot biases, tell you where things might break |
| Breakthrough Mentor | Musk | First principles, decompose constraints, find 10x efficiency |
| Action Mentor | Wang Yangming | See inner truth, mind-action alignment, find what's really blocking you |
| Long-term Mentor | Zeng Guofan | Habit building, self-reflection rhythm, help you befriend time |

**Three modes**

- **Single mentor deep dialogue** — go deep with one mentor on a specific concern
- **Roundtable meeting** — complex life decisions, multiple mentors from different angles
- **Devil's advocate** — challenges your judgment, exposes where you're self-justifying

**How to trigger**

```
/masters Munger [your life record]
/masters roundtable [your life record]
/masters challenge [your life record]
```

→ [SKILL.md](./masters/SKILL.md) · [Master Profiles](./masters/) · [Decision Scoring](./masters/decision-score.md)

</td></tr>
</table>

---

## 🧩 Content Categories

- `skills/` — instructions, knowledge, and workflows for AI agents;
- `modules/` — reusable medium-grained code components;
- `connectors/` — complete, deployable integration solutions;
- `examples/` — minimal composition examples.

See [CATALOG.yaml](./CATALOG.yaml) and each component's `manifest.yaml` for a concise
description of purpose, inputs, outputs, dependencies, and limitations.

Current connector: [feishu-agent-bridge](./connectors/feishu-agent-bridge)

Current reusable modules:

- [feishu-channel](./modules/feishu-channel)
- [async-agent-backend](./modules/async-agent-backend)
- [agent-bridge-runtime](./modules/agent-bridge-runtime)

## 🤝 Contributing

Issues and Pull Requests are welcome.

## 📄 License

[MIT](./LICENSE)
