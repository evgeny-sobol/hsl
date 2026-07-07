class LinqMixin:
    # Python-style loop head `cty in` → a SCOPE_DEF marker that binds the loop
    # variable so resolve_scopes can map it to THIS/PREV downstream.
    def loop_binding(self, items):
        return ("SCOPE_DEF", str(items[0]))

    def linq_statement(self, items):
        # Both surface forms ("for scope() ... -> var:" and "for var in scope() ...:")
        # deliver the same set of parts in different order. Classify by type
        # instead of position: the scope name is the only non-tuple item, the
        # loop variable arrives as a SCOPE_DEF tuple, the block as a BLOCK tuple,
        # and the optional .which() condition is any other tuple.
        scope_name = None
        condition = None
        scope_var = None
        block_ast = None

        for it in items:
            if isinstance(it, tuple):
                tag = it[0]
                if tag == "SCOPE_DEF":
                    scope_var = it[1]
                elif tag == "BLOCK":
                    block_ast = it
                else:
                    condition = it
            else:
                scope_name = str(it)

        original_commands = block_ast[1]
        new_block_items = []

        if condition:
            new_block_items.append(("ASSIGN", "limit", "=", ("BLOCK", self.unwrap_top_and(condition))))

        new_block_items += original_commands

        # Pass scope_var into BLOCK so resolve_scopes can use it
        return ("ASSIGN", scope_name, "=", ("BLOCK", new_block_items, scope_var))

    # Array iteration: for value, index in array_name[]:  ->  for_each_loop.
    # `value` and `index` are ordinary variables the engine writes each element
    # into (NOT scope pointers), so no scope_var is bound — the body uses them
    # verbatim and resolve_scopes must leave them alone.
    def array_loop(self, items):
        value = str(items[0])
        index = str(items[1])
        array = str(items[2])
        block_ast = items[3]

        new_block_items = [
            ("ASSIGN", "array", "=", array),
            ("ASSIGN", "value", "=", value),
        ]
        # '_' is a throwaway index placeholder — omit the index line entirely.
        if index != "_":
            new_block_items.append(("ASSIGN", "index", "=", index))
        new_block_items += list(block_ast[1])

        return ("ASSIGN", "for_each_loop", "=", ("BLOCK", new_block_items, None))
