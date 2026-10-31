"""Conservative, offset-based prose editing; never regenerate a LaTeX document."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.models import LatexChange

MAX_SOURCE_BYTES = 512 * 1024
MAX_SPANS = 160
ACTION_VERBS = {"designed", "developed", "built", "implemented", "contributed", "worked", "created", "maintained", "added", "improved", "optimized", "processed", "visualized", "integrated", "enabled", "secured", "applied", "wrote", "led", "owned", "automated", "deployed", "reduced", "supported", "delivered", "engineered", "collaborated"}
# These formatting arguments are deliberately immutable (including skill names).
# Only text directly inside a supported bullet is editable.
TOKEN = re.compile(r"%[^\r\n]*|\\(?:[A-Za-z@]+\*?|[^\r\n])|[{}]|[^\\%{}]+")
BULLET_MACROS = {r"\resumeItem", r"\resumeSubItem"}
QUALIFIERS = re.compile(r"\b(?:familiar(?:ity)?|basic|beginner|intermediate|advanced|exposure|learning|assisted|contributed|internal|customer[- ]facing|on[- ]prem(?:ises)?|prototype)\b", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*(?:[kKmMbB]|st|nd|rd|th)?\+?")
# Keep technical names visible to the model but immutable in every edited span.
TECH = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*(?:[./+#-][A-Za-z0-9]+)*[+#]*|[A-Za-z]*[A-Z][A-Z][A-Za-z0-9]*|[A-Za-z]+[+#]{1,2})(?!\w)")


@dataclass(frozen=True)
class TextSpan:
    id: str
    start: int
    end: int
    text: str
    context: str


def decode_source(data: bytes) -> str:
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Upload a nonempty .tex file up to 512 KB.")
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Save the LaTeX source as UTF-8 before uploading.") from exc
    if "\x00" in source or not re.search(r"\\begin\s*\{document\}", source):
        raise ValueError("Upload a complete LaTeX document containing \\begin{document}.")
    return source


def editable_spans(source: str) -> list[TextSpan]:
    """Find direct prose in resumeItem, resumeSubItem, and ordinary item bodies.

    Commands, their arguments, comments, math, skills lists, and all content
    outside the document body stay immutable. Unsupported constructs are skipped.
    """
    tokens = list(TOKEN.finditer(source))
    # Find the real body using tokens so commented-out begin/end markers cannot
    # activate commented content or the preamble's macro definitions.
    masked = TOKEN.sub(lambda m: " " * len(m.group()) if m.group().startswith("%") else m.group(), source)
    body_start = masked.find(r"\begin{document}")
    body_end = masked.rfind(r"\end{document}")
    if body_start < 0 or body_end < body_start:
        raise ValueError("Use literal \\begin{document} and \\end{document} markers.")
    # Resolve complete bullet contexts before locating individual prose leaves.
    # Braces inside comments/escaped control symbols are already single tokens.
    brace_stack = []
    brace_ends = {}
    for token in tokens:
        if token.group() == "{":
            brace_stack.append(token.start())
        elif token.group() == "}" and brace_stack:
            brace_ends[brace_stack.pop()] = token.end()
    regions = []
    next_boundaries = {}
    next_boundary = body_end
    for index in range(len(tokens) - 1, -1, -1):
        next_boundaries[index] = next_boundary
        if tokens[index].group() in BULLET_MACROS | {r"\item", r"\end", r"\section"}:
            next_boundary = tokens[index].start()
    for index, token in enumerate(tokens):
        if not body_start < token.start() < body_end:
            continue
        if token.group() in BULLET_MACROS:
            for next_index in range(index + 1, len(tokens)):
                following = tokens[next_index]
                if following.group().isspace() or following.group().startswith("%"):
                    continue
                if following.group() == "{" and following.start() in brace_ends:
                    regions.append((following.end(), brace_ends[following.start()] - 1))
                break
        elif token.group() == r"\item":
            end = next_boundaries[index]
            regions.append((token.end(), end))
    depth = 0
    bullet_depth = None
    pending_bullet = False
    ordinary_item = False
    spans = []
    math = False
    for token in tokens:
        if token.start() < body_start + len(r"\begin{document}") or token.start() >= body_end:
            continue
        value = token.group()
        if value.startswith("%"):
            continue
        if value in {r"\(", r"\["}:
            math = True
            continue
        if value in {r"\)", r"\]"}:
            math = False
            continue
        if "$" in value:
            if len(re.findall(r"\$\$|\$", value)) % 2:
                math = not math
            continue
        if math:
            continue
        if value in BULLET_MACROS:
            pending_bullet = True
            ordinary_item = False
            continue
        if value == r"\item":
            # Grouped skill lists are skipped below because their direct prose
            # contains no sentence. Simple itemize prose is eligible.
            ordinary_item = True
            bullet_depth = depth
            pending_bullet = False
            continue
        if value == "{":
            depth += 1
            if pending_bullet:
                bullet_depth = depth
                pending_bullet = False
            continue
        if value == "}":
            if bullet_depth is not None and depth == bullet_depth and not ordinary_item:
                bullet_depth = None
            depth -= 1
            continue
        if value.startswith("\\"):
            if value in {r"\end", r"\section", r"\subsection", r"\resumeItemListEnd", r"\resumeSubHeadingListEnd"}:
                ordinary_item = False
                bullet_depth = None
            continue
        if bullet_depth is None or depth != bullet_depth:
            continue
        # Dollar-delimited math and alignment/tabular content are never edited.
        if any(c in value for c in "$&#[]"):
            continue
        leading = len(value) - len(value.lstrip())
        text = value.strip()
        if len(text) < 45 or len(text.split()) < 7:
            continue
        first_word = re.match(r"[A-Za-z]+", text)
        if first_word and first_word.group()[0].isupper() and first_word.group().casefold() not in ACTION_VERBS:
            continue
        # Skills/technology lists, dates, ratings, and headings are not prose.
        if text.casefold().startswith(("technologies", "tools", "skills")) or ":" in text:
            continue
        start = token.start() + leading
        # Give the entire sentence/bullet, including protected formatting, so a
        # prose leaf is not mistaken for an incomplete sentence to be completed.
        context_start, context_end = next(((a, b) for a, b in regions if a <= start < b), (start, token.end()))
        context = source[context_start:context_end]
        spans.append(TextSpan(f"text-{len(spans)}", start, start + len(text), text, context))
    if len(spans) > MAX_SPANS:
        raise ValueError("This source has too many editable passages. Use a shorter resume.")
    return spans


def validate_change(before: str, after: str) -> None:
    if not after.strip() or after != after.strip():
        raise ValueError("A replacement must contain nonempty text without outer whitespace.")
    if any(c in after for c in "\\{}%$&#_^~\r\n\x00"):
        raise ValueError("Replacements must be plain prose without LaTeX commands or special characters.")
    if len(after) > len(before) * 1.15 + 8 or len(after) < len(before) * 0.65:
        raise ValueError("A replacement changed the passage length too much.")
    if Counter(NUMBER.findall(before)) != Counter(NUMBER.findall(after)):
        raise ValueError("A replacement changed a metric or number.")
    if Counter(m.group().casefold() for m in QUALIFIERS.finditer(before)) != Counter(m.group().casefold() for m in QUALIFIERS.finditer(after)):
        raise ValueError("A replacement changed a proficiency or scope qualifier.")
    # Sentence-initial action verbs may change; other capitalized tokens (e.g.
    # Python, Workday, SQL) must remain. This is deliberately conservative.
    def names(text):
        return Counter(m.group() for m in TECH.finditer(text) if m.start() > 0 or m.group().casefold() not in ACTION_VERBS)
    if names(before) != names(after):
        raise ValueError("A replacement changed a named technology or proper noun.")


def apply_changes(source: str, changes: list[LatexChange]) -> str:
    spans = {span.id: span for span in editable_spans(source)}
    selected = []
    seen = set()
    for change in changes:
        if change.id in seen or change.id not in spans:
            raise ValueError("A change references an unknown or duplicate passage.")
        seen.add(change.id)
        span = spans[change.id]
        if change.before != span.text:
            raise ValueError("The source changed since the proposal. Generate suggestions again.")
        validate_change(span.text, change.after)
        selected.append((span, change.after))
    result = source
    for span, replacement in sorted(selected, key=lambda item: item[0].start, reverse=True):
        result = result[:span.start] + replacement + result[span.end:]
    return result
