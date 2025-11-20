class PetriPolicy:
    def __init__(self):
        import os
        self.allow_domains=['example.com']
        self.max_actions=40
        self.action_timeout_s=8.0
        self.total_timeout_s=120.0
        self.screenshot_every_step=True
        self.trace_dir=os.path.expanduser('~/.kloros/traces/browser')
    def ensure_dirs(self):
        import os
        os.makedirs(self.trace_dir, exist_ok=True)
    def check_domain(self, url:str)->bool:
        from urllib.parse import urlparse
        host=(urlparse(url).hostname or '')
        if not host: return False
        return any(host.endswith(ad) for ad in self.allow_domains)
