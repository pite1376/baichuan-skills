# feishu-custom-http-agent

示例说明如何保留飞书通道，把 Agent 后端替换为其他提供异步 HTTP 接口的平台。

只需要实现 `async-agent-backend` 约定的提交任务、查询任务和提取结果操作，
连接器的飞书处理和会话运行时可以继续复用。

