class Collector:
    def __init__(self):
        self.episodes = []
        self.generations = []
        self.macro_traces = []
        self.playbook_deltas = []
        self.petri_reports = []

    def add_episode(self, ep): self.episodes.append(ep)
    def add_generation(self, gen): self.generations.append(gen)
    def add_macro_trace(self, mt): self.macro_traces.append(mt)
    def add_playbook_delta(self, delta): self.playbook_deltas.append(delta)
    def add_petri_report(self, rep): self.petri_reports.append(rep)

    def snapshot(self):
        return {
            "episodes": self.episodes,
            "generations": self.generations,
            "macro_traces": self.macro_traces,
            "playbook_deltas": self.playbook_deltas,
            "petri_reports": self.petri_reports,
        }
