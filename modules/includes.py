import os
import re

# =============================================================================
# .include PARSING  (source -> node tree)
# =============================================================================

# A block header: optional '+' (create), an identifier, an optional [selector],
# a colon, nothing else.
#   on_startup:                   -> first existing "on_startup" block
#   focus[3]:                     -> the 4th "focus" child (positional, 0-based)
#   focus[id = YUG_xxx]:          -> the "focus" child whose direct `id` is YUG_xxx
#   +C:                           -> create a NEW block "C"
# Anything with extra tokens before ':' (e.g. "if cond():") is NOT a header.
_HEADER_RE = re.compile(r'^(\+?)([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\]]+)\])?:\s*$')

# Inside [...]: an integer (positional) or `key = value` / `key == value` (attr).
_ATTR_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*={1,2}\s*(.+)$')


def _parse_selector(raw):
    """Parse the bracket body of a header into a selector tuple, or None."""
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return ('index', int(raw))
    m = _ATTR_RE.match(raw)
    if m:
        return ('attr', m.group(1), m.group(2).strip())
    raise ValueError(f"Invalid block selector: [{raw}]")


def _indent_width(raw_line):
    """Number of leading whitespace columns (tab counts as 1 here; only used
    for relative nesting comparisons, so absolute width does not matter)."""
    return len(raw_line) - len(raw_line.lstrip(' \t'))


class Node:
    """A header in the .include tree. `items` is an ordered list whose members
    are either child Nodes or ('leaf', raw_line) tuples, preserving source order
    so leaves and sub-blocks interleave correctly."""
    __slots__ = ('name', 'selector', 'create', 'col', 'items')

    def __init__(self, name=None, selector=None, create=False, col=-1):
        self.name = name
        self.selector = selector
        self.create = create
        self.col = col
        self.items = []


def parse_include(source):
    """Parse an .include source into a virtual root Node.

    Only `IDENT:` / `+IDENT:` lines are headers (they form the tree); every
    other non-blank, non-comment line is a leaf attached to the nearest header
    whose column is strictly smaller. Leaves keep their raw text so their
    relative indentation (e.g. an `if:` body) survives to compilation."""
    root = Node(col=-1)
    stack = [root]

    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue

        col = _indent_width(raw)
        # Pop frames at >= this column so the new line attaches to its parent.
        while len(stack) > 1 and stack[-1].col >= col:
            stack.pop()

        m = _HEADER_RE.match(stripped)
        if m:
            create = bool(m.group(1))
            name = m.group(2)
            selector = _parse_selector(m.group(3))
            node = Node(name, selector, create, col)
            stack[-1].items.append(node)
            stack.append(node)
        else:
            stack[-1].items.append(('leaf', raw))

    return root


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
    """`i` points at the opening quote; return index just past the closing quote."""
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
    return i  # unterminated; treat rest as string


def _skip_comment(text, i):
    """`i` points at '#'; return index of the newline (or end)."""
    n = len(text)
    while i < n and text[i] != '\n':
        i += 1
    return i


def _match_closing_brace(text, open_pos):
    """`open_pos` is the index just AFTER a '{'. Return the index of its
    matching '}', skipping nested braces, strings and comments."""
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


_WORD_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


def _is_word_char(text, i):
    return 0 <= i < len(text) and text[i] in _WORD_CHARS


def _iter_named_blocks(text, name, start, end):
    """Yield (open_pos, close_pos) for every direct-child block `name = { ... }`
    at brace depth 0 within text[start:end]. open_pos is just AFTER '{',
    close_pos is the matching '}'."""
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


def _resolve_segment(text, name, selector, start, end):
    """Pick the target child block for one path segment.

    selector is one of:
      * None                  -> first `name` block
      * ('index', N)          -> N-th `name` block (0-based)
      * ('attr', key, value)  -> first `name` block whose direct `key` == value

    Returns (open_pos, close_pos) or None if no match."""
    blocks = list(_iter_named_blocks(text, name, start, end))
    if not blocks:
        return None

    if selector is None:
        return blocks[0]

    kind = selector[0]
    if kind == 'index':
        n = selector[1]
        return blocks[n] if 0 <= n < len(blocks) else None
    if kind == 'attr':
        key, val = selector[1], selector[2]
        for (op, cl) in blocks:
            got = _read_direct_scalar(text, op, cl, key)
            if got is not None and _values_equal(got, val):
                return (op, cl)
        return None
    return None


