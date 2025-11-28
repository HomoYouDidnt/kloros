"""Sample code for bug injection testing."""


def sum_inclusive(a: int, b: int) -> int:
    """Return sum of all integers from a to b inclusive (a <= b)."""
    total = 0
    for x in range(a, b + 1):
        total += x
    return total


def mean(values):
    """Return arithmetic mean as float."""
    if not values:
        raise ValueError("empty")
    return sum(values) / len(values)


def count_evens(numbers):
    """Count even numbers in a list."""
    result = 0
    for num in numbers:
        if num % 2 == 0:
            result += 1
    return result


def fibonacci(n: int) -> int:
    """Return nth Fibonacci number (0-indexed)."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
