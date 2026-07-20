class MiscMixin:
    # Preserve comments in our AST
    def comment(self, items):
        # items[0] contains the actual text of the comment, e.g., "# My comment"
        comment_text = str(items[0])
        return ("COMMENT", comment_text)

    def operator(self, items):
        return str(items[0])

    # Python-style no-op: compiles to nothing. Returning None makes it vanish
    # (start() filters None at top level; block() filters it inside blocks).
    def pass_statement(self, items):
        return None

    # `break` inside a for-loop. Emitted as a marker; the enclosing loop handler
    # allocates a unique flag var, declares `break = hsl_break_N` in the loop
    # header, and rewrites this marker to `set_temp_variable = { hsl_break_N = 1 }`.
    def break_statement(self, items):
        return ("BREAK",)

    # A bare value on its own line.
    #  - An operator-macro call used as a statement expands to a LIST of
    #    statements → pass it straight through so it flattens like before.
    #  - Any other bare value is wrapped as ("EXPR", value); this is what a
    #    value-macro body looks like, and macro_def unwraps it. Elsewhere it
    #    is effectively inert (a bare value is not a valid standalone effect).
    def expr_statement(self, items):
        v = items[0]
        if isinstance(v, list):
            return v
        return ("EXPR", v)
