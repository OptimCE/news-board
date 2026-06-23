"""Server-side Markdown rendering with a single, trusted sanitisation boundary.

`POST.post` is stored as Markdown source (the source of truth). On read it is
rendered to HTML with raw HTML **disabled** (`markdown-it-py`) and the output is
sanitised against a strict allow-list (`nh3`). There is no `bypassSecurityTrust`
anywhere near this path; the frontend binds the already-sanitised HTML. Rendering
happens on read (no cache in V1; a rendered-HTML cache lands in V2 with email).

The enabled constructs mirror exactly what the Crepe WYSIWYG editor can emit:
headings, paragraphs, bold/italic/strikethrough/inline-code, links, bullet/ordered/
task lists, blockquotes, fenced code and horizontal rules. Strikethrough and task
lists are GFM extensions; everything else is core CommonMark. (Images are not
insertable in the editor but legacy posts may contain them, so they stay.)
"""

import nh3
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

# CommonMark with raw HTML disabled, plus the two GFM constructs the editor emits
# that CommonMark lacks: strikethrough (``~~x~~`` -> ``<s>``) and task lists
# (``- [ ]`` / ``- [x]``). ``html=False`` keeps any literal HTML in the *source*
# escaped; the tasklists plugin still injects its ``<input>`` as a post-parse token,
# which the renderer emits raw and nh3 then vets. linkify/typographer stay off — the
# editor produces explicit ``[text](url)`` links.
_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
_md.enable("strikethrough")
_md.use(tasklists_plugin)  # enabled=False -> read-only disabled checkboxes, no <label>

# Tags markdown-it (+ the tasklists plugin) can emit. Everything else is dropped.
_ALLOWED_TAGS: set[str] = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "em",
    "strong",
    "s",
    "del",
    "a",
    "img",
    "input",
}

_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title"},
    # GFM task lists: the disabled checkbox plus the classes the renderer marks
    # the list (``contains-task-list``) and items (``task-list-item``) with.
    "input": {"type", "checked", "disabled", "class"},
    "ul": {"class"},
    "ol": {"class"},
    "li": {"class"},
    # Fenced-code language hint (``class="language-*"``) the renderer may add.
    "pre": {"class"},
    "code": {"class"},
}

_URL_SCHEMES: set[str] = {"http", "https", "mailto"}

# rel hardening applied to every rendered link; ``target="_blank"`` is force-added so
# external links open in a new tab without leaking the referrer or opener.
_LINK_REL: str = "nofollow noopener noreferrer ugc"
_SET_TAG_ATTRIBUTE_VALUES: dict[str, dict[str, str]] = {"a": {"target": "_blank"}}


def render_markdown(source: str) -> str:
    """Render Markdown source to sanitised HTML safe for direct binding."""
    html = _md.render(source or "")
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes=_URL_SCHEMES,
        link_rel=_LINK_REL,
        set_tag_attribute_values=_SET_TAG_ATTRIBUTE_VALUES,
    )
