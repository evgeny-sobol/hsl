from lark import Transformer
from modules.transformers.arrays       import ArraysMixin
from modules.transformers.assignments  import AssignmentsMixin
from modules.transformers.blocks       import BlocksMixin
from modules.transformers.conditions   import ConditionsMixin
from modules.transformers.control_flow import ControlFlowMixin
from modules.transformers.functions    import FunctionsMixin
from modules.transformers.linq         import LinqMixin
from modules.transformers.macros       import MacrosMixin
from modules.transformers.misc         import MiscMixin
from modules.transformers.values       import ValuesMixin

class HslTransformer(
    ArraysMixin,
    AssignmentsMixin,
    BlocksMixin,
    ConditionsMixin,
    ControlFlowMixin,
    FunctionsMixin,
    LinqMixin,
    MacrosMixin,
    MiscMixin,
    ValuesMixin,
    Transformer
):
    # Explicitly define external_macros as a keyword argument with a default value of None
    def __init__(self, external_macros=None):
        # Initialize the base Lark Transformer class WITHOUT passing our custom argument
        super().__init__()
        # Store the macros dictionary in the transformer instance
        # If external_macros was passed, we use it; otherwise, we start with an empty dict
        self.macros = external_macros if external_macros is not None else {}
        # Monotonic counter for compiler-generated temp names (e.g. randi's
        # inclusive-max intermediate). Unique within one transform pass.
        self._gensym = 0

    def start(self, items):
        # Filter out None values (which are left by macro definitions)
        items = [item for item in items if item is not None]
        # Compile arithmetic expression trees into accumulator value-blocks.
        return self._lift_seq(items)

    # ---- arithmetic -> accumulator value-blocks -----------------------------
    # An arithmetic expression is parsed into a tree:
    #   ("MATH", op, left, right)   binary op, op in + - * / % **
    #   ("MATHFN", name, [args])    builtin: sqrt / round / clamp
    # HoI4 has no inline math, but it *does* have accumulator "value = { ... }"
    # blocks (see script_math_functions docs): a block starts from `value = X`
    # and applies a sequence of ops (add/subtract/multiply/divide/modulo/pow/
    # root/round/clamp) left to right. We compile a whole tree into ONE such
    # nested block, so `(1 + 2) * 3` becomes
    #   value = { value = { value = 1  add = 2 }  multiply = 3 }
    # No temp variables are generated. Operator precedence and associativity are
    # already baked into the tree by the grammar cascade, so compilation is a
    # straight structural walk.
    #
    # A statement sequence may contain nested lists (operator-macro expansions,
    # folded conditions); generate_hoi4_code flattens those at render time, so we
    # flatten here first — otherwise MATH nodes hiding inside a spliced list are
    # never visited.
    _MATH_CMD = {
        "+":  "add",
        "-":  "subtract",
        "*":  "multiply",
        "/":  "divide",
        "%":  "mod",
        "**": "pow",
    }

    @staticmethod
    def _scope_name(v):
        """Normalise a scope head to its bare name.

        A scope head is either a plain name token (PREV, THIS, a variable) or a
        country tag. The tag reaches scope position as a raw COUNTRY_TAG token
        ("$HAI") rather than the ("COUNTRY_TAG", name) tuple that the value-level
        rule produces, so strip a leading '$' here.
        """
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return v[1]
        s = str(v)
        return s[1:] if s.startswith("$") else s

    @staticmethod
    def _unwrap_tag(v):
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return v[1]
        return v

    def _flatten(self, items):
        # Splice nested lists (macro expansions / folded conditions) into one level.
        out = []
        for it in items:
            if isinstance(it, list):
                out.extend(self._flatten(it))
            else:
                out.append(it)
        return out

    # --- variable lifetime marker ('&' = persistent; default = temp) ---------
    # New semantics: a bare variable is TEMP by default. A leading '&' on the
    # name (after any scope prefix, e.g. `&foo`, `global.&foo`) marks it
    # PERSISTENT. The '&' is a compiler marker only and is stripped before the
    # name is emitted to HoI4 script.
    def _resolve_breaks(self, block_items):
        """Rewrite ("BREAK",) markers in a loop body into a flag-setting
        statement, recursing into nested blocks (a break may sit inside an if).
        Returns (new_items, flag_name_or_None). The flag is allocated once per
        loop that contains at least one break; the caller declares it in the
        loop header as `break = <flag>`.
        """
        flag = None

        def walk(items):
            nonlocal flag
            out = []
            for it in items:
                if isinstance(it, tuple) and it and it[0] == "BREAK":
                    if flag is None:
                        flag = f"hsl_break{self._gensym}"
                        self._gensym += 1
                    out.append(("ASSIGN", "set_temp_variable", "=",
                                ("BLOCK", [("ASSIGN", flag, "=", 1)])))
                elif (isinstance(it, tuple) and len(it) == 4 and it[0] == "ASSIGN"
                      and isinstance(it[3], tuple) and it[3] and it[3][0] == "BLOCK"):
                    # Recurse into a nested block (e.g. an if body), preserving
                    # any trailing scope_var element of the BLOCK tuple.
                    blk = it[3]
                    new_inner = walk(list(blk[1]))
                    new_blk = ("BLOCK", new_inner) + tuple(blk[2:])
                    out.append((it[0], it[1], it[2], new_blk))
                else:
                    out.append(it)
            return out

        new_items = walk(list(block_items))
        return new_items, flag

    @staticmethod
    def _var_is_temp(name):
        seg = str(name).rsplit(".", 1)[-1]
        return not seg.startswith("&")

    @staticmethod
    def _strip_persist(name):
        # Remove the '&' marker from the last dotted segment for output.
        s = str(name)
        head, sep, tail = s.rpartition(".")
        if tail.startswith("&"):
            return f"{head}{sep}{tail[1:]}"
        return s

    @staticmethod
    def _check_var_name(name):
        # Under the new scheme a variable is temp by default and '&' marks
        # persistent; a leading '_' is no longer a temp marker and is rejected so
        # old '_'-prefixed code fails loudly instead of silently becoming a
        # differently-scoped variable. Checks the last dotted segment (after any
        # scope prefix), and after any '&' marker.
        seg = str(name).rsplit(".", 1)[-1]
        if seg.startswith("&"):
            seg = seg[1:]
        if seg.startswith("_"):
            raise ValueError(
                f"Variable name '{name}' starts with '_'. Underscores are no "
                f"longer a temp marker: variables are temp by default, and '&' "
                f"marks a persistent variable (e.g. &{seg.lstrip('_')}). Rename "
                f"to drop the leading underscore."
            )
        return name

    def _is_expr(self, v):
        return isinstance(v, tuple) and v and v[0] in ("MATH", "MATHFN")

    def _expr_to_str(self, v):
        # Best-effort source-like rendering of an expression tree, for error
        # messages. Not a full round-trip — just enough to point the user at the
        # offending expression.
        if isinstance(v, tuple) and v and v[0] == "MATH":
            return f"{self._expr_to_str(v[2])} {v[1]} {self._expr_to_str(v[3])}"
        if isinstance(v, tuple) and v and v[0] == "MATHFN":
            inner = ", ".join(self._expr_to_str(a) for a in v[2])
            return f"{v[1]}({inner})"
        if isinstance(v, tuple) and v and v[0] == "COUNTRY_TAG":
            return f"${v[1]}"
        return str(v)

    def _acc_operand(self, v):
        # Value that goes on the right of an accumulator op (value=/add=/...).
        # A sub-expression becomes a nested ("BLOCK", <accumulator steps>);
        # a scalar is emitted verbatim (tags unwrapped to bare identifiers).
        if self._is_expr(v):
            return ("BLOCK", self._compile_expr(v))
        return self._unwrap_tag(v)

    def _compile_expr(self, node):
        # Returns a list of accumulator ASSIGN steps for one expression node,
        # suitable as the body of a ("BLOCK", ...). The list always begins with
        # a `value = ...` seed.
        if node[0] == "MATH":
            _, op, left, right = node
            cmd = self._MATH_CMD.get(op, "unknown_math_op")
            return [
                ("ASSIGN", "value", "=", self._acc_operand(left)),
                ("ASSIGN", cmd,     "=", self._acc_operand(right)),
            ]

        # MATHFN
        _, name, args = node
        seed = ("ASSIGN", "value", "=", self._acc_operand(args[0]))
        if name == "sqrt":
            # root of degree 2; second arg would be the degree if we ever add it.
            return [seed, ("ASSIGN", "root", "=", 2)]
        if name == "round":
            return [seed, ("ASSIGN", "round", "=", "yes")]
        if name == "clamp":
            lo = self._acc_operand(args[1])
            hi = self._acc_operand(args[2])
            return [seed, ("ASSIGN", "clamp", "=",
                           ("BLOCK", [("ASSIGN", "min", "=", lo),
                                      ("ASSIGN", "max", "=", hi)]))]
        return [seed, ("ASSIGN", "unknown_math_func", "=", name)]

    def _lift_seq(self, stmts):
        out = []
        for s in self._flatten(stmts):
            # A bare RANDCALL (rand*() used as a statement, not `var = rand*()`)
            # is finalized here into its effect(s). rand_assign handles the
            # assignment form before reaching this point.
            if isinstance(s, tuple) and s and s[0] == "RANDCALL":
                fin = self._finalize_randcall(s)
                if isinstance(fin, list):
                    out.extend(self._lift_stmt(x) for x in fin)
                else:
                    out.append(self._lift_stmt(fin))
            else:
                out.append(self._lift_stmt(s))
        return out

    def _lift_value(self, v):
        # Rewrite a value slot: expression -> accumulator BLOCK; BLOCK -> recurse
        # into its children; scalar -> unchanged.
        if self._is_expr(v):
            return ("BLOCK", self._compile_expr(v))
        if isinstance(v, tuple) and v and v[0] == "BLOCK":
            inner = self._flatten(v[1])
            scope_var = v[2] if len(v) > 2 else None
            new_inner = [self._lift_stmt(ist) for ist in inner]
            if scope_var is not None:
                return ("BLOCK", new_inner, scope_var)
            return ("BLOCK", new_inner)
        return v

    def _lift_stmt(self, s):
        # Rewrite any arithmetic trees inside a statement's value slot in place.
        if not (isinstance(s, tuple) and s and s[0] == "ASSIGN" and len(s) == 4):
            return s
        _, L, OP, R = s
        return ("ASSIGN", L, OP, self._lift_value(R))
