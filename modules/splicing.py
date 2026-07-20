"""Splicing compiled fragments into vanilla text: single-line block expansion,
flat-abort normalization, reindentation, injection, and EOF brace balancing.
"""
import re
from modules.paradox_text import (
    _skip_string, _skip_comment, _match_closing_brace, _is_word_char,
    _iter_named_blocks, _iter_top_level_blocks, _in_comment_or_string,
    _SL_TOKEN,
)

_WS = " \t\r\n"


def _reflow_single_line_body(inner, base_indent):
    toks = _SL_TOKEN.findall(inner)
    if not toks:
        return None
    lines = []
    indent = 1
    cur = []

    def flush():
        if cur:
            lines.append(base_indent + ('\t' * indent) + ' '.join(cur))
            cur.clear()

    for t in toks:
        if t == '{':
            cur.append('{')
            flush()
            indent += 1
        elif t == '}':
            flush()
            indent -= 1
            lines.append(base_indent + ('\t' * indent) + '}')
        else:
            cur.append(t)
            if len(cur) == 3:
                flush()
    flush()
    return '\n'.join(lines)


_WS = " \t\r\n"


def expand_single_line_blocks_multi(text, names):
    """Expand every single-line `name = { ... }` block for ALL given names in
    ONE pass. Replaces calling expand_single_line_blocks once per name, which
    was O(text x names) with a per-character Python scan (the profiler hot spot:
    ~125M _is_word_char calls). A compiled regex locates `name = {` candidates
    at C speed; comment/string false positives are filtered per match.

    Behaviourally identical to applying the single-name version sequentially
    (verified byte-for-byte over randomized inputs and edge cases).
    """
    names = [n for n in names if n]
    if not names:
        return text
    # Longest-first alternation so `decision_5` wins over `decision`.
    alt = "|".join(re.escape(n) for n in sorted(set(names), key=len, reverse=True))
    pat = re.compile(r"\b(" + alt + r")\b[ \t\r\n]*=[ \t\r\n]*\{")

    out = []
    pos = 0
    for m in pat.finditer(text):
        start = m.start()
        line_start = text.rfind('\n', 0, start) + 1
        # Skip a match that sits inside a comment or a string on its line.
        if _in_comment_or_string(text, line_start, start):
            continue
        open_pos = m.end()                      # index just after '{'
        try:
            close_pos = _match_closing_brace(text, open_pos)
        except ValueError:
            continue
        block_text = text[open_pos:close_pos]
        if '\n' in block_text:                  # multi-line already; leave as-is
            continue
        name = m.group(1)
        base_indent = text[line_start:start]
        body = _reflow_single_line_body(block_text.strip(), base_indent)
        out.append(text[pos:start])
        if body is not None:
            out.append(f"{name} = {{\n{body}\n{base_indent}}}")
        else:
            out.append(f"{name} = {{\n{base_indent}}}")
        pos = close_pos + 1
    out.append(text[pos:])
    return "".join(out)


def expand_single_line_blocks(text, name):
    out = []
    i = 0
    n = len(text)
    nlen = len(name)
    while i < n:
        c = text[i]
        if c == '#':
            j = _skip_comment(text, i)
            out.append(text[i:j]); i = j; continue
        if c == '"':
            j = _skip_string(text, i)
            out.append(text[i:j]); i = j; continue
        if not _is_word_char(text, i - 1) \
                and text.startswith(name, i) \
                and not _is_word_char(text, i + nlen):
            j = i + nlen
            k = j
            while k < n and text[k] in ' \t\r\n':
                k += 1
            if k < n and text[k] == '=':
                k += 1
                while k < n and text[k] in ' \t\r\n':
                    k += 1
                if k < n and text[k] == '{':
                    open_pos = k + 1
                    close_pos = _match_closing_brace(text, open_pos)
                    block_text = text[open_pos:close_pos]
                    if '\n' not in block_text:
                        line_start = text.rfind('\n', 0, i) + 1
                        base_indent = text[line_start:i]
                        body = _reflow_single_line_body(block_text.strip(), base_indent)
                        if body is not None:
                            out.append(f"{name} = {{\n{body}\n{base_indent}}}")
                        else:
                            out.append(f"{name} = {{\n{base_indent}}}")
                        i = close_pos + 1
                        continue
            out.append(text[i:j]); i = j; continue
        out.append(c); i += 1
    return ''.join(out)


