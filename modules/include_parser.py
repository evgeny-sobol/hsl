"""Parsing of .include files into a Node tree (selectors + payload lines)."""
import re
from modules.paradox_text import _indent_width

_HEADER_RE = re.compile(r'^(\+?)([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\]]+)\])?:\s*$')
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
