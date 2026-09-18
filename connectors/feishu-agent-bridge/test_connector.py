import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpx

from connector.coze_client import (
    CozeClient,
    extract_reply_text,
    extract_stream_text,
    merge_stream_text,
)
from connector.feishu import (
    CardOperationError,
    FeishuClient,
    GroupContextMessage,
    IncomingMessage,
    StreamingCard,
    _chunk_text,
    _streaming_card_spec,
    _to_post,
    format_card_markdown,
    parse_event,
)
from connector.main import Connector, build_group_prompt, resolve_conversation
from connector.store import Store


class StoreTests(unittest.TestCase):
    def test_message_dedup_and_new_uuid_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "test.db"))
            self.assertTrue(store.claim_message("m1", "c1"))
            self.assertFalse(store.claim_message("m1", "c1"))
            self.assertIsNone(store.legacy_session_id("c1", "m1"))
            first = store.get_or_create_session("user:u1", "user")
            uuid.UUID(first)
            self.assertEqual(
                store.get_or_create_session("user:u1", "user"), first
            )
            other = store.get_or_create_session("user:u2", "user")
            self.assertNotEqual(first, other)
            store.close()

    def test_legacy_session_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "test.db"))
            store.claim_message("old-message", "old-chat")
            legacy = store.legacy_session_id("old-chat", "new-message")
            self.assertEqual(legacy, "feishu_old-chat")
            resolution = store.resolve_session("user:u1", "user", legacy)
            self.assertEqual(resolution.session_id, "feishu_old-chat")
            self.assertEqual(resolution.status, "migrated")

            with store._lock, store._conn:
                store._conn.execute(
                    "INSERT INTO sessions (chat_id, sequence, updated_at) "
                    "VALUES ('reset-chat', 3, 1)"
                )
            self.assertEqual(
                store.legacy_session_id("reset-chat", "new-message"),
                "feishu_reset-chat_3",
            )
            store.close()

    def test_reset_replaces_only_current_session_and_clears_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "test.db"))
            first = store.get_or_create_session("chat:c1", "chat")
            second = store.get_or_create_session("chat:c2", "chat")
            store.update_context_cursor("chat:c1", 100, "m1")
            reset = store.reset_session("chat:c1", "chat")
            uuid.UUID(reset)
            self.assertNotEqual(reset, first)
            self.assertEqual(
                store.get_or_create_session("chat:c2", "chat"), second
            )
            self.assertEqual(store.get_context_cursor("chat:c1"), (None, None))
            store.close()

    def test_concurrent_creation_returns_one_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "test.db"))
            with ThreadPoolExecutor(max_workers=8) as pool:
                values = list(
                    pool.map(
                        lambda _: store.get_or_create_session("user:u1", "user"),
                        range(30),
                    )
                )
            self.assertEqual(len(set(values)), 1)
            uuid.UUID(values[0])
            store.close()

    def test_mapping_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "test.db")
            store = Store(path)
            session_id = store.get_or_create_session("thread:c:t", "thread")
            store.close()
            reopened = Store(path)
            self.assertEqual(
                reopened.get_or_create_session("thread:c:t", "thread"),
                session_id,
            )
            reopened.close()


