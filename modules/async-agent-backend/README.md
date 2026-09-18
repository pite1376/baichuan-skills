# async-agent-backend

异步 Agent 后端调用模块，封装提交任务、轮询任务状态、超时、重试和最终文本提取。

当前实现文件：`async_agent_backend.py`，支持扣子 `/stream_run` SSE 和兼容旧版的异步任务接口。
接口设计保持平台无关，后续可在同一模块下增加 Dify、OpenAI-compatible 或自定义 HTTP 后端。

依赖：`httpx`。模块不关心消息来自飞书、Slack 还是 Web。
