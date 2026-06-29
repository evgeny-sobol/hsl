class BlocksMixin:
    # Handle generic named blocks like effect:, trigger:, option:
    def generic_block(self, items):
        block_name = str(items[0])
        block_ast = items[-1]

        return ("ASSIGN", block_name, "=", block_ast)

    def block(self, items):
        processed_items = []
        scope_var = None

        for item in items:
            # If a context declaration is encountered, store it for future reference
            if isinstance(item, tuple) and item[0] == "SCOPE_DEF":
                scope_var = item[1]
            elif isinstance(item, str):
                processed_items.append(("ASSIGN", item, "=", "yes"))
            else:
                processed_items.append(item)

        return ("BLOCK", processed_items, scope_var)

    # Context declaration interceptor: c ->
    def scope_def(self, items):
        # Return a special tuple containing the variable name
        return ("SCOPE_DEF", str(items[1]))