def _normalize_flat_aborts(text):
    """Wrap any flat `abort = { ... }` (a top-level plan block whose abort has no
    direct OR child) into `abort = { OR = { ... } }`, so an include that
    navigates abort:/OR: can add a branch. OR-form and missing aborts are left
    as-is. Operates on an in-memory copy only. Applied bottom-up so offsets stay
    valid."""
    edits = []
    for name, o, c in _iter_top_level_blocks(text):
        ablocks = list(_iter_named_blocks(text, "abort", o, c))
        if not ablocks:
            continue
        ao, ac = ablocks[0]
        if list(_iter_named_blocks(text, "OR", ao, ac)):
            continue
        inner = text[ao:ac]
        astart = text.rfind("abort", o, ao)
        line_start = text.rfind("\n", 0, astart) + 1
        base = text[line_start:astart]
        inner_lines = inner.strip("\n").split("\n")
        wrapped = "\n".join(
            (base + "\t\t" + l.strip()) if l.strip() else ""
            for l in inner_lines
        ).strip("\n")
        replacement = f"abort = {{\n{base}\tOR = {{\n{wrapped}\n{base}\t}}\n{base}}}"
        edits.append((astart, ac + 1, replacement))
    for s, e, r in sorted(edits, key=lambda t: t[0], reverse=True):
        text = text[:s] + r + text[e:]
    return text


def reindent_fragment(fragment, content_indent):
    """Prefix every non-empty line of `fragment` with `content_indent`.
    `fragment` is expected to use '\\t' indentation starting from column 0."""
    out = []
    for line in fragment.splitlines():
        if line.strip() == '':
            out.append('')
        else:
            out.append(content_indent + line)
    return '\n'.join(out)


def splice_injections(text, injections):
    """
    Apply a list of (insert_pos, payload_text) to `text`.

    `payload_text` is the already-reindented block of lines to insert
    immediately before `insert_pos` (the closing brace). Applied from the
    bottom up so earlier offsets stay valid.
    """
    # Detect dominant newline style of the host file.
    newline = '\r\n' if text.count('\r\n') >= text.count('\n') - text.count('\r\n') else '\n'

    for insert_pos, payload in sorted(injections, key=lambda t: t[0], reverse=True):
        block = payload.replace('\r\n', '\n').replace('\n', newline)
        # Ensure the injected content sits on its own line(s) ending before '}'.
        chunk = block.rstrip('\n').rstrip('\r') + newline
        text = text[:insert_pos] + chunk + text[insert_pos:]
    return text


# =============================================================================
# ORCHESTRATION  (compile_fragment is injected so this stays lark-free/testable)
# =============================================================================


def _eof_brace_deficit(text):
    """Net unclosed '{' at EOF (comments and strings ignored), plus whether the
    running depth ever went negative. A negative excursion means a stray or
    misplaced '}' — a real structural defect, not a simple unterminated tail."""
    i = 0
    n = len(text)
    depth = 0
    went_negative = False
    while i < n:
        c = text[i]
        if c == '#':
            i = _skip_comment(text, i)
            continue
        if c == '"':
            i = _skip_string(text, i)
            continue
        if c == '{':
            depth += 1
            i += 1
            continue
        if c == '}':
            depth -= 1
            if depth < 0:
                went_negative = True
            i += 1
            continue
        i += 1
    return depth, went_negative


def normalize_eof_braces(text):
    """Append the trailing top-level '}' that some vanilla/mod files omit.

    HoI4's engine tolerates a missing closing brace at end of file (it auto-
    closes at EOF), so certain common/ideas files ship structurally sound right
    up to the final block yet leave the outermost block unclosed. A strict
    brace matcher can't splice into such a file. This restores the missing
    closer(s) so the delta can be injected, exactly matching engine behaviour.

    Acts ONLY when the deficit is a clean unterminated tail: a positive net of
    unclosed '{' AND depth never went negative. Balanced files and genuine
    defects (extra or misplaced '}') are returned unchanged so they still
    surface as real errors instead of being silently masked.
    """
    deficit, went_negative = _eof_brace_deficit(text)
    if deficit <= 0 or went_negative:
        return text
    return text + '\n' + '\n'.join('}' for _ in range(deficit)) + '\n'
