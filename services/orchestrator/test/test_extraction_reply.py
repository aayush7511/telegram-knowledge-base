"""telegram.format_extraction_reply — the reply listing what a save put into
memory (specs/extraction-reply.md, tests 1–9c). Pure function, no network."""
import html
import re

from extract import ResponseObject
from telegram import format_extraction_reply

RO = ResponseObject(url="https://ex.com/post", title="Agent memory", author="Jane", sitename="Ex", text="body")
ENTITIES = ["Zep", "Graphiti"]
FACTS = ["Zep built Graphiti.", "Graphiti uses FalkorDB."]


def visible(msg: str) -> str:
    """What Telegram shows (and counts toward its 4,096 limit): tags stripped, entities decoded."""
    return html.unescape(re.sub(r"<[^>]+>", "", msg))


def names(prefix: str, n: int) -> list[str]:
    return [f"{prefix}-{i:02d}" for i in range(n)]


# --- 1, 2: layout ----------------------------------------------------------

def test_reply_shows_header_entities_and_facts():
    msg = format_extraction_reply(RO, ENTITIES, FACTS)

    assert "<b>Agent memory</b>" in msg
    assert "Jane" in msg and "Ex" in msg
    assert 'href="https://ex.com/post"' in msg
    assert "Zep, Graphiti" in msg
    assert "• Zep built Graphiti." in msg and "• Graphiti uses FalkorDB." in msg
    # header, then entities, then facts
    assert msg.index("Agent memory") < msg.index("<b>Entities</b>") < msg.index("<b>Facts</b>")


def test_text_note_reply_has_no_header():
    msg = format_extraction_reply(None, ENTITIES, FACTS)

    assert msg.startswith("<b>Entities</b>")
    assert "href" not in msg


# --- 3, 4, 5: caps ---------------------------------------------------------

def test_caps_entities_at_15_with_more():
    msg = format_extraction_reply(None, names("ent", 20), [])

    for name in names("ent", 15):
        assert name in msg
    assert "ent-15" not in msg
    assert "+5 more" in msg


def test_caps_facts_at_10_with_more():
    msg = format_extraction_reply(None, [], names("fact", 13))

    assert msg.count("• ") == 10
    assert "fact-09" in msg and "fact-10" not in msg
    assert "+3 more" in msg


def test_no_more_line_at_exact_cap():
    msg = format_extraction_reply(None, names("ent", 15), names("fact", 10))

    assert "more" not in msg
    assert msg.count("• ") == 10


# --- 6, 7: empty sections --------------------------------------------------

def test_empty_section_omitted():
    msg = format_extraction_reply(None, ENTITIES, [])

    assert "<b>Entities</b>" in msg
    assert "Facts" not in msg


def test_nothing_extracted():
    msg = format_extraction_reply(None, [], [])

    assert "Saved — nothing extracted" in msg
    assert "Entities" not in msg and "Facts" not in msg


def test_nothing_extracted_keeps_the_header():
    msg = format_extraction_reply(RO, [], [])

    assert "<b>Agent memory</b>" in msg
    assert msg.index("Agent memory") < msg.index("Saved — nothing extracted")


# --- 8: escaping -----------------------------------------------------------

def test_escapes_html():
    ro = ResponseObject(url="https://ex.com/a?x=1&y=2", title="A <b> & C", text="body")
    msg = format_extraction_reply(ro, ["<script>"], ["Tom & Jerry <3"])

    assert "<script>" not in msg and "&lt;script&gt;" in msg
    assert "Tom &amp; Jerry &lt;3" in msg
    assert "A &lt;b&gt; &amp; C" in msg


# --- 9, 9a, 9b, 9c: limits, duplicates, truncation --------------------------

def test_reply_under_telegram_limit():
    ro = ResponseObject(url="https://ex.com/" + "p" * 5000, title="t" * 1000, author="a" * 500, sitename="s", text="body")
    msg = format_extraction_reply(ro, ["e" * 1000 + str(i) for i in range(40)], ["f" * 2000 + str(i) for i in range(40)])

    assert len(visible(msg)) < 4096


def test_duplicates_removed_before_cap():
    msg = format_extraction_reply(None, ["Zep", "zep ", "Graphiti"], ["Zep built Graphiti.", " zep built graphiti. "])

    assert "Zep, Graphiti" in msg
    assert "zep " not in msg
    assert msg.count("• ") == 1

    # 20 entities, 5 of them repeats → 15 unique, all shown, nothing cut
    entities = names("ent", 15) + [n.upper() for n in names("ent", 5)]
    msg = format_extraction_reply(None, entities, [])
    for name in names("ent", 15):
        assert name in msg
    assert "more" not in msg


def test_long_entity_and_fact_truncated():
    msg = format_extraction_reply(None, ["a" * 100], ["b" * 500])

    assert "a" * 59 + "…" in msg and "a" * 60 not in msg
    assert "b" * 199 + "…" in msg and "b" * 200 not in msg


def test_items_at_the_limit_are_not_truncated():
    msg = format_extraction_reply(None, ["a" * 60], ["b" * 200])

    assert "a" * 60 in msg and "…" not in msg
    assert "b" * 200 in msg


def test_full_caps_with_max_length_items_fit():
    entities = [f"{i:02d}" + "x" * 98 for i in range(15)]
    facts = [f"{i:02d}" + "y" * 498 for i in range(10)]
    ro = ResponseObject(url="https://ex.com/" + "p" * 3000, title="T" * 300, author="Jane", sitename="Ex", text="body")
    msg = format_extraction_reply(ro, entities, facts)

    assert len(visible(msg)) < 4096
    for i in range(15):
        assert f"{i:02d}" + "x" * 57 + "…" in msg
    for i in range(10):
        assert f"{i:02d}" + "y" * 197 + "…" in msg
    assert "more" not in msg
    assert 'href="https://ex.com/' + "p" * 3000 + '"' in msg  # the link target stays whole
