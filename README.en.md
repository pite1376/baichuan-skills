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
| 🧠 [**masters**](#-masters) | Analyze life records and decisions using thinking models from Munger, Musk, Wang Yangming, and Zeng Guofan | 5 built-in masters + roundtable + devil's advocate |

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

> *"Not roleplay — thinking model agents."*

Analyze life records and decisions using different thinking models. Built-in masters with clear responsibilities:

| Role | Code Name | Responsibility |
|------|-----------|---------------|
| Moderator | Socrates | Refine questions, control flow |
| Risk Officer | Munger | Inverse thinking, identify biases |
| Breakthrough Officer | Musk | First principles, find efficient solutions |
| Action Officer | Wang Yangming | Inner truth, mind-action alignment |
| Long-term Officer | Zeng Guofan | Habits, self-reflection, endurance |

**Three modes**

- **Single master** — deep analysis on a specific concern
- **Roundtable** — multiple masters, complementary perspectives
- **Devil's advocate** — challenges your judgment, exposes self-justification

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

## 🤝 Contributing

Issues and Pull Requests are welcome.

## 📄 License

[MIT](./LICENSE)
