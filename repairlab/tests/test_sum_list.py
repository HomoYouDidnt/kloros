"""Tests that pass on correct code, fail when bugs are injected."""
import pytest
import sys
from pathlib import Path

# Ensure we can import from repairlab
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from repairlab.samples.sum_list import sum_inclusive, mean, count_evens, fibonacci


def test_sum_inclusive_small():
    """Test sum_inclusive with small ranges."""
    assert sum_inclusive(1, 3) == 6  # 1+2+3
    assert sum_inclusive(5, 5) == 5  # Single number
    assert sum_inclusive(2, 4) == 9  # 2+3+4


def test_sum_inclusive_larger():
    """Test sum_inclusive with larger ranges."""
    # 10..20 inclusive = average(10,20)*count = 15*11 = 165
    assert sum_inclusive(10, 20) == 165
    assert sum_inclusive(0, 10) == 55  # 0+1+2+...+10


def test_sum_inclusive_edge_cases():
    """Test sum_inclusive edge cases."""
    assert sum_inclusive(0, 0) == 0
    assert sum_inclusive(-5, -3) == -12  # -5 + -4 + -3


def test_mean_basic():
    """Test mean with simple lists."""
    assert mean([1, 2, 3, 4]) == 2.5
    assert mean([5]) == 5.0
    assert mean([10, 20, 30]) == 20.0


def test_mean_floats():
    """Test mean preserves floating point precision."""
    result = mean([1, 2, 3])
    assert isinstance(result, float)
    assert result == 2.0


def test_mean_raises_on_empty():
    """Test mean raises on empty list."""
    with pytest.raises(ValueError):
        mean([])


def test_count_evens_basic():
    """Test count_evens with various inputs."""
    assert count_evens([1, 2, 3, 4, 5, 6]) == 3  # 2,4,6
    assert count_evens([1, 3, 5]) == 0  # No evens
    assert count_evens([2, 4, 6, 8]) == 4  # All evens


def test_count_evens_edge():
    """Test count_evens edge cases."""
    assert count_evens([]) == 0
    assert count_evens([0]) == 1  # 0 is even


def test_fibonacci_small():
    """Test Fibonacci for small n."""
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5


def test_fibonacci_larger():
    """Test Fibonacci for larger n."""
    assert fibonacci(10) == 55
    assert fibonacci(15) == 610


# These tests will fail when:
# - RemoveColon: Syntax error on function definitions
# - MissingParen: Syntax error on function calls
# - MissingQuote: Syntax error on strings
# - WrongOperator: count_evens logic breaks (== becomes !=)
# - TypoVariable: NameError when 'result' becomes 'resutl'
# - OffByOne: sum_inclusive/fibonacci off by one iteration
# - FloatTruncation: mean returns int instead of float
# - EarlyReturn: Functions return None prematurely
