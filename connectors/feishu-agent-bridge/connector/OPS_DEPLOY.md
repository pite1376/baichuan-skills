# 飞书－扣子流式连接器运维部署手册

交付版本：2026-09-18.4 无头 CardKit + Markdown 换行 + 持久化会话 + 群聊上下文

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
- 已开通群聊历史读取所需的 `im:message:readonly`、`im:chat:read`；
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
tests/
└── test_connector.py
Dockerfile
docker-compose.yml
requirements.txt
.env
SHA256SUMS
```

`.env` 需要由运维通过密钥系统或私密渠道注入 App ID、App Secret、扣子 Token、项目 ID 和 API 地址；
本开源仓库只提供 `.env.example`，不包含真实凭证。
它属于敏感文件：传输必须使用私密渠道；落盘后权限设为 `600`；不得提交 Git、发到
公开群或写入镜像。

## 4. 首次部署

```bash
unzip feishu-connector-streaming-ops-20260918-v3.2.zip
cd feishu-connector-streaming-ops-20260918-v3.2
sha256sum -c SHA256SUMS
chmod 600 .env
python -m unittest discover -s tests -v
docker compose -f docker-compose.yml build --pull --no-cache
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs --tail=300 -f feishu-connector
```

### 4.1 从旧版原地升级

如果服务器已经运行旧目录 `feishu-connector-streaming-ops-20260918`，不要直接在名称不同
的新目录执行 `docker compose up`。Compose 默认使用目录名作为 project name；目录名改变
时，可能创建新的 `connector-data` volume，导致旧数据库没有挂载。

推荐保持旧部署目录路径不变：

1. 在旧目录中按第 8 节命令在线备份 `connector.db`；
2. 执行 `docker compose -f docker-compose.yml down`，禁止添加 `-v`；
3. 把新包的 `connector/`、`tests/`、`Dockerfile`、
   `docker-compose.yml`、`requirements.txt` 覆盖到原目录；
4. 保留原 `.env`，补入四个 `GROUP_CONTEXT_*` 变量；
5. 在原目录执行测试、无缓存构建和启动命令。

```bash
python -m unittest discover -s tests -v
docker compose -f docker-compose.yml build --pull --no-cache
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml logs --tail=300 -f feishu-connector
```

如果必须从新目录启动，先通过 `docker compose ls` 确认旧 project name，然后所有新目录
命令都显式添加 `-p <旧project名称>`；上线前再确认实际挂载的仍是旧
`connector-data` volume。

正常启动日志应包含：

```text
连接器异步任务循环已启动
飞书连接器启动
connected to wss://msg-frontier.feishu.cn/...
```

同时应看到版本 `2026.09.18.4`、数据库路径 `/app/data/connector.db` 和机器人身份解析
成功的日志。版本核对：

```bash
docker compose -f docker-compose.yml exec feishu-connector \
  python -c 'import connector; print(connector.__version__)'
docker compose -f docker-compose.yml exec feishu-connector \
  sha256sum /app/connector/main.py /app/connector/store.py /app/connector/feishu.py
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

1. 立即出现无 header 的 CardKit 正文，不显示“Costa PPT 助手”和“正在生成内容”；
2. 初始正文为“正在连接智能体，请稍候…”；
3. Agent 有输出后，同一张卡片正文逐步增长；
4. 不产生大量碎片文本消息；
5. 完成后卡片停止流式状态，只保留完整答案正文；
6. 如果 60 秒仍无文本，同一卡片显示“⏳ 收到，正在处理中，请稍候…”；
7. 普通正文单换行正确显示，代码块、表格、列表和双换行结构不被破坏。

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

### 6.4 会话隔离与群聊

1. 两个私聊用户分别发消息，日志中的会话指纹应不同；同一用户重发时指纹保持不变；
2. 同一普通群的两个成员分别 @机器人，会话指纹应相同，并能理解前序群聊背景；
3. 未 @机器人的普通群消息不得调用 Agent；
4. 同群两个不同话题分别 @机器人，会话指纹应不同，回复保留在原话题；
5. “新建对话”只更换当前会话指纹，不影响其他用户、群和话题；
6. 重启容器后再次消息，会话指纹应保持不变。

## 7. 配置说明

```env
COZE_API_BASE_URL=https://76mwxwmfhb.coze.site
COZE_PROJECT_ID=7680791829243035657
ACK_DELAY_SECONDS=60
TASK_TIMEOUT_SECONDS=900
POLL_INTERVAL_SECONDS=2
REQUEST_TIMEOUT_SECONDS=30
CONNECTOR_DATABASE_PATH=/app/data/connector.db
GROUP_CONTEXT_ENABLED=true
GROUP_CONTEXT_MAX_MESSAGES=20
GROUP_CONTEXT_WINDOW_SECONDS=1800
GROUP_CONTEXT_MAX_CHARS=8000
LOG_LEVEL=INFO
```

