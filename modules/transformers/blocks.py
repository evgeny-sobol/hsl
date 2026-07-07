class BlocksMixin:
    # Handle generic named blocks like effect:, trigger:, option:
    def generic_block(self, items):
        block_name = str(items[0])
        block_ast = items[-1]

        return ("ASSIGN", block_name, "=", block_ast)

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
