# agent-bridge-runtime

消息通道和 Agent 后端之间的运行时组件，负责消息去重、会话序号和任务状态持久化。

当前实现文件：`store.py`。单实例默认使用 SQLite；多实例部署时可以替换为 PostgreSQL
或 Redis 实现相同接口。

