#!/usr/bin/env python3
"""
D-REAM Novelty and Anti-collapse Module
Implements behavior archives, novelty pressure, and Pareto front selection.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class BehaviorVector:
    """Behavior characterization for diversity assessment."""
    values: np.ndarray
    metadata: Dict = None

    def distance(self, other: 'BehaviorVector') -> float:
        """Calculate Euclidean distance to another behavior."""
        return float(np.linalg.norm(self.values - other.values))

    def correlation(self, other: 'BehaviorVector') -> float:
        """Calculate correlation with another behavior."""
        if np.all(self.values == 0) or np.all(other.values == 0):
            return 0.0
        return float(np.corrcoef(self.values, other.values)[0, 1])


class BehaviorArchive:
    """
    Archive of behavioral characteristics for novelty calculation.
    Maintains a fixed-size archive using FIFO replacement.
    """

    def __init__(self, k: int = 10, max_size: int = 256):
        """
        Initialize behavior archive.

        Args:
            k: Number of nearest neighbors for novelty calculation
            max_size: Maximum archive size (FIFO replacement)
        """
        self.k = k
        self.max_size = max_size
        self.vectors: List[BehaviorVector] = []

    def add(self, vec: np.ndarray, metadata: Dict = None):
        """
        Add a behavior vector to the archive.

        Args:
            vec: Behavior vector values
            metadata: Optional metadata for the behavior
        """
        behavior = BehaviorVector(vec, metadata)
        self.vectors.append(behavior)
        
        # FIFO replacement when archive is full
        if len(self.vectors) > self.max_size:
            removed = self.vectors.pop(0)
            logger.debug(f"Archive full, removed oldest behavior (size={self.max_size})")

    def novelty(self, vec: np.ndarray) -> float:
        """
        Calculate novelty as mean distance to k-nearest neighbors.

        Args:
            vec: Behavior vector to evaluate

        Returns:
            Novelty score (higher = more novel)
        """
        if not self.vectors:
            return 0.0

        behavior = BehaviorVector(vec)
        distances = [behavior.distance(v) for v in self.vectors]
        distances.sort()
        
        k_actual = min(self.k, len(distances))
        k_nearest = distances[:k_actual]
        novelty_score = float(np.mean(k_nearest)) if k_nearest else 0.0
        
        logger.debug(f"Novelty score: {novelty_score:.3f} (k={k_actual})")
        return novelty_score

    def get_diversity(self) -> float:
        """Calculate overall archive diversity."""
        if len(self.vectors) < 2:
            return 0.0

        total_dist = 0
        count = 0
        for i, v1 in enumerate(self.vectors):
            for v2 in self.vectors[i+1:]:
                total_dist += v1.distance(v2)
                count += 1

        return total_dist / count if count > 0 else 0.0


def correlation_penalty(candidate_vec: np.ndarray, 
                        champions: List[np.ndarray]) -> float:
    """
    Calculate correlation penalty vs champion set.

    Args:
        candidate_vec: Candidate behavior vector
        champions: List of champion behavior vectors

    Returns:
        Penalty in [0,1] where 1 = highly correlated (bad)
    """
    if not champions:
        return 0.0

    candidate = BehaviorVector(candidate_vec)
    correlations = []
    
    for champ_vec in champions:
        champ = BehaviorVector(champ_vec)
        corr = abs(candidate.correlation(champ))  # Use absolute correlation
        correlations.append(corr)

    penalty = max(correlations) if correlations else 0.0
    logger.debug(f"Correlation penalty: {penalty:.3f} (vs {len(champions)} champions)")
    return penalty


def pareto_front(points: List[Dict[str, float]], 
                 keys: List[str],
                 maximize: bool = True) -> List[int]:
    """
    Find Pareto-optimal points.

    Args:
        points: List of points with metric dictionaries
        keys: Keys to consider for dominance
        maximize: Whether to maximize (True) or minimize (False)

    Returns:
        Indices of points on the Pareto front
    """
    if not points:
        return []

    front = []
    n = len(points)

    for i in range(n):
        dominated = False
        
        for j in range(n):
            if i == j:
                continue

            # Check if j dominates i
            if maximize:
                # For maximization: j dominates i if j >= i in all keys and j > i in at least one
                all_geq = all(points[j].get(k, 0) >= points[i].get(k, 0) for k in keys)
                any_greater = any(points[j].get(k, 0) > points[i].get(k, 0) for k in keys)
            else:
                # For minimization: j dominates i if j <= i in all keys and j < i in at least one
                all_leq = all(points[j].get(k, 0) <= points[i].get(k, 0) for k in keys)
                any_less = any(points[j].get(k, 0) < points[i].get(k, 0) for k in keys)
                all_geq = all_leq
                any_greater = any_less

            if all_geq and any_greater:
                dominated = True
                break

        if not dominated:
            front.append(i)

    logger.info(f"Pareto front: {len(front)}/{len(points)} points")
    return front


def crowding_distance(points: List[Dict[str, float]], 
                     indices: List[int],
                     keys: List[str]) -> List[float]:
    """
    Calculate crowding distance for diversity preservation.

    Args:
        points: All points
        indices: Indices of points to evaluate
        keys: Objective keys

    Returns:
        Crowding distances for indexed points
    """
    if len(indices) <= 2:
        return [float('inf')] * len(indices)

    distances = [0.0] * len(indices)
    
    for key in keys:
        # Sort indices by this objective
        sorted_idx = sorted(indices, key=lambda i: points[i].get(key, 0))
        
        # Edge points get infinite distance
        if len(sorted_idx) > 0:
            idx_to_dist = {sorted_idx[0]: float('inf'), 
                          sorted_idx[-1]: float('inf')}
            
            # Calculate distances for interior points
            values = [points[i].get(key, 0) for i in sorted_idx]
            value_range = max(values) - min(values) if max(values) != min(values) else 1.0
            
            for j in range(1, len(sorted_idx) - 1):
                dist = (values[j+1] - values[j-1]) / value_range
                idx_to_dist[sorted_idx[j]] = idx_to_dist.get(sorted_idx[j], 0) + dist

            # Map back to distances array
            for i, idx in enumerate(indices):
                distances[i] += idx_to_dist.get(idx, 0)

    return distances


class NoveltySelection:
    """Selection mechanisms incorporating novelty and diversity."""

    @staticmethod
    def tournament_select(population: List[Dict], 
                         archive: BehaviorArchive,
                         tournament_size: int = 3,
                         novelty_weight: float = 0.3) -> Dict:
        """
        Tournament selection with novelty pressure.

        Args:
            population: List of individuals with 'fitness' and 'behavior' keys
            archive: Behavior archive for novelty calculation
            tournament_size: Number of individuals in tournament
            novelty_weight: Weight for novelty vs fitness

        Returns:
            Selected individual
        """
        if not population:
            return None

        # Ensure we don't exceed population size
        actual_size = min(tournament_size, len(population))
        
        # Random tournament
        import random
        tournament = random.sample(population, actual_size)
        
        # Score with novelty
        scored = []
        for ind in tournament:
            fitness = ind.get('fitness', 0)
            behavior = ind.get('behavior')
            
            if behavior is not None:
                novelty = archive.novelty(behavior)
            else:
                novelty = 0
                
            combined_score = (1 - novelty_weight) * fitness + novelty_weight * novelty
            scored.append((combined_score, ind))

        # Return best
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    @staticmethod
    def pareto_select(population: List[Dict],
                     objectives: List[str],
                     n_select: int) -> List[Dict]:
        """
        Select using Pareto fronts with crowding distance.

        Args:
            population: Population with objective values
            objectives: List of objective keys
            n_select: Number to select

        Returns:
            Selected individuals
        """
        if n_select >= len(population):
            return population

        selected = []
        remaining = list(range(len(population)))
        
        while len(selected) < n_select and remaining:
            # Get next Pareto front
            front_idx = pareto_front([population[i] for i in remaining], 
                                    objectives, maximize=True)
            front = [remaining[i] for i in front_idx]
            
            if len(selected) + len(front) <= n_select:
                # Add entire front
                selected.extend(front)
                remaining = [i for i in remaining if i not in front]
            else:
                # Use crowding distance for partial selection
                n_needed = n_select - len(selected)
                distances = crowding_distance(population, front, objectives)
                
                # Sort by crowding distance (higher = more diverse)
                sorted_front = sorted(zip(front, distances), 
                                    key=lambda x: x[1], reverse=True)
                selected.extend([idx for idx, _ in sorted_front[:n_needed]])
                break

        return [population[i] for i in selected]


def extract_behavior_vector(individual: Dict, 
                           feature_keys: List[str]) -> np.ndarray:
    """
    Extract behavior vector from individual metrics.

    Args:
        individual: Individual with metrics
        feature_keys: Keys to use for behavior characterization

    Returns:
        Behavior vector as numpy array
    """
    values = []
    for key in feature_keys:
        val = individual.get(key, 0.0)
        values.append(val)

    vec = np.array(values, dtype=np.float32)
    
    # Normalize to unit sphere for consistent distance metrics
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
        
    return vec
