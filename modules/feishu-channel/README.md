# feishu-channel

可复用的飞书消息通道模块，负责飞书 WebSocket 连接、事件解析、资源下载和消息回复。

它只处理消息通道，不负责调用 Agent、任务轮询或业务 Prompt。适合被多个 `connectors/`
方案复用。

当前实现文件：`feishu_channel.py`，包含普通文本回复和 CardKit 2.0 流式卡片控制器。完整可部署示例见
`connectors/feishu-agent-bridge/`。

依赖：`lark-oapi`。需要飞书应用的 App ID、App Secret，以及开放平台消息和资源权限。
