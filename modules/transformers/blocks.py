import re

# One raw token: a quoted string (kept whole) or a run of non-space chars.
_RAW_TOKEN = re.compile(r'"[^"]*"|[^\s]+')


class BlocksMixin:
    # Handle generic named blocks like effect:, trigger:, option:
    def generic_block(self, items):
        block_name = str(items[0])
        block_ast = items[-1]

        return ("ASSIGN", block_name, "=", block_ast)

    # `scope::func:` + block  ->  scope = { func = { ...block... } }.
    # The scoped counterpart of generic_block, for engine scope-transitions that
    # take a trigger/effect block (e.g. any_controlled_state) rather than the
    # single argument scoped_func_call handles.
    def scoped_block(self, items):
        items = [it for it in items if not (hasattr(it, "type") and it.type == "ARROW")]
        scope = self._scope_name(items[0])
        func  = str(items[1])
        block_ast = items[-1]
        return ("ASSIGN", scope, "=",
                ("BLOCK", [("ASSIGN", func, "=", block_ast)]))

    # Multi-level scope chain A->B->...->trigger(arg) -> nested scope blocks.
    # All names but the last are scope transitions; the last name is the
    # trigger/effect and takes the (optional) argument.
    #   A->B->C(x)  ->  A = { B = { C = x } }
    def scoped_chain(self, items):
        # Drop ARROW tokens; remaining are name tokens plus an optional arg.
        parts = [it for it in items if not (hasattr(it, "type") and it.type == "ARROW")]
        parts = [p for p in parts if p is not None]

        # Chain elements are UNQUOTED_VALUE tokens; the head may also be a
        # COUNTRY_TAG (e.g. $HAI->...), which arrives as a ("COUNTRY_TAG", tag)
        # tuple. Anything else is the trailing argument (empty `()` -> "yes").
        def is_name(p):
            if hasattr(p, "type") and p.type in ("UNQUOTED_VALUE", "COUNTRY_TAG"):
                return True
            return isinstance(p, tuple) and len(p) == 2 and p[0] == "COUNTRY_TAG"

        name_toks = [p for p in parts if is_name(p)]
        non_names = [p for p in parts if not is_name(p)]
        arg = non_names[0] if non_names else "yes"
        if isinstance(arg, tuple) and arg and arg[0] == "COUNTRY_TAG":
            arg = arg[1]

        *scopes, trigger = [self._scope_name(t) for t in name_toks]
        node = ("ASSIGN", trigger, "=", arg)   # innermost trigger
        for sc in reversed(scopes):            # wrap in each scope, outward
            node = ("ASSIGN", sc, "=", ("BLOCK", [node]))
        return node

    # Bracket list-trigger: name[a, b, c] -> name = { a b c } on ONE line.
    # Emitted as RAW_INLINE so the renderer prints it inline instead of expanding
    # each element to its own line — the compact form engine list-triggers like
    # owns_any_state_of read best in.
    def bracket_list(self, items):
        name = str(items[0])
        body = " ".join(str(self._unwrap_tag(v)) for v in items[1:])
        return ("RAW_INLINE", name, body)

    # A var:/token:/mtth: reference used as a scope header, optionally indexed:
    #   var:NAME[i]:  ...   ->  var:NAME^i = { ... }
    #   var:NAME:     ...   ->  var:NAME   = { ... }
    # items: [PREFIXED_REF, index_value?, BLOCK]. The index maps to the engine's
    # `^i` element access.
    def prefixed_block(self, items):
        ref = str(items[0])
        block_ast = items[-1]
        # 3 items -> an index sits between the ref and the block.
        if len(items) == 3:
            idx = self._unwrap_tag(items[1])
            name = f"{ref}^{idx}"
        else:
            name = ref
        return ("ASSIGN", name, "=", block_ast)

    # Unwrap a COUNTRY_TAG sentinel to its bare tag; pass anything else through.
    def _unwrap_tag(self, v):
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return v[1]
        return v

    # Raw block: `raw name: { ... }`  ->  name = { <verbatim lines> }
    # items[0] is the RAW_KW marker token; the name follows it.
    def raw_block(self, items):
        name = str(items[1])
        body = list(items[2:])   # raw_line + comment results, in order
        return ("ASSIGN", name, "=", ("BLOCK", body))

    # Single-line raw block: `raw name: { lhs op rhs  lhs op rhs ... }`
    # Emitted verbatim on ONE line as `name = { <body> }`. The body is kept as a
    # single normalized string so:
    #   * the renderer prints it inline instead of expanding to multiple lines;
    #   * macro substitution still reaches it — _replace_args_in_ast does a
    #     \b-bounded replace over string leaves, and body_text is such a leaf.
    # Tokens are re-joined with single spaces to normalize incoming whitespace.
    # items[0] is the RAW_KW marker; name is items[1], the { } body is items[2].
    def raw_block_inline(self, items):
        name = str(items[1])
        body_text = str(items[2])[1:-1]           # strip surrounding { }
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

    # A verbatim line that is a single bare token (no operator), e.g. a focus id
    # in an `ai_national_focuses` priority list. Emitted as-is on its own line,
    # with no "= yes" sugar. Kept as ("RAW_BARE", token) — a string leaf so macro
    # substitution still reaches it.
    def raw_line_bare(self, items):
        tok = self._unwrap_tag(items[0])
        return ("RAW_BARE", str(tok))

    # Standalone raw trigger `raw LHS op RHS` -> a verbatim RAW_ASSIGN, emitted
    # with no sugar and no wrapping block. items[0] is the RAW_KW marker; the
    # operands follow. Tagged RAW_ASSIGN (not ASSIGN) so macro substitution strips
    # surrounding quotes off ALL three slots — a date arg must be quoted at the
    # call site (`"1939.1.1"`) to survive tokenizing, but HoI4 wants it bare.
    def raw_stmt_op(self, items):
        rest = items[1:]                       # drop RAW_KW marker
        left  = self._unwrap_tag(rest[0])
        right = self._unwrap_tag(rest[-1])
        # 3 items -> [left, op, right]; 2 items -> the '=' literal was filtered out.
        op = str(rest[1]) if len(rest) == 3 else "="
        return ("RAW_ASSIGN", left, op, right)

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
