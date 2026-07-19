class ArraysMixin:
    # Array lifetime: temp by DEFAULT; a leading '&' on the array NAME (after any
    # scope prefix, e.g. `&rivals`, `cty.&rivals`) marks it persistent. The '&'
    # is a compiler marker, stripped before the name is emitted. The scope prefix
    # is skipped by testing only the segment after the last '.'.
    def _is_temp_array(self, arr):
        return self._var_is_temp(arr)

    # Writing a value by index: arr[i] = val
    def array_assign(self, items):
        arr = self._check_var_name(str(items[0]))
        i = items[1]
        val = items[3] # items[2] is the "<-" token, so the value is in items[3]

        # Unwrap COUNTRY_TAG sentinel
        if isinstance(val, tuple) and val[0] == "COUNTRY_TAG":
            val = val[1]

        is_temp = self._is_temp_array(arr)
        target = f"{self._strip_persist(arr)}^{i}"
        cmd = "set_temp_variable" if is_temp else "set_variable"
        return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", target, "=", val)]))

    # Reading a value by index: arr[i]
    def array_access(self, items):
        arr = self._strip_persist(self._check_var_name(str(items[0])))
        i = items[1]
        return f"{arr}^{i}"

    # Reading array size: arr[].size()
    def array_size(self, items):
        arr = self._strip_persist(self._check_var_name(str(items[0])))
        return f"{arr}^num"

    # arr[].rand_idx() / arr[].rand() — intermediate node, finalized by
    # array_rand_assign with the assignment's LHS as the destination variable.
    def array_rand(self, items):
        arr = self._strip_persist(self._check_var_name(str(items[0])))
        method = str(items[1])
        return ("ARRAYRAND", arr, method)

    # var = arr[].rand_idx()  ->  random valid index 0..size-1 into var
    # var = arr[].rand()      ->  random element of arr into var
    def array_rand_assign(self, items):
        var = self._check_var_name(str(items[0]))
        _, arr, method = items[2]
        is_temp = self._var_is_temp(var)
        dst = self._strip_persist(var)
        cmd = "set_temp_variable_to_random" if is_temp else "set_variable_to_random"

        if method == "rand_idx":
            # Engine range is half-open [min, max); max=arr^num (=size) yields
            # 0..size-1 exactly — the valid index range, no +1 needed.
            body = f"var={dst} min=0 max={arr}^num integer=yes"
            return ("RAW_INLINE", cmd, body)

        # method == "rand": pick a random index into a temp, then read the
        # element arr^idx into the destination variable.
        tmp = f"_hsl_randidx{self._gensym}"
        self._gensym += 1
        idx_call = ("RAW_INLINE", "set_temp_variable_to_random",
                    f"var={tmp} min=0 max={arr}^num integer=yes")
        set_cmd = "set_temp_variable" if is_temp else "set_variable"
        read = ("ASSIGN", set_cmd, "=",
                ("BLOCK", [("ASSIGN", dst, "=", f"{arr}^{tmp}")]))
        return [idx_call, read]

    # Array methods (clear, add, remove)
    def array_method(self, items):
        arr = self._check_var_name(str(items[0]))
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
        is_temp = self._is_temp_array(arr)
        name = self._strip_persist(arr)
        rem_cmd = "remove_from_temp_array" if is_temp else "remove_from_array"

        if method == "add":
            cmd = "add_to_temp_array" if is_temp else "add_to_array"
            return ("ASSIGN", cmd, "=", ("BLOCK", [("ASSIGN", name, "=", val)]))
        elif method == "erase":
            # Remove by VALUE: remove_from_array = { array=name value=v }
            if val is None:
                raise ValueError("erase() needs a value: arr[].erase(v)")
            return ("RAW_INLINE", rem_cmd, f"array={name} value={val}")
        elif method == "remove_at":
            # Remove by INDEX: remove_from_array = { array=name index=i }
            if val is None:
                raise ValueError("remove_at() needs an index: arr[].remove_at(i)")
            return ("RAW_INLINE", rem_cmd, f"array={name} index={val}")
        elif method == "pop":
            # Remove the LAST element: remove_from_array = { array=name }.
            # Does not return the removed value.
            if val is not None:
                raise ValueError("pop() takes no argument: arr[].pop()")
            return ("RAW_INLINE", rem_cmd, f"array={name}")
        elif method == "resize":
            # One-arg form resize(N): new elements default to 0 (engine default),
            # so no `value` is emitted. resize(N, V) goes through array_minmax.
            if val is None:
                raise ValueError("resize() needs a size: arr[].resize(n) or arr[].resize(n, v)")
            cmd = "resize_temp_array" if is_temp else "resize_array"
            return ("RAW_INLINE", cmd, f"array={name} size={val}")
        elif method == "clear":
            cmd = "clear_temp_array" if is_temp else "clear_array"
            return ("ASSIGN", cmd, "=", name)
        else:
            raise ValueError(f"Compilation Error: Unknown array method '.{method}()'")

    # Clearing an array: arr[] <- null
    # Temp arrays (leading '_') map to clear_temp_array, which HoI4 does provide.
    def clear_arr(self, items):
        arr = self._check_var_name(str(items[0]))
        cmd = "clear_temp_array" if self._is_temp_array(arr) else "clear_array"
        return ("ASSIGN", cmd, "=", self._strip_persist(arr))

    # Two-argument array search: arr[].min(value, index) / arr[].max(value, index)
    #   .min -> find_lowest_in_array,  .max -> find_highest_in_array
    # `value` and `index` are the output variables the engine writes into.
    def array_minmax(self, items):
        arr    = self._check_var_name(str(items[0]))
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
        elif method == "resize":
            # Two-arg form resize(size, value): explicit default value for new
            # elements. (One-arg resize(size) is handled in array_method.)
            is_temp = self._is_temp_array(arr)
            rcmd = "resize_temp_array" if is_temp else "resize_array"
            body = (f"array={self._strip_persist(arr)} "
                    f"size={self._strip_persist(str(value))} "
                    f"value={self._strip_persist(str(index))}")
            return ("RAW_INLINE", rcmd, body)
        else:
            raise ValueError(
                f"Unknown two-argument array method '.{method}()'; expected 'min' or 'max'."
            )

        block_items = [
            ("ASSIGN", "array", "=", self._strip_persist(arr)),
            ("ASSIGN", "value", "=", self._strip_persist(str(value))),
        ]
        # '_' is a throwaway index placeholder — omit the index line entirely.
        if str(index) != "_":
            block_items.append(("ASSIGN", "index", "=", self._strip_persist(str(index))))

        return ("ASSIGN", cmd, "=", ("BLOCK", block_items))
