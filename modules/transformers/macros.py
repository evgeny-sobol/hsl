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

        # Store both parameters and the body block
        self.macros[macro_name] = {
            "params": params,
            "body": block_ast[1]
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

        params = macro_data["params"]
        body = macro_data["body"]

        # Validation
        if len(args) != len(params):
            raise ValueError(f"Error: Macro '{macro_name}' expects {len(params)} arguments, but got {len(args)}!")

        # Create a mapping dictionary: {'country': 'SWE', 'amount': '50'}
        param_map = dict(zip(params, args))

        # Return a deep-copied AST with all variables replaced!
        return self._replace_args_in_ast(body, param_map)

    # Helper to unpack parameters
    def macro_params(self, items):
        return [str(item) for item in items]

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
            # Recursively process tuples
            return tuple(self._replace_args_in_ast(child, param_map) for child in node)

        else:
            return node
