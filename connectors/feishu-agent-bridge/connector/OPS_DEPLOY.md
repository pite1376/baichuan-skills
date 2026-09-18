# 飞书－扣子流式连接器运维部署手册

交付版本：2026-09-18 CardKit SSE

## 1. 部署目标

在一台长期在线的 Linux 服务器上运行独立连接器：

```text
飞书 WebSocket → 外部连接器 → 扣子 /stream_run SSE → 飞书 CardKit 2.0 流式卡片
```

连接器不监听公网业务端口，不需要域名、Nginx 或 HTTPS 证书。服务器只需允许出站
访问飞书 WSS/HTTPS 和 `https://76mwxwmfhb.coze.site`。

## 2. 前置要求

- Linux x86_64 或 arm64；
- Docker Engine 24+、Docker Compose v2；
- 服务器时间已同步；
- 飞书应用已启用机器人能力并订阅 `im.message.receive_v1`；
- 已开通机器人收发消息、消息资源及 CardKit 创建/发送/更新权限；
- 扣子 Agent 的 `/stream_run` 可访问；
- 旧版扣子进程不再维持飞书长连接。

## 3. 交付文件

```text
connector/
├── __init__.py
├── main.py
├── coze_client.py
├── feishu.py
├── settings.py
├── store.py
├── README.md
└── OPS_DEPLOY.md
Dockerfile
docker-compose.yml
requirements.txt
.env
SHA256SUMS
```

`.env` 应填入飞书 App ID、App Secret、扣子 Token、项目 ID 和 API 地址。
它属于敏感文件：传输必须使用私密渠道；落盘后权限设为 `600`；不得提交 Git、发到
公开群或写入镜像。

## 4. 首次部署

```bash
cd feishu-agent-bridge
sha256sum -c SHA256SUMS
chmod 600 .env
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=300 -f feishu-connector
```

正常启动日志应包含：

```text
连接器异步任务循环已启动
飞书连接器启动
connected to wss://msg-frontier.feishu.cn/...
```

## 5. 上线切换顺序

1. 在扣子 Agent 环境设置 `FEISHU_BOT_ENABLED=false`；
2. 重新部署扣子 Agent，确保旧版长连接退出；
3. 等待 1－2 分钟，让飞书清理旧连接；
4. 在外部服务器启动本连接器；
5. 完成第 6 节验收；
6. 验收通过后保持单实例运行。

不要让旧版机器人和外部连接器同时使用同一个飞书 App 建立长连接，否则消息可能被
随机分配到不同实例。

## 6. 验收清单

### 6.1 流式卡片

飞书私聊机器人发送：

```text
流式测试，请用两句话回复
```

预期：

1. 立即出现标题为“Costa PPT 助手”的 CardKit 卡片；
2. 初始正文为“正在连接智能体，请稍候…”；
3. Agent 有输出后，同一张卡片正文逐步增长；
4. 不产生大量碎片文本消息；
5. 完成后卡片停止流式状态，内容保留完整；
6. 如果 60 秒仍无文本，同一卡片显示“⏳ 收到，正在处理中，请稍候…”。

### 6.2 上下文

依次发送：

```text
我想做一份门店培训PPT
受众是新入职店员
```

预期：第二条回复能理解上一条主题，不重复首次身份介绍。

发送“新建对话”，预期立即收到：

```text
已开启全新对话，此前的上下文不再带入。请继续～
```

该提示不走 SSE，不受 60 秒配置影响。

### 6.3 文件与重启

- 发送 PDF 或 DOCX，确认能提取文字并进入 Agent；
- 执行容器重启，确认恢复飞书长连接；
- 日志不得持续出现 `401`、`403`、CardKit 权限错误或 WebSocket 重连。

## 7. 配置说明

```env
COZE_API_BASE_URL=https://76mwxwmfhb.coze.site
COZE_PROJECT_ID=7680791829243035657
ACK_DELAY_SECONDS=60
TASK_TIMEOUT_SECONDS=900
POLL_INTERVAL_SECONDS=2
REQUEST_TIMEOUT_SECONDS=30
CONNECTOR_DATABASE_PATH=/app/data/connector.db
LOG_LEVEL=INFO
```

- `ACK_DELAY_SECONDS`：60 秒无 Agent 文本时，更新同一卡片的处理中状态；
- `TASK_TIMEOUT_SECONDS`：单次 SSE 最大执行时间；
- `REQUEST_TIMEOUT_SECONDS`：连接和写请求超时；
- `POLL_INTERVAL_SECONDS`：兼容旧接口的保留参数，当前 SSE 主链路不使用；
- `CONNECTOR_DATABASE_PATH`：消息去重和会话序号数据库。

修改 `.env.connector` 后执行：

```bash
docker compose -f docker-compose.connector.yml up -d --force-recreate
```

## 8. 日常运维

```bash
docker compose -f docker-compose.connector.yml ps
docker compose -f docker-compose.connector.yml logs --tail=500 -f feishu-connector
docker compose -f docker-compose.connector.yml restart feishu-connector
docker compose -f docker-compose.connector.yml down
docker compose -f docker-compose.connector.yml up -d --build
```

SQLite 数据保存在 Docker volume `connector-data`。不要执行 `down -v`，否则会删除
消息去重记录和会话序号。

## 9. 日志故障判断

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `401` / `403` | 飞书或扣子凭证失效 | 检查并轮换对应密钥，重建容器 |
| WebSocket 持续重连 | 网络、证书、重复实例或 App 配置 | 检查出站网络、系统时间及旧实例 |
| 卡片创建失败 | CardKit 权限或卡片 JSON 问题 | 查看 `code/msg`，确认权限和应用版本 |
| 卡片出现但不更新 | SSE 无 answer 或元素更新失败 | 检查 SSE 和 `stream_md` 更新日志 |
| 每次都自我介绍 | volume 未持久化或 session_id 变化 | 检查数据库路径和 volume |
| 60 秒出现处理中 | Agent 尚未产生首段 SSE | 属于预期状态，不是断连 |
| 生成一半中断 | SSE、网络或任务超时 | 查看中断前后的 HTTP/超时日志 |

## 10. 回滚

保留上一版本目录或镜像标签。若新版异常：

```bash
docker compose -f docker-compose.connector.yml down
cd ../上一版本目录
docker compose -f docker-compose.connector.yml up -d
```

回滚期间不要在扣子侧重新启用旧飞书连接，除非明确停止外部连接器，确保同一 App
始终只有一个消费者。

## 11. 安全要求

- `.env.connector` 权限必须为 `600`；
- 不在工单、群聊或日志中粘贴完整 App Secret / API Token；
- 不把 `.env.connector` COPY 进 Docker 镜像；
- 密钥轮换后执行 `up -d --force-recreate`；
- 交付包包含真实密钥，用完后应从个人下载目录删除；
- 如果交付渠道不是端到端加密，先移除 `.env.connector`，由运维通过密钥系统注入。
