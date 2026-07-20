"""Resolving .include addresses against the vanilla text: selector matching,
direct-scalar reads, the _VanillaIndex cache, and injection-point lookup.
"""
from modules.paradox_text import (
    _skip_string, _skip_comment, _match_closing_brace, _is_word_char,
    _iter_named_blocks, _SL_TOKEN,
)


def _read_direct_scalar(text, open_pos, close_pos, key):
    """Return the scalar value string of the first `key = <scalar>` found at
    brace depth 0 directly inside the block, or None. Block-valued keys
    (`key = { ... }`) are skipped, so we never match on a nested key."""
    i = open_pos
    depth = 0
    klen = len(key)
    while i < close_pos:
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
            while j < close_pos and text[j] in ' \t\r\n':
                j += 1
            if j < close_pos and text[j] == '=':
                j += 1
                while j < close_pos and text[j] in ' \t\r\n':
                    j += 1
                if j < close_pos and text[j] == '{':
                    # Block-valued: not a scalar. Skip past it and keep looking.
                    i = _match_closing_brace(text, j + 1) + 1
                    continue
                if j < close_pos and text[j] == '"':
                    endq = _skip_string(text, j)
                    return text[j:endq]
                k = j
                while k < close_pos and text[k] not in ' \t\r\n}#':
                    k += 1
                return text[j:k]
            i = i + klen
            continue
        i += 1
    return None


def _values_equal(a, b):
    """Compare two HoI4 scalar values, ignoring surrounding quotes."""
    return a.strip().strip('"') == b.strip().strip('"')


def _norm_value(v):
    return v.strip().strip('"')


class _VanillaIndex:
    """Per-file memoized view over the vanilla text.

    Enumerating a block's direct children and reading their scalar keys are the
    hot operations when an .include addresses hundreds of siblings by attribute
    (e.g. 320 `focus[id = ...]` under one `focus_tree`). Without caching, every
    lookup re-scans the whole block, which is O(injections * file). The index
    scans each (parent-span, name) exactly once and answers by-attribute lookups
    from a {value: block} map, collapsing that to O(file + injections)."""

    __slots__ = ('text', '_blocks', '_attr')

    def __init__(self, text):
        self.text = text
        self._blocks = {}   # (start, end, name)      -> list[(open, close)]
        self._attr = {}     # (start, end, name, key)  -> {norm_value: (open, close)}

    def named_blocks(self, name, start, end):
        key = (start, end, name)
        cached = self._blocks.get(key)
        if cached is None:
            cached = list(_iter_named_blocks(self.text, name, start, end))
            self._blocks[key] = cached
        return cached

    def attr_map(self, name, attr_key, start, end):
        ck = (start, end, name, attr_key)
        m = self._attr.get(ck)
        if m is None:
            m = {}
            for (op, cl) in self.named_blocks(name, start, end):
                val = _read_direct_scalar(self.text, op, cl, attr_key)
                if val is not None:
                    # First occurrence wins, matching the linear-scan semantics.
                    m.setdefault(_norm_value(val), (op, cl))
            self._attr[ck] = m
        return m


def _resolve_segment(index, name, selector, start, end):
    """Pick the target child block for one path segment, using the memoized
    index. `index` is a _VanillaIndex over the file being addressed.

    selector is one of:
      * None                  -> first `name` block
      * ('index', N)          -> N-th `name` block (0-based)
      * ('attr', key, value)  -> first `name` block whose direct `key` == value

    Returns (open_pos, close_pos) or None if no match."""
    if selector is not None and selector[0] == 'attr':
        key, val = selector[1], selector[2]
        return index.attr_map(name, key, start, end).get(_norm_value(val))

    blocks = index.named_blocks(name, start, end)
    if not blocks:
        return None
    if selector is None:
        return blocks[0]
    if selector[0] == 'index':
        n = selector[1]
        return blocks[n] if 0 <= n < len(blocks) else None
    return None


def _selector_repr(name, selector):
    if selector is None:
        return name
    if selector[0] == 'index':
        return f"{name}[{selector[1]}]"
    return f"{name}[{selector[1]} = {selector[2]}]"


def find_injection_point(text, path, index=None):
    """
    Resolve an address `path` (list/tuple of (name, selector)) inside `text`.

    `index` is an optional _VanillaIndex over `text`; pass a shared one when
    resolving many paths in the same file so block enumerations are reused.

    Return (insert_pos, content_indent):
      * insert_pos      - index at the START of the line that holds the target
                          block's closing '}'. Inject text here; the existing
                          '}' line stays intact below it.
      * content_indent  - the whitespace string each injected line should start
                          with (one level deeper than the block's brace).
    """
    if index is None:
        index = _VanillaIndex(text)

    search_start = 0
    search_end = len(text)
    close_pos = None

    for (name, selector) in path:
        res = _resolve_segment(index, name, selector, search_start, search_end)
        if res is None:
            raise KeyError(
                f"Block path segment '{_selector_repr(name, selector)}' not found")
        open_pos, close_pos = res
        search_start = open_pos
        search_end = close_pos

    line_start = text.rfind('\n', 0, close_pos) + 1
    prefix = text[line_start:close_pos]

    if prefix.strip() != '':
        # The closing '}' is not alone on its line (single-line block like
        # `foo = { a = b }`). Structural injection would corrupt it.
        raise ValueError(
            f"Target block '{path[-1][0]}' is written on a single line; "
            f"cannot inject into it. Reformat the block across multiple lines.")

    brace_indent = prefix            # the whitespace before '}'
    content_indent = brace_indent + '\t'
    return line_start, content_indent


