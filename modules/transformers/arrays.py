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

        # A leading '_' marks a temp array. In HoI4 "temp" is decided by the
        # command, not the name, so every operation on a '_' array must use the
        # temp variant — otherwise add/remove hit a persistent array while clear
        # hits a temp one, silently targeting two different arrays.
        is_temp = arr.startswith("_")

        if method == "add":
            cmd = "add_to_temp_array" if is_temp else "add_to_array"
            return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", arr, "=", val)]))
        elif method == "remove":
            cmd = "remove_from_temp_array" if is_temp else "remove_from_array"
            return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", arr, "=", val)]))
        elif method == "clear":
            cmd = "clear_temp_array" if is_temp else "clear_array"
            return ("ASSIGN", cmd, "=", arr)
        else:
            raise ValueError(f"Compilation Error: Unknown array method '.{method}()'")

    # Clearing an array: arr[] <- null
    # Temp arrays (leading '_') map to clear_temp_array, which HoI4 does provide.
    def clear_arr(self, items):
        arr = str(items[0])
        cmd = "clear_temp_array" if arr.startswith("_") else "clear_array"
        return ("ASSIGN", cmd, "=", arr)

    # Two-argument array search: arr[].min(value, index) / arr[].max(value, index)
    #   .min -> find_lowest_in_array,  .max -> find_highest_in_array
    # `value` and `index` are the output variables the engine writes into.
    def array_minmax(self, items):
        arr    = str(items[0])
        method = str(items[1])
        value  = items[2]
        index  = items[3]

        # Unwrap COUNTRY_TAG sentinels defensively (normally these are var names).
        if isinstance(value, tuple) and value[0] == "COUNTRY_TAG":
            value = value[1]
        if isinstance(index, tuple) and index[0] == "COUNTRY_TAG":
            index = index[1]

        if method == "min":
            cmd = "find_lowest_in_array"
        elif method == "max":
            cmd = "find_highest_in_array"
        else:
            raise ValueError(
                f"Unknown two-argument array method '.{method}()'; expected 'min' or 'max'."
            )

        block_items = [
            ("ASSIGN", "array", "=", arr),
            ("ASSIGN", "value", "=", value),
        ]
        # '_' is a throwaway index placeholder — omit the index line entirely.
        if str(index) != "_":
            block_items.append(("ASSIGN", "index", "=", index))

        return ("ASSIGN", cmd, "=", ("BLOCK", block_items))
