# 飞书－扣子连接器运维部署单

## 目标

在一台长期在线的 Linux 服务器上运行飞书 WebSocket 连接器。连接器不监听公网端口，
只需允许出站访问飞书 WSS/HTTPS 和 `https://76mwxwmfhb.coze.site`。

## 前置要求

- Docker Engine 24+；
- Docker Compose v2；
- 服务器时间和时区同步；
- 飞书应用已订阅 `im.message.receive_v1`，并开启机器人收发消息权限；
- 扣子托管 Agent 已停止启动旧飞书机器人。

## 文件

部署包根目录应包含：

```text
connector/
Dockerfile
docker-compose.yml
requirements.txt
.env
```

`.env` 应配置飞书 App ID、App Secret、扣子 Token、项目 ID 和 API 地址，
属于敏感文件，权限应设为 `600`，不得提交到 Git 或发到公开群聊。

## 启动

```bash
chmod 600 .env
docker compose up -d --build
docker compose logs --tail=200 -f feishu-connector
```

正常日志应包含：

```text
连接器异步任务循环已启动
飞书连接器启动
connected to wss://msg-frontier.feishu.cn/...
```

## 验收

1. 飞书私聊机器人发送“你好”，应收到 Agent 回复；
2. 连续发送两条消息，回复顺序应一致；
3. 发送“新建对话”，应收到会话已重置提示；
4. 发送 PDF 或 DOCX，应能提取文字并交给 Agent；
5. 执行 `docker compose ... restart` 后，应自动恢复长连接；
6. `docker compose ... logs` 中不得出现 `401`、`403` 或持续重连。

## 常用命令

```bash
docker compose ps
docker compose restart feishu-connector
docker compose logs --tail=500 feishu-connector
docker compose down
```

SQLite 数据保存在 Docker volume `connector-data`。执行 `down` 不会删除；不要执行
`down -v`，否则会删除消息去重记录和会话序号。

## 扣子侧切换

重新部署扣子 Agent 项目，确保环境变量：

```env
FEISHU_BOT_ENABLED=false
```

新版代码已经移除 Agent 服务内的飞书启动逻辑。切换时先停止旧连接，等待 1－2 分钟，
再启动外部连接器，避免飞书将消息短暂路由给旧连接。
