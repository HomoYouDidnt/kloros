"""
Auto-generated predictive modeler - model=ewma, history=300s, horizon=60s.
"""
import time
import logging
from collections import deque
from kloros.orchestration.chem_bus_v2 import ChemPub

HISTORY_WINDOW_SEC = 300
PREDICTION_HORIZON_SEC = 60
MODEL_TYPE = "ewma"
POLL_INTERVAL = 3.21
BATCH_SIZE = 10
TIMEOUT_SEC = 30
LOG_LEVEL = "WARNING"

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def predict_linear(history):
    if len(history) < 2:
        return history[-1] if history else 0.0
    x = list(range(len(history)))
    y = list(history)
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
    intercept = (sum_y - slope * sum_x) / n
    return slope * n + intercept


def predict_ewma(history, alpha=0.3):
    if not history:
        return 0.0
    ewma = history[0]
    for val in history[1:]:
        ewma = alpha * val + (1 - alpha) * ewma
    return ewma


def predict_arima(history):
    return predict_ewma(history, alpha=0.5)


def main():
    pub = ChemPub()
    history = deque(maxlen=int(HISTORY_WINDOW_SEC / POLL_INTERVAL))

    logger.info(f"Predictive modeler started: model={MODEL_TYPE}, history={HISTORY_WINDOW_SEC}s")

    while True:
        try:
            current_value = time.time() % 100

            history.append(current_value)

            if len(history) >= 5:
                if MODEL_TYPE == "linear":
                    prediction = predict_linear(history)
                elif MODEL_TYPE == "ewma":
                    prediction = predict_ewma(history)
                elif MODEL_TYPE == "arima":
                    prediction = predict_arima(history)
                else:
                    prediction = sum(history) / len(history)

                logger.debug(f"Current: {current_value:.2f}, Predicted: {prediction:.2f}")

                if prediction > 80:
                    logger.warning(f"Predicted value {prediction:.2f} exceeds threshold")
                    pub.signal("PREDICTED_LOAD")

            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Predictor error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
