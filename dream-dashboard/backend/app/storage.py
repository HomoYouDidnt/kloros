import sqlite3, json, time
from contextlib import contextmanager
from datetime import datetime

@contextmanager
def db_conn(db_path: str, timeout: float = 5.0, isolation_level: str | None = None):
    conn = sqlite3.connect(db_path, timeout=timeout, isolation_level=isolation_level)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db(db_path: str):
    with db_conn(db_path) as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS improvements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL,
            score REAL NOT NULL,
            meta TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            type_key TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            claimed_by TEXT,
            started_at TEXT,
            finished_at TEXT,
            meta TEXT DEFAULT '{}'
        )
        """)

def add_improvement(db_path, title, description, domain="general", score=0.0, meta=None):
    meta = meta or {}
    with db_conn(db_path) as c:
        c.execute("""
        INSERT INTO improvements (created_at, title, description, domain, status, score, meta)
        VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """, (datetime.utcnow().isoformat(), title, description, domain, score, json.dumps(meta)))
        return c.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

def list_improvements(db_path, status=None):
    q = "SELECT * FROM improvements"
    args = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY created_at DESC"
    with db_conn(db_path) as c:
        return [dict(r) | {"meta": json.loads(r["meta"])} for r in c.execute(q, args).fetchall()]

def update_improvement_status(db_path, iid, status):
    with db_conn(db_path) as c:
        c.execute("UPDATE improvements SET status=? WHERE id=?", (status, iid))

def add_queue_item(db_path, type_key, params, note=None, meta=None):
    meta = meta or {}
    with db_conn(db_path) as c:
        # Add meta column if it doesn't exist (migration)
        try:
            c.execute("SELECT meta FROM queue LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE queue ADD COLUMN meta TEXT DEFAULT '{}'")
        
        c.execute("""
        INSERT INTO queue (created_at, type_key, params, status, note, claimed_by, started_at, finished_at, meta)
        VALUES (?, ?, ?, 'queued', ?, NULL, NULL, NULL, ?)
        """, (datetime.utcnow().isoformat(), type_key, json.dumps(params), note, json.dumps(meta)))
        return c.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

def list_queue(db_path, status=None):
    q = "SELECT * FROM queue"
    args = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY created_at DESC"
    with db_conn(db_path) as c:
        rows = c.execute(q, args).fetchall()
        result = []
        for r in rows:
            row_dict = dict(r)
            row_dict["params"] = json.loads(r["params"])
            # Handle missing meta column gracefully
            row_dict["meta"] = json.loads(r["meta"]) if "meta" in r.keys() else {}
            result.append(row_dict)
        return result

def update_queue_status(db_path, qid, status, note=None):
    now = datetime.utcnow().isoformat()
    with db_conn(db_path) as c:
        if status == "running":
            c.execute("UPDATE queue SET status=?, started_at=?, note=COALESCE(?, note) WHERE id=?", (status, now, note, qid))
        elif status in ("succeeded","failed","cancelled"):
            c.execute("UPDATE queue SET status=?, finished_at=?, note=COALESCE(?, note) WHERE id=?", (status, now, note, qid))
        else:
            c.execute("UPDATE queue SET status=?, note=COALESCE(?, note) WHERE id=?", (status, note, qid))

def claim_next_queue_item(db_path, worker_id: str):
    """Atomically claim the oldest queued item. Returns row dict or None."""
    with db_conn(db_path, isolation_level=None) as conn:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute("SELECT * FROM queue WHERE status='queued' ORDER BY created_at ASC LIMIT 1").fetchone()
        if not row:
            conn.commit()
            return None
        qid = row["id"]
        now = datetime.utcnow().isoformat()
        cur.execute("UPDATE queue SET status='running', claimed_by=?, started_at=? WHERE id=?", (worker_id, now, qid))
        conn.commit()
        row_dict = dict(row)
        row_dict["params"] = json.loads(row["params"])
        row_dict["meta"] = json.loads(row["meta"]) if "meta" in row.keys() else {}
        return row_dict

def claim_specific_queue_item(db_path, qid: int, worker_id: str):
    """Atomically claim a specific queued item. Returns row dict or None."""
    with db_conn(db_path, isolation_level=None) as conn:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute("SELECT * FROM queue WHERE id=? AND status='queued'", (qid,)).fetchone()
        if not row:
            conn.commit()
            return None
        now = datetime.utcnow().isoformat()
        cur.execute("UPDATE queue SET status='running', claimed_by=?, started_at=? WHERE id=?", (worker_id, now, qid))
        conn.commit()
        row_dict = dict(row)
        row_dict["params"] = json.loads(row["params"])
        row_dict["meta"] = json.loads(row["meta"]) if "meta" in row.keys() else {}
        return row_dict
