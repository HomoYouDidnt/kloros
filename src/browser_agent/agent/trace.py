import os, json, time, uuid
class TraceLogger:
    def __init__(self, base_dir):
        self.base_dir=os.path.expanduser(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self.run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        self.run_dir=os.path.join(self.base_dir,self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        self.jsonl=os.path.join(self.run_dir,'trace.jsonl')
        self.vars={}
    def log(self,ev):
        import json, time
        with open(self.jsonl,'a',encoding='utf-8') as f:
            f.write(json.dumps({'ts':time.time(),**ev})+'\n')
    async def save_screenshot(self, page, rel):
        path = os.path.join(self.run_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await page.screenshot(path=path)
        self.log({'type': 'screenshot', 'path': rel})
        return path
    def save_vars(self,rel):
        p=os.path.join(self.run_dir, rel)
        with open(p,'w',encoding='utf-8') as f: json.dump(self.vars,f,ensure_ascii=False,indent=2)
        self.log({'type':'vars_saved','path':rel}); return p