class MessageRoutingTests(unittest.TestCase):
    def test_private_group_and_thread_conversation_keys(self):
        private = IncomingMessage("m", "c", "p2p", "text", sender_open_id="u")
        group = IncomingMessage("m", "c", "group", "text", sender_open_id="u")
        thread = IncomingMessage(
            "m", "c", "group", "text", sender_open_id="u", thread_id="t"
        )
        root = IncomingMessage(
            "m", "c", "group", "text", sender_open_id="u", root_id="r"
        )
        self.assertEqual(resolve_conversation(private), ("user:u", "user"))
        self.assertEqual(resolve_conversation(group), ("chat:c", "chat"))
        self.assertEqual(
            resolve_conversation(thread), ("thread:c:t", "thread")
        )
        self.assertEqual(resolve_conversation(root), ("thread:c:r", "thread"))

    def test_private_message_requires_open_id(self):
        with self.assertRaises(ValueError):
            resolve_conversation(IncomingMessage("m", "c", "p2p", "text"))

    def test_parse_group_event_detects_bot_mention_and_sender(self):
        mention = SimpleNamespace(
            key="@_user_1",
            id=SimpleNamespace(open_id="ou_bot"),
            mentioned_type="bot",
            name="Costa",
        )
        message = SimpleNamespace(
            message_id="om_1",
            chat_id="oc_1",
            chat_type="group",
            message_type="text",
            content=json.dumps({"text": "@_user_1 你好"}),
            thread_id="omt_1",
            root_id="",
            create_time=1_700_000_000_000,
            mentions=[mention],
        )
        sender = SimpleNamespace(
            sender_type="user", sender_id=SimpleNamespace(open_id="ou_user")
        )
        parsed = parse_event(
            SimpleNamespace(event=SimpleNamespace(message=message, sender=sender)),
            "ou_bot",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.text, "你好")
        self.assertEqual(parsed.sender_open_id, "ou_user")
        self.assertTrue(parsed.bot_mentioned)
        self.assertEqual(parsed.create_time, 1_700_000_000)

    def test_group_prompt_uses_recent_messages_and_char_budget(self):
        messages = [
            GroupContextMessage("m1", 1_700_000_000, "甲", "u1", "先讨论受众"),
            GroupContextMessage("m2", 1_700_000_010, "乙", "u2", "再讨论页数"),
        ]
        prompt, chars = build_group_prompt("请汇总", messages, 8000)
        self.assertIn("甲：先讨论受众", prompt)
        self.assertIn("乙：再讨论页数", prompt)
        self.assertTrue(prompt.endswith("请汇总"))
        self.assertGreater(chars, 0)

    def test_group_history_request_filters_type_bot_current_and_thread(self):
        current = IncomingMessage(
            "current",
            "oc_1",
            "group",
            "text",
            sender_open_id="ou_1",
            thread_id="omt_1",
        )
        user_sender = SimpleNamespace(
            sender_type="user", id="ou_2", sender_name="同事"
        )
        bot_sender = SimpleNamespace(
            sender_type="app", id="ou_bot", sender_name="机器人"
        )

        def item(message_id, sender, text, thread="omt_1", msg_type="text"):
            return SimpleNamespace(
                message_id=message_id,
                deleted=False,
                msg_type=msg_type,
                sender=sender,
                thread_id=thread,
                root_id="",
                create_time=1_700_000_000_000,
                body=SimpleNamespace(content=json.dumps({"text": text})),
                mentions=[],
            )

        items = [
            item("m1", user_sender, "有效上下文"),
            item("m2", bot_sender, "机器人消息"),
            item("m3", user_sender, "其他话题", thread="omt_2"),
            item("current", user_sender, "当前问题"),
            item("m4", user_sender, "图片", msg_type="image"),
        ]

        class FakeMessageResource:
            def __init__(self):
                self.request = None

            def list(self, request):
                self.request = request
                return SimpleNamespace(
                    success=lambda: True,
                    code=0,
                    msg="success",
                    data=SimpleNamespace(items=items),
                )

        resource = FakeMessageResource()
        client = FeishuClient.__new__(FeishuClient)
        client.client = SimpleNamespace(
            im=SimpleNamespace(v1=SimpleNamespace(message=resource))
        )
        result = client.list_recent_group_messages(current, 20, 1800)
        self.assertEqual([entry.message_id for entry in result], ["m1"])
        self.assertEqual(result[0].text, "有效上下文")
        self.assertEqual(resource.request.container_id, "oc_1")
        self.assertEqual(resource.request.sort_type, "ByCreateTimeDesc")
        self.assertTrue(resource.request.with_sender_name)


