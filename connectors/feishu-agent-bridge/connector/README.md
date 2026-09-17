# 飞书－扣子外部连接器

连接器常驻外部服务器，通过飞书 SDK WebSocket 接收消息，再调用扣子 Agent 的
`/async_run` 和 `/task/{task_id}` HTTPS API，最后把结果回复到飞书。

## 部署

1. 在飞书开放平台启用「使用长连接接收事件」，订阅
   `im.message.receive_v1`，并授予消息接收、机器人发消息以及资源读取权限。
2. 复制 `.env.example` 为 `.env`，填入部署凭证。
3. 确认扣子托管项目没有启动旧机器人：`FEISHU_BOT_ENABLED=false`。
4. 启动并查看日志：

```bash
docker compose up -d --build
docker compose logs -f feishu-connector
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

真实 `.env.connector` 不得提交到 Git。连接器使用 SQLite 持久化消息去重、任务映射
和会话序号，Docker volume 默认保存于 `connector-data`。

文字、富文本、PDF、DOCX、TXT、MD、CSV、JSON 已支持。当前扣子接口样例没有给出
图片上传协议，因此图片会返回明确提示，不会静默丢失。