- `ACK_DELAY_SECONDS`：60 秒无 Agent 文本时，更新同一卡片的处理中状态；
- `TASK_TIMEOUT_SECONDS`：单次 SSE 最大执行时间；
- `REQUEST_TIMEOUT_SECONDS`：连接和写请求超时；
- `POLL_INTERVAL_SECONDS`：兼容旧接口的保留参数，当前 SSE 主链路不使用；
- `CONNECTOR_DATABASE_PATH`：消息去重、持久化会话映射和群聊上下文游标数据库；
- `GROUP_CONTEXT_ENABLED`：是否为被 @ 的群聊请求注入近期背景；
- `GROUP_CONTEXT_MAX_MESSAGES`：单次最多读取和注入的历史消息数；
- `GROUP_CONTEXT_WINDOW_SECONDS`：历史消息时间窗口；
- `GROUP_CONTEXT_MAX_CHARS`：群聊背景总字符上限，单条最多 1,000 字。

修改 `.env` 后执行：

```bash
docker compose -f docker-compose.yml up -d --force-recreate
```

## 8. 日常运维

```bash
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs --tail=500 -f feishu-connector
docker compose -f docker-compose.yml restart feishu-connector
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d --build
```

SQLite 数据保存在 Docker volume `connector-data`。不要执行 `down -v`，否则会删除
消息去重记录、真实 session 映射和群聊上下文游标，导致所有会话重新开始。当前实现按
单实例部署设计；同一飞书 App 不要同时启动多个连接器容器。

升级时会自动新增 `conversation_sessions` 表，不重建也不删除旧表。私聊和普通群首次
访问时，如果数据库能证明该 chat 曾由旧版处理，会迁移旧的
`feishu_{chat_id}` / `feishu_{chat_id}_{sequence}`；全新会话使用 UUID。话题群不会复用
旧的群级 session，而是从独立 UUID 开始。

升级前备份数据库：

```bash
docker compose -f docker-compose.yml exec -T feishu-connector \
  python -c 'import sqlite3; s=sqlite3.connect("/app/data/connector.db"); d=sqlite3.connect("/app/data/connector.db.backup"); s.backup(d); d.close(); s.close()'
docker compose -f docker-compose.yml cp \
  feishu-connector:/app/data/connector.db.backup ./connector.db.backup
```

## 9. 日志故障判断

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `401` / `403` | 飞书或扣子凭证失效 | 检查并轮换对应密钥，重建容器 |
| WebSocket 持续重连 | 网络、证书、重复实例或 App 配置 | 检查出站网络、系统时间及旧实例 |
| 卡片创建/发送失败，出现普通文本 | CardKit 权限、JSON 或发送阶段异常 | 查看带 `create/send` 阶段的 `code/msg`，普通文本是预期降级 |
| 卡片出现但不更新 | SSE 无 answer 或元素更新失败 | 检查 `update/finish` 阶段、SSE chunk 数和 `stream_md` 更新日志 |
| 每次都自我介绍 | volume 未持久化或 session 映射变化 | 检查数据库路径、volume 及同一用户的脱敏 session 指纹 |
| 60 秒出现处理中 | Agent 尚未产生首段 SSE | 属于预期状态，不是断连 |
| 最终一次性显示全文 | 上游 Agent 只返回一个 answer chunk | 连接器不会伪造流式；需在 Agent 内修复真正的分块输出 |
| 群聊不回复 | 未 @当前机器人、机器人身份解析失败或事件配置错误 | 检查 @对象、启动日志和 `im.message.receive_v1` |
| 群聊没有近期背景 | 缺少历史消息权限或筛选后无可用文本 | 检查 `im:message:readonly`、`im:chat:read` 和历史注入计数 |
| 生成一半中断 | SSE、网络或任务超时 | 查看中断前后的 HTTP/超时日志 |

## 10. 回滚

保留上一版本目录或镜像标签。若新版异常：

```bash
docker compose -f docker-compose.yml down
cd ../上一版本目录
docker compose -f docker-compose.yml up -d
```

回滚期间不要在扣子侧重新启用旧飞书连接，除非明确停止外部连接器，确保同一 App
始终只有一个消费者。

## 11. 安全要求

- `.env` 权限必须为 `600`；
- 不在工单、群聊或日志中粘贴完整 App Secret / API Token；
- 不把 `.env` COPY 进 Docker 镜像；
- 密钥轮换后执行 `up -d --force-recreate`；
- 交付包包含真实密钥，用完后应从个人下载目录删除；
- 如果交付渠道不是端到端加密，先移除 `.env`，由运维通过密钥系统注入。
