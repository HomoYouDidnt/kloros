import os, csv, json
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path
from collections import defaultdict

base = "/home/kloros/metrics"
voice_csv = os.path.join(base, "voice.csv")
rag_csv = os.path.join(base, "rag.csv")

def read_csv(path):
    rows = []
    if not os.path.exists(path): return rows
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r: rows.append(row)
    return rows

def read_jsonl(path):
    """Read JSONL file and return list of dicts."""
    rows = []
    if not os.path.exists(path): return rows
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except:
                    pass
    return rows

def plot_series(xs, ys, title, ylabel, out):
    plt.figure()
    plt.plot(xs, ys, marker="o")
    plt.title(title)
    plt.xlabel("time")
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out)
    plt.close()

def plot_bar(labels, values, title, ylabel, out):
    """Plot bar chart."""
    plt.figure(figsize=(10, 6))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out)
    plt.close()

def plot_pie(labels, sizes, title, out):
    """Plot pie chart."""
    plt.figure(figsize=(8, 8))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    plt.title(title)
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(out)
    plt.close()

os.makedirs(base, exist_ok=True)

voice = read_csv(voice_csv)
if voice:
    xs = [row["ts"] for row in voice]
    asr = [int(row.get("asr_ms","0")) for row in voice]
    plot_series(xs, asr, "ASR Latency (ms)", "ms", os.path.join(base, "asr_latency.png"))

rag = read_csv(rag_csv)
if rag:
    xs = [row["ts"] for row in rag]
    hr = [float(row.get("hit_rate5","0")) for row in rag]
    mrr = [float(row.get("mrr5","0")) for row in rag]
    plot_series(xs, hr, "RAG Hit-Rate@5", "rate", os.path.join(base, "rag_hit_rate.png"))
    plot_series(xs, mrr, "RAG MRR@5", "mrr", os.path.join(base, "rag_mrr.png"))

# D-REAM Improvement Proposals
proposals_file = "/home/kloros/var/dream/proposals/improvement_proposals.jsonl"
proposals = read_jsonl(proposals_file)
if proposals:
    # Count by component
    by_component = defaultdict(int)
    by_priority = defaultdict(int)
    by_status = defaultdict(int)

    for p in proposals:
        by_component[p.get("component", "unknown")] += 1
        by_priority[p.get("priority", "unknown")] += 1
        by_status[p.get("status", "unknown")] += 1

    # Plot proposals by component
    if by_component:
        plot_bar(
            list(by_component.keys()),
            list(by_component.values()),
            "Improvement Proposals by Component",
            "Count",
            os.path.join(base, "proposals_by_component.png")
        )

    # Plot proposals by priority
    if by_priority:
        plot_pie(
            list(by_priority.keys()),
            list(by_priority.values()),
            "Proposals by Priority",
            os.path.join(base, "proposals_by_priority.png")
        )

    print(f"[dashboard] D-REAM proposals: {len(proposals)} total")

# D-REAM Candidate Queues
tool_queue_file = "/home/kloros/src/dream/artifacts/tool_synthesis_queue.jsonl"
tool_queue = read_jsonl(tool_queue_file)

# Count candidate files in phase_raw
phase_raw_dir = Path("/home/kloros/src/dream/phase_raw")
candidate_files = list(phase_raw_dir.glob("*.jsonl")) if phase_raw_dir.exists() else []
total_candidates = 0
for f in candidate_files:
    total_candidates += len(read_jsonl(str(f)))

if tool_queue or total_candidates > 0:
    # Count tool queue by status
    tool_by_status = defaultdict(int)
    tool_by_component = defaultdict(int)

    for t in tool_queue:
        tool_by_status[t.get("status", "unknown")] += 1
        tool_by_component[t.get("component", "unknown")] += 1

    # Create summary bar chart
    queue_data = {
        "Tool Synthesis Queue": len(tool_queue),
        "Proposal Candidates": total_candidates,
        "Total Pending": len(tool_queue) + total_candidates
    }

    plot_bar(
        list(queue_data.keys()),
        list(queue_data.values()),
        "D-REAM Candidate Queues",
        "Count",
        os.path.join(base, "dream_candidate_queues.png")
    )

    print(f"[dashboard] D-REAM queues: {len(tool_queue)} tool synthesis, {total_candidates} proposal candidates")

# D-REAM Evolution History
ledger_file = "/home/kloros/var/dream/ledger.jsonl"
ledger = read_jsonl(ledger_file)
if ledger:
    # Track success/failure over time
    timestamps = []
    pass_rate = []

    # Group by time windows (last N runs)
    window_size = 20
    for i in range(0, len(ledger), window_size):
        window = ledger[i:i+window_size]
        if window:
            passed = sum(1 for r in window if r.get("passed", False))
            rate = passed / len(window) if window else 0
            pass_rate.append(rate * 100)
            # Use first timestamp in window
            timestamps.append(f"Run {i}-{i+len(window)}")

    if pass_rate:
        plot_series(
            timestamps,
            pass_rate,
            "D-REAM Evolution Pass Rate",
            "Pass Rate (%)",
            os.path.join(base, "dream_pass_rate.png")
        )

    # Count by family
    by_family = defaultdict(int)
    for r in ledger:
        by_family[r.get("family", "unknown")] += 1

    if by_family:
        plot_bar(
            list(by_family.keys()),
            list(by_family.values()),
            "D-REAM Experiments by Family",
            "Count",
            os.path.join(base, "dream_by_family.png")
        )

    print(f"[dashboard] D-REAM history: {len(ledger)} runs")

print("[dashboard] charts written to", base)
