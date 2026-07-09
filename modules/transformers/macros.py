import re

class MacrosMixin:
    # Macro Definition
    def macro_def(self, items):
        macro_name = str(items[0])

        # Check if parameters were provided
        if len(items) == 3:
            params = items[1]
            block_ast = items[2]
        else:
            params = []
            block_ast = items[1]

        # `params` is a list of (name, default) tuples; default is None when the
        # parameter is required. Enforce Python-style ordering: once a parameter
        # has a default, every parameter after it must have one too — otherwise
        # filling missing trailing args from defaults would be ambiguous.
        seen_default = False
        for name, default in params:
            if default is None:
                if seen_default:
                    raise ValueError(
                        f"Error: Macro '{macro_name}': required parameter '{name}' "
                        f"cannot follow a parameter with a default value."
                    )
            else:
                seen_default = True

        # Store both parameters and the body block.
        # A body that is exactly one bare value expression (("EXPR", v)) marks a
        # *value macro*: calling it in a value position substitutes that
        # expression. Anything else is an ordinary *operator macro* whose body is
        # a list of statements spliced in at the call site.
        body_items = block_ast[1]
        if len(body_items) == 1 and isinstance(body_items[0], tuple) and body_items[0][0] == "EXPR":
            self.macros[macro_name] = {
                "params": params,
                "body": body_items[0][1],   # the value expression itself
                "is_value": True,
            }
        else:
            self.macros[macro_name] = {
                "params": params,
                "body": body_items,
                "is_value": False,
            }
        return None

    # Macro Call
    def macro_call(self, items):
        # Extract the name and strip the leading '@' prefix character
        macro_name = str(items[0])[1:]

        # Check if arguments were provided
        if len(items) == 2:
            args = items[1]
        else:
            args = []

        macro_data = self.macros.get(macro_name)
        if not macro_data:
            raise ValueError(f"Error: Macro '{macro_name}' is not found in the library!")

        params = macro_data["params"]      # list of (name, default) tuples
        body = macro_data["body"]

        param_names = [p[0] for p in params]
        defaults    = [p[1] for p in params]
        required    = sum(1 for d in defaults if d is None)  # defaults are trailing

        # Validation: allow anywhere from `required` up to len(params) arguments.
        if not (required <= len(args) <= len(params)):
            if required == len(params):
                expected = f"{len(params)}"
            else:
                expected = f"{required} to {len(params)}"
            raise ValueError(
                f"Error: Macro '{macro_name}' expects {expected} arguments, "
                f"but got {len(args)}!"
            )

        # Fill the missing trailing arguments from their defaults.
        effective_args = list(args) + defaults[len(args):]

        # Create a mapping dictionary: {'country': 'SWE', 'amount': '50'}
        param_map = dict(zip(param_names, effective_args))

        # Return a deep-copied AST with all variables replaced!
        return self._replace_args_in_ast(body, param_map)

    # One parameter: name with an optional default value.
    # Returns (name, default) where default is None when absent.
    def macro_param(self, items):
        name = str(items[0])
        default = items[1] if len(items) > 1 else None
        return (name, default)

    # Helper to unpack parameters — a list of (name, default) tuples.
    def macro_params(self, items):
        return list(items)

    # Helper to unpack arguments
    def macro_args(self, items):
        return items

    # Recursive AST Replacer
    def _replace_args_in_ast(self, node, param_map):
        # Unwrap COUNTRY_TAG sentinels in param_map before substitution
        unwrapped_map = {
            k: (v[1] if isinstance(v, tuple) and v[0] == "COUNTRY_TAG" else v)
            for k, v in param_map.items()
        }

        if isinstance(node, str):
            new_str = node
            # Loop through all parameters and replace them with passed arguments
            for param, arg in unwrapped_map.items():
                # \b matches word boundaries, so 'var' won't replace 'my_var'
                pattern = r'\b' + re.escape(str(param)) + r'\b'
                new_str = re.sub(pattern, str(arg), new_str)
            return new_str

        elif isinstance(node, list):
            # Recursively process lists
            return [self._replace_args_in_ast(child, param_map) for child in node]

        elif isinstance(node, tuple):
            # For an ASSIGN, the op slot (index 2) may receive an operator passed
            # as a quoted string (e.g. ">"); strip the surrounding quotes so it
            # lands in the operator position literally. Normal ops ("=", ">") are
            # never quoted, so this is a no-op for them.
            if node[0] == "ASSIGN" and len(node) == 4:
                left  = self._replace_args_in_ast(node[1], param_map)
                op    = self._replace_args_in_ast(node[2], param_map)
                right = self._replace_args_in_ast(node[3], param_map)
                if isinstance(op, str) and len(op) >= 2 and op[0] == '"' and op[-1] == '"':
                    op = op[1:-1]
                return ("ASSIGN", left, op, right)
            # Recursively process other tuples
            return tuple(self._replace_args_in_ast(child, param_map) for child in node)

        else:
            return node
