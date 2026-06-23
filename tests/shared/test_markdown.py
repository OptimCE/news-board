"""Unit tests for the Markdown render + sanitise boundary (``shared/markdown.py``).

These exercise ``render_markdown`` directly (a pure function, no DB): the full set of
constructs the Crepe editor can emit must survive rendering + nh3, links must be
hardened, and no XSS vector may get through.
"""

from typing import cast

from shared.markdown import render_markdown

# The complete construct set the editor can emit (the task's reference fixture).
_FIXTURE = """\
# Heading one
## Heading two
### Heading three

A paragraph with **bold**, _italic_, ~~struck~~ and `inline code`, plus a
[link](https://example.com).

- bullet one
- bullet two

1. step one
2. step two

- [ ] todo
- [x] done

> A blockquote.

```
code block
```

---
"""


def test_renders_every_editor_construct():
    html = render_markdown(_FIXTURE)
    assert "<h1>Heading one</h1>" in html
    assert "<h2>Heading two</h2>" in html
    assert "<h3>Heading three</h3>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<s>struck</s>" in html  # GFM strikethrough, not literal ~~
    assert "<code>inline code</code>" in html
    assert "<ul>" in html
    assert "<ol>" in html
    assert "<blockquote>" in html
    assert "<pre><code>" in html
    assert "<hr" in html


def test_strikethrough_is_not_literal():
    html = render_markdown("~~gone~~")
    assert "<s>gone</s>" in html
    assert "~~" not in html


def test_task_list_renders_disabled_checkboxes():
    html = render_markdown("- [ ] todo\n- [x] done\n")
    assert html.count("<input") == 2
    assert 'type="checkbox"' in html
    assert "disabled" in html  # read-only
    assert "checked" in html  # the "done" item
    assert "contains-task-list" in html  # class preserved for styling
    assert "[ ]" not in html  # marker consumed, not rendered literally
    assert "[x]" not in html


def test_links_are_hardened():
    html = render_markdown("[site](https://example.com)")
    assert 'href="https://example.com"' in html
    assert 'rel="nofollow noopener noreferrer ugc"' in html
    assert 'target="_blank"' in html


def test_javascript_url_never_becomes_a_live_link():
    # markdown-it rejects the scheme at parse time (the source stays inert text), and
    # even if it didn't, nh3's url_schemes allow-list would drop the href. Either way
    # there is no executable link.
    html = render_markdown("[click](javascript:alert(1))")
    assert 'href="javascript' not in html


def test_disallowed_scheme_is_stripped_by_sanitizer():
    # markdown-it permits data:image/* as an <img src>; nh3 (http/https/mailto only)
    # must strip it, proving the sanitiser drops schemes the renderer would allow.
    html = render_markdown("![x](data:image/png;base64,iVBORw0KGgo=)")
    assert "<img" in html  # the element survives...
    assert "data:" not in html  # ...but the disallowed src is gone
    assert "src=" not in html


def test_raw_html_in_source_is_escaped_not_executed():
    html = render_markdown("<script>alert(1)</script>")
    assert "<script" not in html  # never a live element
    assert "&lt;script&gt;" in html  # neutralised to inert text


def test_fenced_code_language_class_preserved():
    html = render_markdown("```python\nprint(1)\n```")
    assert 'class="language-python"' in html


def test_legacy_image_still_renders():
    html = render_markdown("![alt](https://example.com/x.png)")
    assert "<img" in html
    assert 'src="https://example.com/x.png"' in html


def test_soft_break_is_not_br_and_blank_line_splits_paragraphs():
    html = render_markdown("line one\nline two\n\npara two")
    assert "<br" not in html  # single newline is a soft break, not a hard break
    assert html.count("<p>") == 2  # blank line separates paragraphs


def test_empty_and_none_render_to_empty_string():
    assert render_markdown("") == ""
    # The ``source or ""`` guard tolerates a None body defensively (off-contract).
    assert render_markdown(cast(str, None)) == ""
