#!/usr/bin/env python3
"""
Extracts, for every `focus = { ... }` block in a HoI4 focus tree file,
the focus id and the *base* value of its ai_will_do (the top-level
`factor = X` line if ai_will_do is a block, or the scalar itself if
ai_will_do is a bare number). Conditional modifiers inside
`modifier = { ... }` blocks are ignored.

Usage:
    python extract_ai_will_do.py path/to/focus_tree.txt
"""

import sys
import re


_WORD_CHARS = set(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
)


def _is_word_char(text, i):
    return 0 <= i < len(text) and text[i] in _WORD_CHARS


def _skip_string(text, i):
    """i points at the opening quote; return index just past the closing quote."""
    i += 1
    n = len(text)
    while i < n:
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    return i


def _skip_comment(text, i):
    n = len(text)
    while i < n and text[i] != '\n':
        i += 1
    return i


def _match_closing_brace(text, open_pos):
    """open_pos is just AFTER a '{'. Return index of the matching '}'."""
    depth = 1
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c == '#':
            i = _skip_comment(text, i)
        elif c == '"':
            i = _skip_string(text, i)
        elif c == '{':
            depth += 1
            i += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
            i += 1
        else:
            i += 1
    raise ValueError("Unbalanced braces: no matching '}' found")


def _iter_named_blocks(text, name, start, end):
    """Yield (open_pos, close_pos) for every direct-child block
    `name = { ... }` at brace depth 0 within text[start:end]."""
    i = start
    depth = 0
    nlen = len(name)
    while i < end:
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
            i += 1
            continue

        if depth == 0 and not _is_word_char(text, i - 1) \
                and text.startswith(name, i) \
                and not _is_word_char(text, i + nlen):
            j = i + nlen
            while j < end and text[j] in ' \t\r\n':
                j += 1
            if j < end and text[j] == '=':
                j += 1
                while j < end and text[j] in ' \t\r\n':
                    j += 1
                if j < end and text[j] == '{':
                    open_pos = j + 1
                    close_pos = _match_closing_brace(text, open_pos)
                    yield (open_pos, close_pos)
                    i = close_pos + 1
                    continue
            i = i + nlen
            continue
        i += 1


def _find_direct_key(text, start, end, key):
    """
    Find the first `key = <value>` at brace depth 0 directly inside
    text[start:end]. Returns (value_str_or_None, value_open_pos, value_close_pos, is_block).

    - If the value is a block `{ ... }`, returns (None, open_pos, close_pos, True)
      so the caller can inspect it further; the raw text isn't needed as scalar.
    - If the value is a scalar (number/word/quoted string), returns
      (scalar_text, start_pos, end_pos, False).
    - If not found, returns (None, None, None, None).
    """
    i = start
    depth = 0
    klen = len(key)
    while i < end:
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
            i += 1
            continue

        if depth == 0 and not _is_word_char(text, i - 1) \
                and text.startswith(key, i) \
                and not _is_word_char(text, i + klen):
            j = i + klen
            while j < end and text[j] in ' \t\r\n':
                j += 1
            if j < end and text[j] == '=':
                j += 1
                while j < end and text[j] in ' \t\r\n':
                    j += 1
                if j < end and text[j] == '{':
                    open_pos = j + 1
                    close_pos = _match_closing_brace(text, open_pos)
                    return (None, open_pos, close_pos, True)
                if j < end and text[j] == '"':
                    endq = _skip_string(text, j)
                    return (text[j:endq], j, endq, False)
                k = j
                while k < end and text[k] not in ' \t\r\n}#':
                    k += 1
                return (text[j:k], j, k, False)
            i = i + klen
            continue
        i += 1
    return (None, None, None, None)


def extract_base_ai_will_do(text, start, end):
    """
    Given the body of one `focus = { ... }` block (start/end offsets),
    return the base ai_will_do value as a string, or None if absent.

    - ai_will_do = 5           -> "5"
    - ai_will_do = { factor = 5  modifier = { ... } }  -> "5" (the factor)
    - ai_will_do = { modifier = { ... } }  (no factor) -> None
    """
    val, vstart, vend, is_block = _find_direct_key(text, start, end, "ai_will_do")

    if vstart is None:
        return None

    if not is_block:
        # Bare scalar: ai_will_do = 5
        return val.strip().strip('"')

    # It's a block: look for a direct `factor = <scalar>` inside it.
    fval, fstart, fend, f_is_block = _find_direct_key(text, vstart, vend, "factor")
    if fval is None:
        return None
    if f_is_block:
        # factor itself is a block — not the simple scalar case we expect.
        return None
    return fval.strip().strip('"')


def extract_focus_id(text, start, end):
    val, _, _, is_block = _find_direct_key(text, start, end, "id")
    if val is None or is_block:
        return None
    return val.strip().strip('"')


def process_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()

    # `focus` blocks live one level deep, inside `focus_tree = { ... }`.
    search_ranges = list(_iter_named_blocks(text, "focus_tree", 0, len(text)))
    if not search_ranges:
        # Fallback: no focus_tree wrapper found, search the whole file.
        search_ranges = [(0, len(text))]

    results = []
    for tree_start, tree_end in search_ranges:
        for open_pos, close_pos in _iter_named_blocks(text, "focus", tree_start, tree_end):
            focus_id = extract_focus_id(text, open_pos, close_pos)
            if focus_id is None:
                # Skip malformed focus blocks without an id
                continue
            ai_will_do = extract_base_ai_will_do(text, open_pos, close_pos)
            results.append((focus_id, ai_will_do))

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_ai_will_do.py <focus_tree_file.txt>")
        sys.exit(1)

    path = sys.argv[1]
    results = process_file(path)

    print("focus_id,ai_will_do")
    for focus_id, ai_will_do in results:
        value = ai_will_do if ai_will_do is not None else "_"
        print(f"{focus_id},{value}")


if __name__ == "__main__":
    main()
