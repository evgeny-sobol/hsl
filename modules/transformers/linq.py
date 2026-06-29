class LinqMixin:
    def linq_statement(self, items):
        scope_name = str(items[0])

        # Check if .which(condition) is present
        if isinstance(items[1], tuple) and items[1][0] not in ("SCOPE_DEF", "BLOCK"):
            condition = items[1]
            offset = 2
        else:
            condition = None
            offset = 1

        scope_var = None
        if isinstance(items[offset], tuple) and items[offset][0] == "SCOPE_DEF":
            scope_var = items[offset][1]
            block_ast = items[offset + 1]
        else:
            block_ast = items[offset]

        original_commands = block_ast[1]
        new_block_items = []

        if condition:
            new_block_items.append(("ASSIGN", "limit", "=", ("BLOCK", self.unwrap_top_and(condition))))

        new_block_items += original_commands

        # Pass scope_var into BLOCK so resolve_scopes can use it
        return ("ASSIGN", scope_name, "=", ("BLOCK", new_block_items, scope_var))
