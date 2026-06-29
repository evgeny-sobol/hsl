class ArraysMixin:
    # Writing a value by index: arr[i] <- val
    def array_assign(self, items):
        arr = str(items[0])
        i = items[1]
        val = items[3] # items[2] is the "<-" token, so the value is in items[3]

        # Unwrap COUNTRY_TAG sentinel
        if isinstance(val, tuple) and val[0] == "COUNTRY_TAG":
            val = val[1]

        target = f"{arr}^{i}"
        return ("ASSIGN", "set_variable", "=", ("BLOCK", [("ASSIGN", target, "=", val)]))

    # Reading a value by index: arr[i]
    def array_access(self, items):
        arr = str(items[0])
        i = items[1]
        return f"{arr}^{i}"

    # Reading array size: arr[].size()
    def array_size(self, items):
        arr = str(items[0])
        return f"{arr}^num"

    # Array methods (clear, add, remove)
    def array_method(self, items):
        arr = str(items[0])
        method = str(items[1])

        # If there's an argument in parentheses, it will be in items[2]
        val = items[2] if len(items) > 2 else None

        # Unwrap COUNTRY_TAG sentinel
        if isinstance(val, tuple) and val[0] == "COUNTRY_TAG":
            val = val[1]

        if method == "add":
            return ("ASSIGN", "add_to_array", "=", ("BLOCK", [("ASSIGN", arr, "=", val)]))
        elif method == "remove":
            return ("ASSIGN", "remove_from_array", "=", ("BLOCK", [("ASSIGN", arr, "=", val)]))
        elif method == "clear":
            return ("ASSIGN", "clear_array", "=", arr)
        else:
            raise ValueError(f"Compilation Error: Unknown array method '.{method}()'")
