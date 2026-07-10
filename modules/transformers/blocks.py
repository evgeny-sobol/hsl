import re

# One raw token: a quoted string (kept whole) or a run of non-space chars.
_RAW_TOKEN = re.compile(r'"[^"]*"|[^\s]+')


class BlocksMixin:
    # Handle generic named blocks like effect:, trigger:, option:
    def generic_block(self, items):
        block_name = str(items[0])
        block_ast = items[-1]

        return ("ASSIGN", block_name, "=", block_ast)

    # Unwrap a COUNTRY_TAG sentinel to its bare tag; pass anything else through.
    def _unwrap_tag(self, v):
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return v[1]
        return v

    # Raw block: name(): { ... }  ->  name = { <verbatim lines> }
    def raw_block(self, items):
        name = str(items[0])
        body = list(items[1:])   # raw_line + comment results, in order
        return ("ASSIGN", name, "=", ("BLOCK", body))

    # Single-line raw block: name(): { lhs op rhs  lhs op rhs ... }
    # Emitted verbatim on ONE line as `name = { <body> }`. The body is kept as a
    # single normalized string so:
    #   * the renderer prints it inline instead of expanding to multiple lines;
    #   * macro substitution still reaches it — _replace_args_in_ast does a
    #     \b-bounded replace over string leaves, and body_text is such a leaf.
    # Tokens are re-joined with single spaces to normalize incoming whitespace.
    def raw_block_inline(self, items):
        name = str(items[0])
        body_text = str(items[1])[1:-1]           # strip surrounding { }
        body_text = " ".join(_RAW_TOKEN.findall(body_text))
        return ("RAW_INLINE", name, body_text)

    # One verbatim line `LHS op RHS`. `op` is '=', a comparison, or a bare
    # identifier placeholder (resolved later by macro substitution). Emitted
    # literally as an ASSIGN — no check_variable, no "= yes".
    def raw_line_op(self, items):
        left  = self._unwrap_tag(items[0])
        right = self._unwrap_tag(items[-1])
        # 3 items -> [left, op, right]; 2 items -> the '=' token was filtered out.
        op = str(items[1]) if len(items) == 3 else "="
        return ("ASSIGN", left, op, right)

    def block(self, items):
        processed_items = []

        for item in items:
            # `pass` and other no-ops transform to None → drop them, so an
            # empty (pass-only) block yields a clean, effect-less body.
            if item is None:
                continue
            # A bare word inside a block is a standalone flag/trigger → "= yes"
            if isinstance(item, str):
                processed_items.append(("ASSIGN", item, "=", "yes"))
            else:
                processed_items.append(item)

        # Third slot is the block's scope variable. Plain blocks never bind one
        # (loop variables are attached by linq_statement, not here), so it's None;
        # kept for a uniform BLOCK shape that downstream code can index safely.
        return ("BLOCK", processed_items, None)


