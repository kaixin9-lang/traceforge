import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime,timezone
from langgraph.store.base import BaseStore, Item, GetOp, PutOp, SearchOp, ListNamespacesOp
from .config import settings

def uid():
    return uuid.uuid4().hex

class Database:
    def __init__(self, path=None):
        self.path = str(path or settings.data_dir / 'traceforge.db')
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS objects (kind TEXT, id TEXT, value TEXT, updated REAL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, event TEXT, data TEXT, created REAL);
            CREATE INDEX IF NOT EXISTS events_run ON events(run_id,seq);
            CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, run_id TEXT, hash TEXT, status TEXT, value TEXT, updated REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS action_once ON actions(run_id,hash);
            CREATE TABLE IF NOT EXISTS memories (namespace TEXT, key TEXT, value TEXT, created REAL, updated REAL, PRIMARY KEY(namespace,key));
            ''')

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def put(self, kind, id, value):
        with self.lock, self.connect() as c:
            c.execute('INSERT OR REPLACE INTO objects VALUES (?,?,?,?)', (kind,id,json.dumps(value,ensure_ascii=False),time.time()))
        return value

    def get(self, kind, id):
        with self.connect() as c:
            row = c.execute('SELECT value FROM objects WHERE kind=? AND id=?', (kind,id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT value FROM objects WHERE kind=? ORDER BY updated DESC', (kind,))]

    def delete(self, kind, id):
        with self.lock, self.connect() as c:
            c.execute('DELETE FROM objects WHERE kind=? AND id=?',(kind,id))

    def event(self, run_id, event, data):
        with self.lock, self.connect() as c:
            cur = c.execute('INSERT INTO events(run_id,event,data,created) VALUES(?,?,?,?)', (run_id,event,json.dumps(data,ensure_ascii=False),time.time()))
            return cur.lastrowid

    def events(self, run_id, after=0):
        with self.connect() as c:
            return [{'seq': r['seq'],'event':r['event'],'data':json.loads(r['data'])} for r in c.execute('SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 500',(run_id,after))]

    def claim_action(self, run_id, payload_hash, value):
        with self.lock, self.connect() as c:
            id = uid()
            try:
                c.execute('INSERT INTO actions VALUES(?,?,?,?,?,?)',(id,run_id,payload_hash,'executing',json.dumps(value,ensure_ascii=False),time.time()))
            except sqlite3.IntegrityError:
                row=c.execute('SELECT * FROM actions WHERE run_id=? AND hash=?',(run_id,payload_hash)).fetchone()
                return row['id'], False
            return id, True

    def action_finish(self,id,status,value):
        with self.connect() as c:
            c.execute('UPDATE actions SET status=?,value=?,updated=? WHERE id=?',(status,json.dumps(value,ensure_ascii=False),time.time(),id))

    def actions(self):
        with self.connect() as c:
            return [dict(r)|{'value':json.loads(r['value'])} for r in c.execute('SELECT * FROM actions ORDER BY updated DESC')]

db=Database()

class SQLiteStore(BaseStore):
    """BaseStore JSON persistence; semantic case search belongs to Milvus."""
    def __init__(self,database=db):
        self.db=database

    def batch(self, ops):
        result=[]
        for op in ops:
            namespace=tuple(getattr(op,'namespace',()))
            ns_json=json.dumps(namespace)
            if isinstance(op,GetOp):
                with self.db.connect() as c:row=c.execute('SELECT * FROM memories WHERE namespace=? AND key=?',(ns_json,op.key)).fetchone()
                result.append(self._item(row) if row else None)
            elif isinstance(op,PutOp):
                with self.db.lock,self.db.connect() as c:
                    if op.value is None:c.execute('DELETE FROM memories WHERE namespace=? AND key=?',(ns_json,op.key))
                    else:
                        now=time.time();c.execute('INSERT INTO memories VALUES (?,?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value,updated=excluded.updated',(ns_json,op.key,json.dumps(op.value,ensure_ascii=False),now,now))
                result.append(None)
            elif isinstance(op,SearchOp):
                items=[]
                with self.db.connect() as c:
                    for r in c.execute('SELECT * FROM memories ORDER BY updated DESC'):
                        ns=tuple(json.loads(r['namespace'])); value=json.loads(r['value'])
                        if ns[:len(op.namespace_prefix)] == tuple(op.namespace_prefix) and all(value.get(k)==v for k,v in (op.filter or {}).items()):
                            items.append(self._item(r))
                result.append(items[op.offset:op.offset+op.limit])
            elif isinstance(op,ListNamespacesOp):
                with self.db.connect() as c:
                    namespaces=[tuple(json.loads(r[0])) for r in c.execute('SELECT DISTINCT namespace FROM memories')]
                for condition in op.match_conditions or []:
                    pattern=condition.path
                    namespaces=[ns for ns in namespaces if len(ns)>=len(pattern) and all(p=='*' or p==n for p,n in zip(pattern,ns if condition.match_type=='prefix' else ns[-len(pattern):]))]
                if op.max_depth:namespaces=list(dict.fromkeys(ns[:op.max_depth] for ns in namespaces))
                result.append(namespaces[op.offset:op.offset+op.limit])
        return result

    @staticmethod
    def _item(row):
        return Item(value=json.loads(row['value']),key=row['key'],namespace=tuple(json.loads(row['namespace'])),created_at=datetime.fromtimestamp(row['created'],timezone.utc),updated_at=datetime.fromtimestamp(row['updated'],timezone.utc))

    async def abatch(self,ops):
        import asyncio
        return await asyncio.to_thread(self.batch,ops)
