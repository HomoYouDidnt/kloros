"""Calibration metrics for uncertainty quantification."""
import numpy as np
from typing import List, Tuple, Dict, Any


def compute_ece(predictions: List[float], labels: List[int], n_bins: int = 10) -> float:
    """Compute Expected Calibration Error.

    ECE measures how well predicted confidences match actual accuracy.

    Args:
        predictions: Predicted confidences [0,1]
        labels: Ground truth labels {0, 1}
        n_bins: Number of bins for calibration

    Returns:
        ECE score (lower is better)
    """
    if not predictions or not labels or len(predictions) != len(labels):
        return 0.0

    predictions = np.array(predictions)
    labels = np.array(labels)

    # Create bins
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        # Find predictions in this bin
        in_bin = (predictions >= bin_edges[i]) & (predictions < bin_edges[i + 1])

        if i == n_bins - 1:
            # Include right edge in last bin
            in_bin = (predictions >= bin_edges[i]) & (predictions <= bin_edges[i + 1])

        if not in_bin.any():
            continue

        # Confidence (average predicted probability in bin)
        bin_confidence = predictions[in_bin].mean()

        # Accuracy (actual fraction correct in bin)
        bin_accuracy = labels[in_bin].mean()

        # Bin weight (fraction of samples in bin)
        bin_weight = in_bin.sum() / len(predictions)

        # Add weighted calibration error
        ece += bin_weight * abs(bin_confidence - bin_accuracy)

    return float(ece)


def compute_mce(predictions: List[float], labels: List[int], n_bins: int = 10) -> float:
    """Compute Maximum Calibration Error.

    MCE is the maximum calibration error across all bins.

    Args:
        predictions: Predicted confidences [0,1]
        labels: Ground truth labels {0, 1}
        n_bins: Number of bins

    Returns:
        MCE score (lower is better)
    """
    if not predictions or not labels or len(predictions) != len(labels):
        return 0.0

    predictions = np.array(predictions)
    labels = np.array(labels)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    max_error = 0.0

    for i in range(n_bins):
        in_bin = (predictions >= bin_edges[i]) & (predictions < bin_edges[i + 1])

        if i == n_bins - 1:
            in_bin = (predictions >= bin_edges[i]) & (predictions <= bin_edges[i + 1])

        if not in_bin.any():
            continue

        bin_confidence = predictions[in_bin].mean()
        bin_accuracy = labels[in_bin].mean()
        error = abs(bin_confidence - bin_accuracy)

        max_error = max(max_error, error)

    return float(max_error)


def compute_brier_score(predictions: List[float], labels: List[int]) -> float:
    """Compute Brier score (mean squared error of probabilities).

    Args:
        predictions: Predicted confidences [0,1]
        labels: Ground truth labels {0, 1}

    Returns:
        Brier score (lower is better)
    """
    if not predictions or not labels or len(predictions) != len(labels):
        return 0.0

    predictions = np.array(predictions)
    labels = np.array(labels)

    return float(((predictions - labels) ** 2).mean())


def calibrate_predictions(
    predictions: List[float],
    labels: List[int],
    method: str = "platt"
) -> Tuple[List[float], Dict[str, Any]]:
    """Calibrate predictions to improve confidence estimates.

    Args:
        predictions: Predicted confidences [0,1]
        labels: Ground truth labels {0, 1}
        method: Calibration method ('platt' or 'isotonic')

    Returns:
        (calibrated_predictions, calibration_params) tuple
    """
    if not predictions or not labels or len(predictions) != len(labels):
        return predictions, {}

    predictions = np.array(predictions)
    labels = np.array(labels)

    if method == "platt":
        # Platt scaling: fit logistic regression
        from sklearn.linear_model import LogisticRegression

        # Reshape for sklearn
        X = predictions.reshape(-1, 1)
        y = labels

        # Fit calibration model
        calibrator = LogisticRegression()
        calibrator.fit(X, y)

        # Calibrate predictions
        calibrated = calibrator.predict_proba(X)[:, 1]

        return calibrated.tolist(), {
            "method": "platt",
            "coef": float(calibrator.coef_[0][0]),
            "intercept": float(calibrator.intercept_[0])
        }

    elif method == "isotonic":
        # Isotonic regression: fit monotonic function
        from sklearn.isotonic import IsotonicRegression

        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(predictions, labels)

        calibrated = calibrator.predict(predictions)

        return calibrated.tolist(), {
            "method": "isotonic",
            "n_points": len(calibrator.X_thresholds_)
        }

    else:
        raise ValueError(f"Unknown calibration method: {method}")


def reliability_diagram_data(
    predictions: List[float],
    labels: List[int],
    n_bins: int = 10
) -> Dict[str, List[float]]:
    """Generate data for reliability diagram.

    Args:
        predictions: Predicted confidences [0,1]
        labels: Ground truth labels {0, 1}
        n_bins: Number of bins

    Returns:
        Dict with bin_centers, accuracies, confidences, counts
    """
    if not predictions or not labels:
        return {
            "bin_centers": [],
            "accuracies": [],
            "confidences": [],
            "counts": []
        }

    predictions = np.array(predictions)
    labels = np.array(labels)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    accuracies = []
    confidences = []
    counts = []

    for i in range(n_bins):
        in_bin = (predictions >= bin_edges[i]) & (predictions < bin_edges[i + 1])

        if i == n_bins - 1:
            in_bin = (predictions >= bin_edges[i]) & (predictions <= bin_edges[i + 1])

        if not in_bin.any():
            continue

        bin_center = (bin_edges[i] + bin_edges[i + 1]) / 2
        bin_confidence = predictions[in_bin].mean()
        bin_accuracy = labels[in_bin].mean()
        bin_count = in_bin.sum()

        bin_centers.append(float(bin_center))
        confidences.append(float(bin_confidence))
        accuracies.append(float(bin_accuracy))
        counts.append(int(bin_count))

    return {
        "bin_centers": bin_centers,
        "accuracies": accuracies,
        "confidences": confidences,
        "counts": counts
    }