def _selector_repr(name, selector):
    if selector is None:
        return name
    if selector[0] == 'index':
        return f"{name}[{selector[1]}]"
    return f"{name}[{selector[1]} = {selector[2]}]"


def find_injection_point(text, path):
    """
    Resolve an address `path` (list/tuple of (name, selector)) inside `text`.

    Return (insert_pos, content_indent):
      * insert_pos      - index at the START of the line that holds the target
                          block's closing '}'. Inject text here; the existing
                          '}' line stays intact below it.
      * content_indent  - the whitespace string each injected line should start
                          with (one level deeper than the block's brace).
    """
    search_start = 0
    search_end = len(text)
    close_pos = None

    for (name, selector) in path:
        res = _resolve_segment(text, name, selector, search_start, search_end)
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


# =============================================================================
# SPLICING
# =============================================================================

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

def _render_local_hsl(items, indent=0):
    """Render a node's *local* content (leaves + created sub-blocks) back into
    HSL source lines, ready to feed to `compile_fragment`.

    Created sub-blocks become plain `name:` headers (the '+' is only meaningful
    at the navigate/create boundary; everything below a create is created).
    Contiguous leaf runs are dedented as a unit so nested HSL (if/for bodies)
    keeps its shape, then re-indented to the current level."""
    out = []
    pad = '  ' * indent
    i = 0
    n = len(items)
    while i < n:
        it = items[i]
        if isinstance(it, tuple):                      # leaf run
            run = []
            while i < n and isinstance(items[i], tuple):
                run.append(items[i][1])
                i += 1
            for dl in dedent_lines(run):
                out.append(pad + dl if dl else '')
        else:                                          # created sub-block
            out.append(f"{pad}{it.name}:")
            out.extend(_render_local_hsl(it.items, indent + 1))
            i += 1
    return out


def _resolve_nav(vanilla_text, nav_path):
    """Where to inject for a navigate path. Empty path => append at file scope."""
    if not nav_path:
        end = len(vanilla_text)
        # Ensure we land at the start of a fresh line.
        if vanilla_text and not vanilla_text.endswith('\n'):
            return end, '', True   # needs a leading newline
        return end, '', False
    insert_pos, content_indent = find_injection_point(vanilla_text, nav_path)
    return insert_pos, content_indent, False


def _collect(node, nav_path, vanilla_text, compile_fragment, injections):
    """Walk navigate nodes; at each, inject all local content (direct leaves +
    created sub-blocks) as one fragment, then recurse into navigate children."""
    local = []
    nav_children = []
    for it in node.items:
        if isinstance(it, tuple) or it.create:
            local.append(it)
        else:
            nav_children.append(it)

    if local:
        insert_pos, content_indent, need_nl = _resolve_nav(vanilla_text, nav_path)
        fragment = compile_fragment(_render_local_hsl(local))
        reindented = reindent_fragment(fragment, content_indent)
        if need_nl:
            reindented = '\n' + reindented
        injections.append((insert_pos, reindented))

    for child in nav_children:
        _collect(child, nav_path + [(child.name, child.selector)],
                 vanilla_text, compile_fragment, injections)


def transpile_include_source(vanilla_text, include_source, compile_fragment):
    """
    Core, dependency-free transform.

      vanilla_text     - raw text of the original .txt
      include_source   - raw text of the .include file
      compile_fragment - callable(list[str]) -> str
                         (HSL source lines -> HoI4 code, '\\t' indented,
                          starting at column 0, no trailing newline)

    Returns the new .txt text.
    """
    root = parse_include(include_source)
    injections = []
    _collect(root, [], vanilla_text, compile_fragment, injections)
    return splice_injections(vanilla_text, injections)
