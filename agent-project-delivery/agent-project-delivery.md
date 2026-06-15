---
name: agent-project-delivery
description: use this skill when the user needs to manage an end-to-end ai agent project delivery workflow from raw client requirements to requirement clarification, prd writing, tsd writing, and implementation planning. trigger when the user provides client requirements, client answers, confirmed requirements, prd materials, technical solution requests, or asks what stage the agent project is in, what to confirm next, how to write prd, how to write tsd, or how to move toward implementation. the skill must enforce stage gates, preserve assumptions and risks, and produce clear handoff packages between requirement clarification, prd, tsd, and implementation.
---

# 智能体项目交付流程助手

## 目标

将智能体项目从甲方原始需求推进到需求澄清、PRD、TSD 和实施计划。

本 Skill 不直接默认进入某个阶段，而是先判断当前材料所处阶段，再选择对应流程，并在每个阶段结束时生成交接包和下一阶段判断。

## 阶段

智能体项目分为四个阶段：

1. 需求审辨与澄清
2. PRD 生成
3. TSD 生成
4. 实施计划

## 核心规则

- 不允许从甲方原始需求直接跳到 TSD。
- 不允许在需求未澄清时生成正式 PRD。
- 不允许在 PRD 关键内容不完整时生成正式 TSD。
- 不允许在 TSD 关键内容不完整时进入实施。
- 每个阶段都必须生成交接包。
- 每个阶段都必须判断是否可进入下一阶段。
- 每个阶段都必须保留已确认事实、待确认事项、合理假设和风险。
- 未确认内容不得写成确定事实。
- 如果材料不足，应生成待确认版产物，而不是编造内容。
- 输出时优先说明当前阶段、阶段判断、推荐动作和下一步输入。

## 阶段判断

根据用户输入判断当前阶段。

### 需求审辨与澄清阶段

适用于：

- 用户提供甲方原始需求
- 用户提供会议纪要
- 用户询问需要向甲方确认什么
- 用户询问需求是否适合做 Agent
- 用户尚未提供确认版需求

使用 `references/01-agent-requirement-clarifier.md`。

输出：

- 需求理解摘要
- 当前成熟度判断
- 事实、假设与不确定性
- 关键信息缺口
- Agent 适配度判断
- 向甲方确认的问题
- 可发送给甲方的反馈文本
- 是否可以进入 PRD
- 需求确认包

### PRD 阶段

适用于：

- 用户提供已确认需求
- 用户提供甲方回复
- 用户要求生成智能体 PRD
- 需求澄清阶段判断可以进入 PRD

使用 `references/02-agent-prd-writer.md`。

输出：

- PRD 正文
- JTBD 分析
- 场景分析
- 用户旅程
- Agent 定位
- 一期范围与非目标
- 任务能力设计
- 知识库与数据要求
- 工具与系统协作要求
- 权限、风险与兜底机制
- 评估与验收标准
- 运营与持续优化
- 是否可以进入 TSD
- PRD 交接包

### TSD 阶段

适用于：

- 用户提供 PRD
- 用户要求生成技术方案设计
- PRD 阶段判断可以进入 TSD
- 用户需要架构、RAG、工具调用、接口、权限、测试、上线方案

使用 `references/03-agent-tsd-writer.md`。

输出：

- TSD 正文
- 技术前提与约束
- 总体架构
- Agent 行为与编排设计
- 模型与提示词策略
- 知识库与 RAG 设计
- 工具调用与系统集成设计
- 数据流与状态设计
- 权限、安全与风控设计
- Failure Analysis
- Trade-off 决策记录
- 测试与验收设计
- 日志、观测与运营设计
- 部署、联调与上线方案
- 演进路线
- 实施任务拆解
- 是否可以进入实施
- TSD 交接包

### 实施计划阶段

适用于：

- 用户提供 TSD
- 用户要求拆解实施任务
- 用户要求生成交付计划、配置清单、测试用例或上线检查表
- TSD 阶段判断可以进入实施

输出：

- 实施任务拆解
- 人员分工
- 资料准备清单
- 平台配置清单
- 知识库建设清单
- 工具与接口联调清单
- 测试用例清单
- 上线检查表
- 验收材料清单
- 风险跟踪表
- 交付节奏建议

## 阶段门禁

### 进入 PRD 的最低条件

必须具备：

- 业务目标基本明确
- 目标用户基本明确
- 核心场景基本明确
- 一期范围有初步边界
- Agent 适配度已有判断
- 知识来源已有初步判断
- 系统对接范围已有初步判断
- 验收方向已有初步判断

不满足时，返回需求澄清阶段。

### 进入 TSD 的最低条件

必须具备：

- 一期范围明确
- 任务能力明确
- 用户旅程明确
- 知识边界明确
- 工具调用需求明确
- 权限风险边界明确
- 验收标准明确
- 待确认事项可控

不满足时，返回 PRD 阶段。

### 进入实施的最低条件

必须具备：

- 技术架构明确
- 知识库方案明确
- 工具调用方案明确
- 系统接口条件明确
- 权限风控明确
- 失败兜底明确
- 测试验收明确
- 部署上线方案明确
- 运维责任明确

不满足时，返回 TSD 阶段。

## 默认输出顺序

每次响应先输出：

1. 当前阶段判断
2. 是否可以进入下一阶段
3. 主要缺口或风险
4. 当前阶段产物
5. 下一步建议
6. 交接包

## 质量检查

输出前检查：

- 是否正确判断当前阶段
- 是否避免跳阶段
- 是否使用了对应阶段的流程
- 是否保留事实、假设、待确认和风险
- 是否生成交接包
- 是否判断能否进入下一阶段
- 是否避免编造客户信息
- 是否避免过度承诺
- 是否让下一阶段可以直接接收当前输出