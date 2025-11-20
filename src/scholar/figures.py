import os
import matplotlib.pyplot as plt
def bar_fig(path, title, labels, values):
    plt.figure()
    plt.bar(labels, values)
    plt.title(title)
    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path)
    plt.close()
