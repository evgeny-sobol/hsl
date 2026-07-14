class FunctionsMixin:
    def func_call(self, items):
        func_name = str(items[0])

        if len(items) > 1 and items[1] is not None:
            arg = items[1]

            # Reject an arithmetic expression as a direct call argument. The
            # engine does not accept an inline accumulator value-block where a
            # trigger/effect/MTTH key expects a scalar (e.g. factor(1 + x) breaks
            # focus-tree evaluation). Compute it into a variable first.
            # Confirmed in-game on v1.19.2.
            if self._is_expr(arg):
                raise ValueError(
                    f"Arithmetic expression cannot be passed directly to "
                    f"'{func_name}(...)': '{func_name}({self._expr_to_str(arg)})'. "
                    f"HoI4 rejects an inline value-block here. Assign it to a "
                    f"(temp) variable first, e.g.:\n"
                    f"    _tmp <- {self._expr_to_str(arg)}\n"
                    f"    {func_name}(_tmp)"
                )

            # Unwrap a COUNTRY_TAG sentinel to its bare tag.
            if isinstance(arg, tuple) and arg and arg[0] == "COUNTRY_TAG":
                arg = arg[1]
            # Map standard true/false to Clausewitz yes/no. Only strings are
            # touched вЂ” a non-string arg (an int, or an ("ARITH", ...) marker the
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

        if self._is_expr(arg):
            raise ValueError(
                f"Arithmetic expression cannot be passed directly to "
                f"'{scope}::{func}(...)'. HoI4 rejects an inline value-block "
                f"here. Assign it to a (temp) variable first, e.g.:\n"
                f"    _tmp <- {self._expr_to_str(arg)}\n"
                f"    {scope}::{func}(_tmp)"
            )

        # Preserve non-string args (int / ("ARITH", ...) marker); default the
        # empty case to "yes".
        inner_val = "yes" if arg is None else arg
        return ("ASSIGN", scope, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))

    # One-line prefixed scope + trigger:
    #   var:NAME[i]::func(arg)  ->  var:NAME^i = { func = arg }
    #   var:NAME::func(arg)     ->  var:NAME   = { func = arg }
    # items[0] is the PREFIXED_REF. An optional index `value` may follow (from
    # `[i]`), then the func-name token, then an optional call arg (None if empty).
    # The func name is the sole bare-identifier token; the index and arg are the
    # value nodes around it, so classify by position: index is any value BEFORE
    # the func token, arg is the value AFTER it.
    def prefixed_scoped_call(self, items):
        ref = str(items[0])
        rest = list(items[1:])

        # The func name is a Lark Token of type UNQUOTED_VALUE. Locate it; the
        # value before it (if any) is the index, the value after it is the arg.
        func_pos = None
        for i, it in enumerate(rest):
            if hasattr(it, "type") and it.type == "UNQUOTED_VALUE":
                func_pos = i
                break
        # Fallback: if type info is unavailable, the func is the last string-like
        # token that is not the trailing arg.
        if func_pos is None:
            func_pos = 0

        func = str(rest[func_pos])
        index = rest[func_pos - 1] if func_pos >= 1 else None
        arg   = rest[func_pos + 1] if func_pos + 1 < len(rest) else None

        if index is not None:
            idx = self._unwrap_tag(index)
            name = f"{ref}^{idx}"
        else:
            name = ref

        if self._is_expr(arg):
            raise ValueError(
                f"Arithmetic expression cannot be passed directly to "
                f"'{name}::{func}(...)'. HoI4 rejects an inline value-block "
                f"here. Assign it to a (temp) variable first, e.g.:\n"
                f"    _tmp <- {self._expr_to_str(arg)}\n"
                f"    {name}::{func}(_tmp)"
            )

        inner_val = "yes" if arg is None else arg
        return ("ASSIGN", name, "=", ("BLOCK", [("ASSIGN", func, "=", inner_val)]))
