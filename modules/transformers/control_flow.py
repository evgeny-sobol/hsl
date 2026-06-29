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
        # The else block does not need a limit — return the block as-is
        return ("ASSIGN", "else", "=", block_ast)
