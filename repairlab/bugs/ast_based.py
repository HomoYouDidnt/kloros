"""AST-based bug mutations for complex transformations."""
import ast
from .base import BugSpec, InjectionResult


class _RangeUpperBoundReducer(ast.NodeTransformer):
    """Reduce upper bound of range() by 1."""
    def __init__(self):
        self.mutated = False

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == "range"
            and len(node.args) in (1, 2) and not self.mutated):
            # Handle range(b) or range(a, b)
            if len(node.args) == 1:
                b = node.args[0]
            else:
                b = node.args[1]
            
            # Create b - 1
            new_b = ast.BinOp(
                left=ast.copy_location(b, b),
                op=ast.Sub(),
                right=ast.Constant(value=1)
            )
            
            if len(node.args) == 1:
                node.args[0] = new_b
            else:
                node.args[1] = new_b
            
            self.mutated = True
        return node


class OffByOneRange(BugSpec):
    """Reduce range upper bound by 1 causing off-by-one error."""
    bug_id = "off_by_one_range_ast"
    description = "Upper bound reduced by 1 in range(), skipping last iteration"
    difficulty = "hard"

    def applies(self, source: str) -> bool:
        try:
            tree = ast.parse(source)
            class Finder(ast.NodeVisitor):
                found = False
                def visit_Call(self, n):
                    if isinstance(n.func, ast.Name) and n.func.id == "range":
                        self.found = True
            f = Finder()
            f.visit(tree)
            return f.found
        except SyntaxError:
            return False

    def inject(self, source: str) -> InjectionResult:
        tree = ast.parse(source)
        v = _RangeUpperBoundReducer()
        new_tree = v.visit(tree)
        ast.fix_missing_locations(new_tree)
        
        if not v.mutated:
            raise RuntimeError("OffByOneRange: no eligible range() found to mutate")
        
        mutated = ast.unparse(new_tree)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )


class _DivToFloorDiv(ast.NodeTransformer):
    """Replace / with // (floor division)."""
    def __init__(self):
        self.mutated = False

    def visit_BinOp(self, node: ast.BinOp):
        self.generic_visit(node)
        if isinstance(node.op, ast.Div) and not self.mutated:
            node.op = ast.FloorDiv()
            self.mutated = True
        return node


class FloatTruncation(BugSpec):
    """Replace float division with floor division (lossy)."""
    bug_id = "float_trunc"
    description = "Floating-point division replaced with floor division (lossy)"
    difficulty = "hard"

    def applies(self, source: str) -> bool:
        try:
            tree = ast.parse(source)
            class Finder(ast.NodeVisitor):
                found = False
                def visit_BinOp(self, n):
                    if isinstance(n.op, ast.Div):
                        self.found = True
            f = Finder()
            f.visit(tree)
            return f.found
        except SyntaxError:
            return False

    def inject(self, source: str) -> InjectionResult:
        tree = ast.parse(source)
        v = _DivToFloorDiv()
        new_tree = v.visit(tree)
        ast.fix_missing_locations(new_tree)
        
        if not v.mutated:
            raise RuntimeError("FloatTruncation: no division found to mutate")
        
        mutated = ast.unparse(new_tree)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )


class _ReturnNoneInserter(ast.NodeTransformer):
    """Add early return None to break function logic."""
    def __init__(self):
        self.mutated = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        if len(node.body) > 1 and not self.mutated:
            # Insert "return None" as second statement (after first line)
            early_return = ast.Return(value=ast.Constant(value=None))
            ast.copy_location(early_return, node.body[0])
            node.body.insert(1, early_return)
            self.mutated = True
        return node


class EarlyReturn(BugSpec):
    """Insert early return None breaking function logic."""
    bug_id = "early_return"
    description = "Early 'return None' inserted, breaking function logic"
    difficulty = "hard"

    def applies(self, source: str) -> bool:
        try:
            tree = ast.parse(source)
            class Finder(ast.NodeVisitor):
                found = False
                def visit_FunctionDef(self, n):
                    if len(n.body) > 1:
                        self.found = True
            f = Finder()
            f.visit(tree)
            return f.found
        except SyntaxError:
            return False

    def inject(self, source: str) -> InjectionResult:
        tree = ast.parse(source)
        v = _ReturnNoneInserter()
        new_tree = v.visit(tree)
        ast.fix_missing_locations(new_tree)
        
        if not v.mutated:
            raise RuntimeError("EarlyReturn: no eligible function found")
        
        mutated = ast.unparse(new_tree)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )
