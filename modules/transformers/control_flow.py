class ControlFlowMixin:
    def if_statement(self, items):
        condition = items[0]
        block_ast = items[-1] # Block is always the last element

        # Automatically build the vanilla limit = { ... } block for HoI4
        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", self.unwrap_top_and(condition)))

        # Extract commands from the original block
        original_commands = block_ast[1]
        scope_var = block_ast[2] if len(block_ast) > 2 else None

        # Concatenate: limit block first, then the actual commands
        new_block_items = [limit_block] + original_commands

        return ("ASSIGN", "if", "=", ("BLOCK", new_block_items, scope_var))

    # `while cond:` -> while_loop_effect. Identical shape to if_statement: the
    # condition becomes a limit block, the body follows it.
    def while_statement(self, items):
        condition = items[0]
        block_ast = items[-1]

        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", self.unwrap_top_and(condition)))
        original_commands = block_ast[1]
        scope_var = block_ast[2] if len(block_ast) > 2 else None

        new_block_items = [limit_block] + original_commands

        return ("ASSIGN", "while_loop_effect", "=", ("BLOCK", new_block_items, scope_var))

    # --- match / case ---------------------------------------------------
    # `match subj:` + `case a | b:` arms -> if / else_if / else chain.
    # Sugar only: each arm compares subj against its patterns and emits the same
    # check_variable / OR blocks the hand-written equivalent would.
    def case_patterns(self, items):
        # Drop the '|' separator tokens; keep the pattern values in order.
        return ("CASE_PATTERNS", [x for x in items if str(x) != "|"])

    def case_clause(self, items):
        patterns = items[0][1]
        body = [x for x in items[1:] if x is not None]
        return ("CASE_CLAUSE", patterns, body)

    def _match_test(self, subject, pattern):
        # Mirrors var_check's '==' handling so match emits identical triggers.
        # A country tag on the right is a plain Clausewitz trigger, not a
        # check_variable.
        if isinstance(pattern, tuple) and pattern and pattern[0] == "COUNTRY_TAG":
            return ("ASSIGN", subject, "=", pattern[1])
        return ("ASSIGN", "check_variable", "=",
                ("BLOCK", [("ASSIGN", subject, "=", pattern)]))

    @staticmethod
    def _is_default_case(patterns):
        return len(patterns) == 1 and str(patterns[0]) == "_"

    def match_statement(self, items):
        subject = items[0]
        clauses = [x for x in items[1:]
                   if isinstance(x, tuple) and x and x[0] == "CASE_CLAUSE"]

        out = []
        emitted_test = False   # has a real (non-default) arm been emitted yet?
        for patterns, body in ((c[1], c[2]) for c in clauses):
            if self._is_default_case(patterns):
                # `case _:` -> else. Without a preceding test there is nothing to
                # fall through from, so emit the body bare instead of a stray else.
                if emitted_test:
                    out.append(("ASSIGN", "else", "=", ("BLOCK", body, None)))
                else:
                    out.extend(body)
                continue

            tests = [self._match_test(subject, p) for p in patterns]
            cond = tests[0] if len(tests) == 1 else ("ASSIGN", "OR", "=", ("BLOCK", tests))
            limit_block = ("ASSIGN", "limit", "=", ("BLOCK", [cond]))

            key = "else_if" if emitted_test else "if"
            out.append(("ASSIGN", key, "=", ("BLOCK", [limit_block] + body, None)))
            emitted_test = True

        return out

    def elif_statement(self, items):
        condition = items[0]
        block_ast = items[-1]

        limit_block = ("ASSIGN", "limit", "=", ("BLOCK", self.unwrap_top_and(condition)))
        original_commands = block_ast[1]
        scope_var = block_ast[2] if len(block_ast) > 2 else None

        new_block_items = [limit_block] + original_commands

        # HoI4 uses "else_if" as the keyword
        return ("ASSIGN", "else_if", "=", ("BLOCK", new_block_items, scope_var))

    def else_statement(self, items):
        block_ast = items[-1]
        # The else block does not need a limit вЂ” return the block as-is
        return ("ASSIGN", "else", "=", block_ast)