class ConnectorRenderingTests(unittest.TestCase):
    def test_extract_langchain_reply(self):
        data = {
            "status": "completed",
            "result": {
                "messages": [
                    {"type": "human", "content": "问题"},
                    {"type": "ai", "content": "最终答案"},
                ]
            },
        }
        self.assertEqual(extract_reply_text(data), "最终答案")

    def test_extract_output_text(self):
        self.assertEqual(
            extract_reply_text(
                {"status": "success", "data": {"output_text": "完成"}}
            ),
            "完成",
        )

    def test_extract_coze_stream_answer(self):
        raw = '{"type":"answer","finish":false,"content":{"answer":"你好"}}'
        self.assertEqual(extract_stream_text(raw), "你好")
        self.assertEqual(
            extract_stream_text('{"type":"message_start","content":{}}'), ""
        )

    def test_merge_stream_delta_and_snapshot(self):
        self.assertEqual(merge_stream_text("你", "好"), "你好")
        self.assertEqual(merge_stream_text("你好", "你好，我是"), "你好，我是")
        self.assertEqual(merge_stream_text("你好", "好呀"), "你好呀")

    def test_message_rendering(self):
        self.assertEqual(_chunk_text("a" * 6001), ["a" * 3000, "a" * 3000, "a"])
        post = _to_post("下载：[文件](https://example.com/a.pptx)")
        self.assertEqual(post["zh_cn"]["content"][0][1]["tag"], "a")

    def test_streaming_card_has_no_visible_header_or_brand(self):
        spec = _streaming_card_spec()
        self.assertNotIn("header", spec)
        self.assertNotIn("Costa", json.dumps(spec, ensure_ascii=False))
        self.assertEqual(
            spec["body"]["elements"][0]["content"],
            "正在连接智能体，请稍候…",
        )

    def test_card_markdown_converts_only_plain_single_newlines(self):
        self.assertEqual(
            format_card_markdown("第一行\n第二行\n第三行"),
            "第一行<br>\n第二行<br>\n第三行",
        )
        self.assertEqual(
            format_card_markdown("第一段\n\n第二段"), "第一段\n\n第二段"
        )
        self.assertEqual(
            format_card_markdown("第一行<br>\n第二行"), "第一行<br>\n第二行"
        )

    def test_card_markdown_preserves_structured_blocks(self):
        structured = (
            "**标题**\n\n"
            "- 项目一\n- 项目二\n\n"
            "| 列一 | 列二 |\n| --- | --- |\n| A | B |\n\n"
            "```python\nprint(\"a\")\nprint(\"b\")\n```\n\n"
            "    indented code\n    second line\n\n"
            "> 引用\n正文"
        )
        self.assertEqual(format_card_markdown(structured), structured)

    def test_streaming_card_sequence(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def update_streaming_card(self, card_id, content, sequence):
                self.calls.append(("update", card_id, content, sequence))

            def finish_streaming_card(self, card_id, sequence):
                self.calls.append(("finish", card_id, sequence))

        client = FakeClient()
        card = StreamingCard(client, "card-1")
        card.update("你")
        card.finish("你好")
        self.assertEqual(client.calls[0], ("update", "card-1", "你", 1))
        self.assertEqual(client.calls[1], ("update", "card-1", "你好", 2))
        self.assertEqual(client.calls[2], ("finish", "card-1", 3))


class FakeCard:
    def __init__(self, fail_update=False, fail_finish=False):
        self.card_id = "card-1"
        self.message_id = "om-card"
        self.updates = []
        self.finished = []
        self.failed = []
        self.fail_update = fail_update
        self.fail_finish = fail_finish

    def update(self, content):
        if self.fail_update:
            raise CardOperationError("update", 1, "update failed")
        self.updates.append(content)

    def finish(self, content):
        if self.fail_finish:
            raise CardOperationError("finish", 2, "finish failed")
        self.finished.append(content)

    def fail(self, message):
        self.failed.append(message)


class FakeFeishu:
    def __init__(self, card=None, card_error=None, history=None):
        self.card = card or FakeCard()
        self.card_error = card_error
        self.history = history or []
        self.sent_texts = []

    def create_streaming_card(self, msg):
        if self.card_error:
            raise self.card_error
        return self.card

    def send_text(self, msg, text):
        self.sent_texts.append(text)

    def list_recent_group_messages(self, *args):
        return list(self.history)


class FakeCoze:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    async def stream(self, text, session_id, timeout):
        self.calls.append((text, session_id, timeout))
        for chunk in self.chunks:
            yield chunk


def make_connector(path, feishu, coze):
    connector = Connector.__new__(Connector)
    connector.settings = SimpleNamespace(
        database_path=path,
        task_timeout_seconds=30,
        ack_delay_seconds=999,
        group_context_enabled=True,
        group_context_max_messages=20,
        group_context_window_seconds=1800,
        group_context_max_chars=8000,
    )
    connector.store = Store(path)
    connector.feishu = feishu
    connector.coze = coze
    connector.loop = None
    connector._conversation_locks = {}
    return connector


class ConnectorFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_failure_continues_sse_and_sends_plain_text(self):
        with tempfile.TemporaryDirectory() as directory:
            feishu = FakeFeishu(
                card_error=CardOperationError("create", 1, "permission")
            )
            coze = FakeCoze(["你", "好"])
            connector = make_connector(
                str(Path(directory) / "test.db"), feishu, coze
            )
            msg = IncomingMessage(
                "m1", "c1", "p2p", "text", text="问题", sender_open_id="u1"
            )
            connector.store.claim_message(msg.message_id, msg.chat_id)
            await connector._handle_serial(msg, "user:u1")
            self.assertEqual(feishu.sent_texts, ["你好"])
            self.assertEqual(len(coze.calls), 1)
            uuid.UUID(coze.calls[0][1])
            connector.store.close()

    async def test_card_update_failure_falls_back_after_full_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            feishu = FakeFeishu(card=FakeCard(fail_update=True))
            coze = FakeCoze(["你", "好"])
            connector = make_connector(
                str(Path(directory) / "test.db"), feishu, coze
            )
            msg = IncomingMessage(
                "m1", "c1", "p2p", "text", text="问题", sender_open_id="u1"
            )
            connector.store.claim_message(msg.message_id, msg.chat_id)
            await connector._handle_serial(msg, "user:u1")
            self.assertEqual(feishu.sent_texts, ["你好"])
            self.assertEqual(len(coze.calls), 1)
            connector.store.close()

    async def test_successful_card_does_not_send_duplicate_text(self):
        with tempfile.TemporaryDirectory() as directory:
            card = FakeCard()
            feishu = FakeFeishu(card=card)
            coze = FakeCoze(["你", "好"])
            connector = make_connector(
                str(Path(directory) / "test.db"), feishu, coze
            )
            msg = IncomingMessage(
                "m1", "c1", "p2p", "text", text="问题", sender_open_id="u1"
            )
            connector.store.claim_message(msg.message_id, msg.chat_id)
            await connector._handle_serial(msg, "user:u1")
            self.assertEqual(feishu.sent_texts, [])
            self.assertEqual(card.updates[0], "你")
            self.assertEqual(card.finished, ["你好"])
            connector.store.close()

    async def test_group_history_is_added_and_cursor_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            history = [
                GroupContextMessage(
                    "old", 1_700_000_000, "同事", "u2", "受众是新员工"
                )
            ]
            feishu = FakeFeishu(history=history)
            coze = FakeCoze(["收到"])
            connector = make_connector(
                str(Path(directory) / "test.db"), feishu, coze
            )
            msg = IncomingMessage(
                "m1",
                "c1",
                "group",
                "text",
                text="请继续",
                sender_open_id="u1",
                bot_mentioned=True,
                create_time=1_700_000_100,
            )
            connector.store.claim_message(msg.message_id, msg.chat_id)
            await connector._handle_serial(msg, "chat:c1")
            self.assertIn("同事：受众是新员工", coze.calls[0][0])
            self.assertTrue(coze.calls[0][0].endswith("请继续"))
            self.assertEqual(
                connector.store.get_context_cursor("chat:c1"),
                (1_700_000_100, "m1"),
            )
            connector.store.close()


class CozeStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_sse_answer_events(self):
        body = (
            "event: message\n"
            'data: {"type":"message_start","content":{}}\n\n'
            "event: message\n"
            'data: {"type":"answer","content":{"answer":"你"}}\n\n'
            "event: message\n"
            'data: {"type":"answer","content":{"answer":"好"}}\n\n'
        )

        async def handler(request):
            self.assertEqual(request.url.path, "/stream_run")
            payload = json.loads(request.content)
            self.assertEqual(payload["session_id"], "session-1")
            self.assertEqual(
                payload["content"]["query"]["prompt"][0]["content"]["text"],
                "你好",
            )
            return httpx.Response(200, text=body)

        client = CozeClient("https://example.test", "token", 1)
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="https://example.test",
            transport=httpx.MockTransport(handler),
        )
        chunks = [chunk async for chunk in client.stream("你好", "session-1", 30)]
        await client.close()
        self.assertEqual(chunks, ["你", "好"])


if __name__ == "__main__":
    unittest.main()
