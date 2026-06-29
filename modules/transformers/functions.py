class FunctionsMixin:
    def func_call(self, items):
        func_name = str(items[0])

        if len(items) > 1 and items[1] is not None:
            # Convert argument to string for easier manipulation
            arg = str(items[1])

            # REPLACEMENT MAGIC
            # Map standard true/false values to Clausewitz yes/no primitives
            if arg == "true":
                arg = "yes"
            elif arg == "false":
                arg = "no"

            return ("ASSIGN", func_name, "=", arg)
        else:
            # If parentheses are empty, default to standard HoI4 trigger behavior ("= yes")
            return ("ASSIGN", func_name, "=", "yes")

    def scoped_func_call(self, items):
        scope = str(items[0])   # "variable"
        func  = str(items[1])   # "can_ROOT_get_wargoal_on_THIS"
        arg   = items[2] if len(items) > 2 else None

        inner_val = "yes" if arg is None else str(arg)
        return ("ASSIGN", scope, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))
