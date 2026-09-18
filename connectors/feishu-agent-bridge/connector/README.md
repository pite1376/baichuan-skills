# 飞书－扣子外部连接器

连接器常驻外部服务器，通过飞书 SDK WebSocket 接收消息，调用扣子 Agent 的
`/stream_run` SSE 接口，并把 Agent 文本持续更新到同一张 CardKit 2.0 卡片。

## 部署

1. 在飞书开放平台启用「使用长连接接收事件」，订阅
   `im.message.receive_v1`，并授予消息接收、机器人发消息、CardKit 以及
   `im:message:readonly`、`im:chat:read` 权限。
2. 复制 `.env.example` 为 `.env`，填入新生成的凭证。
3. 确认扣子托管项目没有启动旧机器人：`FEISHU_BOT_ENABLED=false`。
4. 启动并查看日志：

```bash
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml logs -f feishu-connector
```

服务器只需允许出站 HTTPS/WSS，不需要域名、证书或开放入站业务端口。

## 本地运行

```bash
python -m pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
python -m connector.main
```

程序会自动使用 `certifi` CA 根证书验证扣子 HTTPS 和飞书 WSS 连接，不需要关闭
TLS 证书校验。

流式卡片会立即显示“正在连接智能体”。`ACK_DELAY_SECONDS` 只控制卡片内
“⏳ 收到，正在处理中”状态的等待时间，默认 60 秒；Agent 一旦开始输出即取消该
状态更新。“新建对话”等连接器本地回复不经过这个计时器，会继续即时发送。

卡片采用无 header 的单正文样式，不展示“Costa PPT 助手”或永久的“正在生成内容”。
生成完成后只保留答案正文。普通正文中的单换行会转换为 CardKit 支持的 `<br>`，代码
块、表格、列表、标题、引用、已有双换行和已有 `<br>` 保持原结构。

真实 `.env` 不得提交到 Git。连接器使用 SQLite 持久化消息去重和真正的
`conversation_key → session_id` 映射，Docker volume 默认保存于 `connector-data`：

- 私聊按发送者 `open_id` 隔离；
- 普通群按 `chat_id` 共享；
- 话题群按 `chat_id + thread_id/root_id` 隔离；
- 群聊只有明确 @ 当前机器人时才触发 Agent；
- “新建对话”只重置当前私聊、群或话题的映射。

群聊被 @ 时，连接器会读取最近 30 分钟、最多 20 条可用文本作为补充背景。可以用
以下变量调整：

```env
GROUP_CONTEXT_ENABLED=true
GROUP_CONTEXT_MAX_MESSAGES=20
GROUP_CONTEXT_WINDOW_SECONDS=1800
GROUP_CONTEXT_MAX_CHARS=8000
```

CardKit 创建、发送或更新失败时，连接器仍会完整消费 Agent SSE，并在结束后降级发送
一条完整普通文本。卡片只按 Agent 实际返回的 `answer` 增量更新；如果上游只返回一个
chunk，连接器不会伪造逐字效果。

文字、富文本、PDF、DOCX、TXT、MD、CSV、JSON 已支持。当前扣子接口样例没有给出
图片上传协议，因此图片会返回明确提示，不会静默丢失。
