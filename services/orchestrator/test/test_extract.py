"""extract_content cascade: JSON-LD → microdata → rdfa → opengraph → hostname."""
from extract import extract_content

JSONLD = """<html><head><title>Fallback Title</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Article","headline":"The Real Headline",
 "author":{"@type":"Person","name":"Jane Doe"},
 "publisher":{"@type":"Organization","name":"Example News"}}
</script></head>
<body><article><h1>The Real Headline</h1>
<p>Body paragraph one with enough words to be considered real content by the extractor engine here.</p>
<p>Second paragraph continues the article body text so trafilatura keeps it.</p></article></body></html>"""

OG_ONLY = """<html><head><title>OG Page</title>
<meta property="og:title" content="OG Title Here"/>
<meta property="og:site_name" content="OG Site"/>
</head><body><article>
<p>Some article body text that is long enough to be extracted as the main content of the page by trafilatura reliably.</p>
</article></body></html>"""

NONE = """<html><head><title>Bare Page</title></head>
<body><article>
<p>Just body text here with no structured metadata at all, but long enough to be pulled out as the main content by the extractor.</p>
</article></body></html>"""


def test_jsonld_populates_all_three():
    ro = extract_content(JSONLD, "https://example.com/news/story")
    assert ro.title == "The Real Headline"
    assert ro.author == "Jane Doe"
    assert ro.sitename == "Example News"
    assert len(ro.text) > 50


def test_opengraph_fallback_no_author():
    ro = extract_content(OG_ONLY, "https://www.blogsite.org/post/1")
    assert ro.title == "OG Title Here"
    assert ro.sitename == "OG Site"
    assert ro.author is None  # OG carries no real author name here


def test_hostname_fallback_when_no_metadata():
    ro = extract_content(NONE, "https://myblog.net/entry")
    assert ro.sitename == "myblog.net"  # last-resort hostname (www stripped)
    assert ro.author is None
    assert ro.title == "Bare Page"  # trafilatura <title> fallback
    assert ro.text
