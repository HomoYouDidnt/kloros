from __future__ import annotations
from typing import Optional
import os
import random

try:
    import numpy as np
except Exception:
    np = None


def seed_everything(seed: Optional[int] = None) -> int:
    """Seed Python (and NumPy if present). Returns the seed actually used."""
    if seed is None:
        # Allow env override to make tests reproducible across runners
        env = os.environ.get("DREAM_GLOBAL_SEED")
        seed = int(env) if env is not None else 1337
    random.seed(seed)
    if np is not None:
        np.random.seed(seed)
    return seed


def get_rng(seed: Optional[int] = None):
    """Return a NumPy Generator if available, else a Python Random instance."""
    s = seed_everything(seed)
    if np is not None and hasattr(np.random, "default_rng"):
        return np.random.default_rng(s)
    return random.Random(s)


class RandomState:
    """
    Compatibility wrapper for tests that expect a RandomState object.

    Provides both NumPy-style and Python random methods.
    """

    def __init__(self, seed: Optional[int] = None):
        self.seed_val = seed_everything(seed)
        self.seed = self.seed_val  # Expose as .seed for test compatibility
        self._rng = get_rng(seed)

    def randint(self, low, high=None):
        """Random integer in [low, high) or [0, low) if high is None."""
        if high is None:
            high = low
            low = 0
        if hasattr(self._rng, 'integers'):
            return self._rng.integers(low, high)
        return self._rng.randint(low, high - 1)

    def random(self):
        """Random float in [0.0, 1.0)."""
        if hasattr(self._rng, 'random'):
            return self._rng.random()
        return self._rng.random()

    def uniform(self, low, high, size=None):
        """Random float in [low, high) or array of shape `size`."""
        if np is not None and size is not None:
            # NumPy path with size parameter
            if hasattr(self._rng, 'uniform'):
                return self._rng.uniform(low, high, size=size)
            # Fallback: generate array using Python random
            import array
            if isinstance(size, int):
                return [self._rng.uniform(low, high) for _ in range(size)]
            # Multi-dimensional size tuple
            result = []
            total = 1
            for dim in size:
                total *= dim
            vals = [self._rng.uniform(low, high) for _ in range(total)]
            if np is not None:
                return np.array(vals).reshape(size)
            return vals
        # Scalar path
        if hasattr(self._rng, 'uniform'):
            return self._rng.uniform(low, high)
        return self._rng.uniform(low, high)

    def choice(self, seq):
        """Random element from sequence."""
        if hasattr(self._rng, 'choice'):
            return self._rng.choice(seq)
        return self._rng.choice(seq)

    def shuffle(self, seq):
        """Shuffle sequence in place."""
        if hasattr(self._rng, 'shuffle'):
            self._rng.shuffle(seq)
        else:
            self._rng.shuffle(seq)
