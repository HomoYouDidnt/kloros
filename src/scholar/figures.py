import os

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

def bar_fig(path, title, labels, values):
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for scholar figure generation. "
            "Install with: pip install matplotlib"
        )
    plt.figure()
    plt.bar(labels, values)
    plt.title(title)
    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path)
    plt.close()
