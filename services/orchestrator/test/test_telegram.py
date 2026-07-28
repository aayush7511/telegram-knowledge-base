"""Telegram formatter layout + sendMessage wiring (mocked HTTP client)."""
import asyncio

from extract import ResponseObject
from telegram import format_message, send_summary


def test_format_message_full_layout():
    ro = ResponseObject(
        url="https://ex.com/a",
        title="Hello & Co",
        author="Jane",
        sitename="Ex",
        text="body",
        comments="c" * 400,
        summary="A concise summary.",
    )
    msg = format_message(ro)
    assert "<b>Hello &amp; Co</b>" in msg  # HTML-escaped and bold
    assert "Jane" in msg and "Ex" in msg
    assert "A concise summary." in msg
    assert 'href="https://ex.com/a"' in msg
    assert "…" in msg  # long comments truncated


def test_format_message_minimal_url_only():
    msg = format_message(ResponseObject(url="https://ex.com/a"))
    assert 'href="https://ex.com/a"' in msg


def test_send_summary_threads_reply():
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    class FakeClient:
        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResp()

    ro = ResponseObject(url="https://ex.com/a", title="T", summary="S")
    asyncio.run(send_summary(99, 7, ro, token="TOK", client=FakeClient()))

    assert "botTOK/sendMessage" in captured["url"]
    assert captured["json"]["chat_id"] == 99
    assert captured["json"]["reply_to_message_id"] == 7
    assert captured["json"]["parse_mode"] == "HTML"
