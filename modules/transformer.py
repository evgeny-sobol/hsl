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

    def start(self, items):
        # Filter out None values (which are left by macro definitions)
        return [item for item in items if item is not None]
