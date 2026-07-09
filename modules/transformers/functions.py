class FunctionsMixin:
    def func_call(self, items):
        func_name = str(items[0])

        if len(items) > 1 and items[1] is not None:
            arg = items[1]

            # Unwrap a COUNTRY_TAG sentinel to its bare tag.
            if isinstance(arg, tuple) and arg and arg[0] == "COUNTRY_TAG":
                arg = arg[1]
            # Map standard true/false to Clausewitz yes/no. Only strings are
            # touched — a non-string arg (an int, or an ("ARITH", ...) marker the
            # post-pass will lift) must pass through untouched, NOT be str()'d.
            elif isinstance(arg, str):
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

        # Preserve non-string args (int / ("ARITH", ...) marker); default the
        # empty case to "yes".
        inner_val = "yes" if arg is None else arg
        return ("ASSIGN", scope, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))
