"""Bug injection library with string-based and AST-based mutations."""
from .base import BugSpec, InjectionResult
from .string_based import (
    RemoveColon,
    MissingParen,
    MissingQuote,
    WrongOperator,
    TypoVariable,
    OffByOneString,
)
from .ast_based import (
    OffByOneRange,
    FloatTruncation,
    EarlyReturn,
)

__all__ = [
    'BugSpec',
    'InjectionResult',
    # String-based (easy/medium)
    'RemoveColon',
    'MissingParen',
    'MissingQuote',
    'WrongOperator',
    'TypoVariable',
    'OffByOneString',
    # AST-based (hard)
    'OffByOneRange',
    'FloatTruncation',
    'EarlyReturn',
]
