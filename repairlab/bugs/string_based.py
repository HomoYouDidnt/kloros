"""Simple string-based bug mutations (ported from spica_bug_injector)."""
from typing import Optional
from .base import BugSpec, InjectionResult


class RemoveColon(BugSpec):
    """Remove trailing colon from function/class definitions."""
    bug_id = "remove_colon"
    description = "Missing colon at end of def/class/if/for/while statement"
    difficulty = "easy"

    def applies(self, source: str) -> bool:
        return any(line.rstrip().endswith(':') for line in source.splitlines())

    def inject(self, source: str) -> InjectionResult:
        lines = source.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.rstrip().endswith(':'):
                lines[i] = line.rstrip().rstrip(':') + '\n'
                break
        else:
            raise RuntimeError("RemoveColon: no line ending with ':' found")
        
        return InjectionResult(
            ''.join(lines),
            self.bug_id,
            self.description,
            self.difficulty
        )


class MissingParen(BugSpec):
    """Remove closing parenthesis from function calls."""
    bug_id = "missing_paren"
    description = "Missing closing parenthesis in function call"
    difficulty = "easy"

    def applies(self, source: str) -> bool:
        return any('(' in line and ')' in line for line in source.splitlines())

    def inject(self, source: str) -> InjectionResult:
        lines = source.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if '(' in line and ')' in line:
                idx = line.rfind(')')
                if line.endswith('\n'):
                    lines[i] = line[:idx] + line[idx+1:-1] + '\n'
                else:
                    lines[i] = line[:idx] + line[idx+1:]
                break
        else:
            raise RuntimeError("MissingParen: no line with parentheses found")
        
        return InjectionResult(
            ''.join(lines),
            self.bug_id,
            self.description,
            self.difficulty
        )


class MissingQuote(BugSpec):
    """Remove opening quote from string literals."""
    bug_id = "missing_quote"
    description = "Missing opening quote in string literal"
    difficulty = "easy"

    def applies(self, source: str) -> bool:
        return any(line.count('"') >= 2 for line in source.splitlines())

    def inject(self, source: str) -> InjectionResult:
        lines = source.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.count('"') >= 2:
                result = line.replace('"', '', 1)
                if line.endswith('\n') and not result.endswith('\n'):
                    result += '\n'
                lines[i] = result
                break
        else:
            raise RuntimeError("MissingQuote: no line with quotes found")
        
        return InjectionResult(
            ''.join(lines),
            self.bug_id,
            self.description,
            self.difficulty
        )


class WrongOperator(BugSpec):
    """Swap equality operator with inequality."""
    bug_id = "wrong_operator"
    description = "Comparison operator == replaced with !="
    difficulty = "medium"

    def applies(self, source: str) -> bool:
        return '==' in source

    def inject(self, source: str) -> InjectionResult:
        if '==' not in source:
            raise RuntimeError("WrongOperator: no == operator found")
        
        mutated = source.replace('==', '!=', 1)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )


class TypoVariable(BugSpec):
    """Introduce typo in common variable name."""
    bug_id = "typo_variable"
    description = "Variable name typo: 'result' -> 'resutl'"
    difficulty = "easy"

    def applies(self, source: str) -> bool:
        return 'result' in source and 'result' not in ['@', '#']

    def inject(self, source: str) -> InjectionResult:
        if 'result' not in source:
            raise RuntimeError("TypoVariable: no 'result' variable found")
        
        mutated = source.replace('result', 'resutl', 1)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )


class OffByOneString(BugSpec):
    """Add range(1, ...) making off-by-one error (string-based)."""
    bug_id = "off_by_one_string"
    description = "range() changed to range(1, ...) causing off-by-one"
    difficulty = "medium"

    def applies(self, source: str) -> bool:
        return 'range(' in source and 'range(1,' not in source

    def inject(self, source: str) -> InjectionResult:
        if 'range(' not in source or 'range(1,' in source:
            raise RuntimeError("OffByOneString: no eligible range() found")
        
        mutated = source.replace('range(', 'range(1, ', 1)
        return InjectionResult(
            mutated,
            self.bug_id,
            self.description,
            self.difficulty
        )
