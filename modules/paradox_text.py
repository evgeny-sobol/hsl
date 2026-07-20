"""Low-level scanning of Paradox (Clausewitz) script text: comment/string
skipping, brace matching, block iteration, indentation. No HSL knowledge.
"""
import re

_STRUCT_CHAR = re.compile(r'[{}#"]')
_WORD_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
_SL_TOKEN = re.compile(r'"[^"]*"|[{}]|[^\s{}]+')



def _indent_width(raw_line):
    """Number of leading whitespace columns (tab counts as 1 here; only used
    for relative nesting comparisons, so absolute width does not matter)."""
    return len(raw_line) - len(raw_line.lstrip(' \t'))


def dedent_lines(lines):
    """Strip the common leading-whitespace prefix from a block of lines."""
    indents = [_indent_width(l) for l in lines if l.strip()]
    if not indents:
        return [l.strip() for l in lines]
    base = min(indents)
    return [l[base:] if l.strip() else '' for l in lines]


# =============================================================================
# BRACE-AWARE LOCATOR  (find where to inject inside a vanilla .txt block)
# =============================================================================


def _skip_string(text, i):
    """`i` points at the opening quote; return index just past the closing quote.

    Clausewitz strings do NOT use backslash escaping — a backslash is a literal
    path separator (e.g. "gfx\\interface\\x.dds"), so a string ending in \\" still
    closes at that quote. Treating \\" as an escaped quote would swallow the
    closing quote, run the "string" to end-of-file, and unbalance every brace
    after it.
    """
    i += 1
    n = len(text)
    while i < n:
        if text[i] == '"':
            return i + 1
        i += 1
    return i  # unterminated; treat rest as string


def _skip_comment(text, i):
    """`i` points at '#'; return index of the newline (or end)."""
    n = len(text)
    while i < n and text[i] != '\n':
        i += 1
    return i




def _match_closing_brace(text, open_pos):
    """`open_pos` is the index just AFTER a '{'. Return the index of its
    matching '}', skipping nested braces, strings and comments.

    Jumps between structural characters (`{ } # "`) via a compiled regex instead
    of scanning every character, since block bodies are mostly non-structural
    text. Behaviourally identical to the char-by-char version.
    """
    depth = 1
    i = open_pos
    n = len(text)
    search = _STRUCT_CHAR.search
    while i < n:
        m = search(text, i)
        if not m:
            break
        c = m.group()
        p = m.start()
        if c == '#':
            i = _skip_comment(text, p)
        elif c == '"':
            i = _skip_string(text, p)
        elif c == '{':
            depth += 1
            i = p + 1
        else:  # '}'
            depth -= 1
            if depth == 0:
                return p
            i = p + 1
    raise ValueError("Unbalanced braces: no matching '}' found")




def _is_word_char(text, i):
    return 0 <= i < len(text) and text[i] in _WORD_CHARS


def _iter_named_blocks(text, name, start, end):
    """Yield (open_pos, close_pos) for every direct-child block `name = { ... }`
    at brace depth 0 within text[start:end]. open_pos is just AFTER '{',
    close_pos is the matching '}'.

    A compiled regex locates `name = {` candidates; between the cursor and each
    candidate only structural characters (`{ } # "`) are inspected to maintain
    brace depth, and nested blocks are jumped via their closing brace. This
    avoids the per-character scan (the profiler hot path). Behaviourally
    identical to the char-by-char version (verified over randomized inputs).
    """
    name_pat = re.compile(r"\b" + re.escape(name) + r"\b[ \t\r\n]*=[ \t\r\n]*\{")
    struct = _STRUCT_CHAR.search

    i = start
    depth = 0
    while i < end:
        m = name_pat.search(text, i, end)
        limit = m.start() if m else end

        # Update depth over [i, limit) inspecting only structural chars. If a
        # comment/string starting before `limit` extends past the candidate,
        # the candidate is inside it -> skip past the obstacle and retry.
        swallowed = False
        k = i
        while True:
            sm = struct(text, k, end)
            if not sm or sm.start() >= limit:
                break
            c = sm.group()
            p = sm.start()
            if c == '#':
                j = _skip_comment(text, p)
                if m and j > m.start():
                    i = j; swallowed = True; break
                k = j
            elif c == '"':
                j = _skip_string(text, p)
                if m and j > m.start():
                    i = j; swallowed = True; break
                k = j
            elif c == '{':
                depth += 1; k = p + 1
            else:  # '}'
                depth -= 1; k = p + 1
        if swallowed:
            continue
        if not m:
            break

        if depth == 0:
            open_pos = m.end()
            close_pos = _match_closing_brace(text, open_pos)
            yield (open_pos, close_pos)
            i = close_pos + 1
        else:
            depth += 1
            i = m.end()


def _iter_top_level_blocks(text):
    i = 0
    n = len(text)
    depth = 0
    while i < n:
        c = text[i]
        if c == "#":
            i = _skip_comment(text, i); continue
        if c == '"':
            i = _skip_string(text, i); continue
        if c == "{":
            depth += 1; i += 1; continue
        if c == "}":
            depth -= 1; i += 1; continue
        if depth == 0 and (c in _WORD_CHARS) and not _is_word_char(text, i - 1):
            j = i
            while j < n and text[j] in _WORD_CHARS:
                j += 1
            k = j
            while k < n and text[k] in " \t\r\n":
                k += 1
            if k < n and text[k] == "=":
                k += 1
                while k < n and text[k] in " \t\r\n":
                    k += 1
                if k < n and text[k] == "{":
                    open_pos = k + 1
                    close_pos = _match_closing_brace(text, open_pos)
                    yield (text[i:j], open_pos, close_pos)
                    i = close_pos + 1
                    continue
            i = j
            continue
        i += 1


# =============================================================================
# SPLICING
# =============================================================================


def _in_comment_or_string(text, line_start, start):
    """True if position `start` lies inside a comment or string on its line."""
    inq = False
    i = line_start
    while i < start:
        ch = text[i]
        if ch == '"':
            inq = not inq
        elif ch == '#' and not inq:
            return True
        i += 1
    return inq
