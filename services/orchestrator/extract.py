"""Body-text + guaranteed-metadata extraction from rendered HTML.

Trafilatura gives us the clean article body, but on many pages it misses
`author` and `sitename`. extruct fills those from whatever structured metadata
the page actually publishes, tried in descending reliability:

    JSON-LD  →  microdata  →  RDFa  →  OpenGraph

first non-empty value wins per field, with the URL hostname as a last-resort
`sitename` so that field is never empty. This is the "guarantee title/author/
sitename" work from the architecture diagram.

`extract_content` is pure over `(html, url)` — no network, no browser — so it
unit-tests against saved HTML fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import extruct
import trafilatura

# Schema.org @types whose `name` is an entity label (org/person/site), NOT the
# page title — so we never mistake a publisher name for the headline.
_NON_TITLE_TYPES = {"Organization", "Person", "WebSite", "ImageObject", "Brand"}


@dataclass
class ResponseObject:
    """The assembled result for one blog URL. `summary` is filled downstream."""

    url: str
    title: str | None = None
    author: str | None = None
    sitename: str | None = None
    text: str = ""
    comments: str = ""
    summary: str | None = None


def extract_content(html: str, url: str) -> ResponseObject:
    """Extract body text (Trafilatura) + title/author/sitename (extruct cascade)."""
    text, comments, tf_title = _trafilatura_body(html, url)
    title, author, sitename = _cascade_metadata(html, url)
    return ResponseObject(
        url=url,
        title=title or tf_title,
        author=author,
        sitename=sitename or _hostname(url),
        text=text,
        comments=comments,
    )


# --- Trafilatura body -------------------------------------------------------

def _trafilatura_body(html: str, url: str) -> tuple[str, str, str | None]:
    try:
        doc = trafilatura.bare_extraction(html, url=url, with_metadata=True)
    except Exception:
        doc = None
    if not doc:
        return "", "", None
    # bare_extraction returns a Document object (attrs) in current versions and
    # a plain dict in older ones — support both.
    get = doc.get if isinstance(doc, dict) else (lambda k: getattr(doc, k, None))
    return (get("text") or "", get("comments") or "", get("title"))


# --- extruct metadata cascade ----------------------------------------------

def _cascade_metadata(html: str, url: str) -> tuple[str | None, str | None, str | None]:
    title = author = sitename = None

    try:
        structured = extruct.extract(
            html, base_url=url, syntaxes=["json-ld", "microdata", "rdfa"], uniform=True
        )
    except Exception:
        structured = {}

    # uniform=True normalizes all three into schema.org-shaped dicts, so one
    # reader handles them; the cascade is just the iteration order.
    for syntax in ("json-ld", "microdata", "rdfa"):
        for obj in _iter_objects(structured.get(syntax)):
            title = title or _obj_title(obj)
            author = author or _obj_author(obj)
            sitename = sitename or _obj_sitename(obj)
        if title and author and sitename:
            return title, author, sitename

    # OpenGraph fallback — flat og:*/article:* keys, read raw for reliability.
    og = _opengraph(html, url)
    return (
        title or og.get("title"),
        author or og.get("author"),
        sitename or og.get("site_name"),
    )


def _iter_objects(items):
    """Yield schema.org dicts, flattening any @graph containers."""
    for item in items or []:
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        if isinstance(graph, list):
            for sub in graph:
                if isinstance(sub, dict):
                    yield sub
        yield item


def _type_of(obj: dict) -> set[str]:
    t = obj.get("@type") or obj.get("type")
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return set()


def _obj_title(obj: dict) -> str | None:
    headline = obj.get("headline")
    if isinstance(headline, str) and headline.strip():
        return headline.strip()
    name = obj.get("name")
    if isinstance(name, str) and name.strip() and not (_type_of(obj) & _NON_TITLE_TYPES):
        return name.strip()
    return None


def _obj_author(obj: dict) -> str | None:
    return _name_of(obj.get("author"))


def _obj_sitename(obj: dict) -> str | None:
    pub = _name_of(obj.get("publisher"))
    if pub:
        return pub
    if _type_of(obj) & {"WebSite"}:
        name = obj.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return _name_of((obj.get("isPartOf") or {})) if isinstance(obj.get("isPartOf"), dict) else None


def _name_of(value) -> str | None:
    """Pull a display name from a schema.org value: str, {name:..}, or a list."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _name_of(value.get("name"))
    if isinstance(value, list):
        for v in value:
            name = _name_of(v)
            if name:
                return name
    return None


def _opengraph(html: str, url: str) -> dict:
    try:
        blocks = extruct.extract(html, base_url=url, syntaxes=["opengraph"]).get("opengraph", [])
    except Exception:
        blocks = []
    props: dict[str, str] = {}
    for block in blocks:
        for key, value in block.get("properties", []):
            if key not in props and isinstance(value, str):
                props[key] = value
    # article:author is frequently a profile URL, not a name — drop those.
    author = props.get("article:author") or props.get("og:author")
    if author and author.startswith(("http://", "https://")):
        author = None
    return {
        "title": props.get("og:title"),
        "site_name": props.get("og:site_name"),
        "author": author,
    }


def _hostname(url: str) -> str | None:
    host = urlparse(url).hostname
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host
