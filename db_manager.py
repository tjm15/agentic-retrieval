# db_manager.py
# (Same as the db_manager.py from the previous "Reproduce the full updated code" response)
# Assumed complete.
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import List, Dict, Any, Optional
import uuid
from config import DB_CONFIG, EMBEDDING_DIMENSION

def get_embedding(text: str) -> List[float]:
    return [0.1] * EMBEDDING_DIMENSION

class DatabaseManager:
    def __init__(self, db_config=DB_CONFIG):
        self.db_config = db_config; self.conn = None; self._connect()
    def _connect(self):
        try: self.conn = psycopg2.connect(**self.db_config); self.conn.autocommit = True
        except psycopg2.Error as e: print(f"ERROR: DB connection failed: {e}"); raise
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        if not self.conn or self.conn.closed: self._connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch_one: return cur.fetchone()
                if fetch_all: return cur.fetchall()
                return None
        except psycopg2.Error as e: print(f"ERROR: DB Query failed: {e}\nQuery: {query[:500]}...\nParams: {params}"); raise
    def add_document(self, fn: str, t: str, dt: str, s: str, pc: int, tags: List[str]=None) -> uuid.UUID:
        did=uuid.uuid4(); q="INSERT INTO documents (doc_id,filename,title,document_type,source,page_count,upload_date,tags) VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s) RETURNING doc_id;"; r=self.execute_query(q,(did,fn,t,dt,s,pc,tags or []),True); return r['doc_id'] if r else did
    def add_document_chunk(self, did: uuid.UUID, pn: int, ct: str, s: Optional[str]=None, tags: List[str]=None) -> uuid.UUID:
        cid=uuid.uuid4(); q="INSERT INTO document_chunks (chunk_id,doc_id,page_number,section,chunk_text,tags) VALUES (%s,%s,%s,%s,%s,%s) RETURNING chunk_id;"; r=self.execute_query(q,(cid,did,pn,s,ct,tags or []),True); cid_to_ret=r['chunk_id'] if r else cid
        emb=get_embedding(ct); eq="INSERT INTO chunk_embeddings (chunk_id,embedding) VALUES (%s,%s);"; self.execute_query(eq,(cid_to_ret,emb)); return cid_to_ret
    def get_full_document_text_by_id(self, did: uuid.UUID) -> Optional[str]:
        q="SELECT chunk_text FROM document_chunks WHERE doc_id = %s ORDER BY page_number, created_at;"; r=self.execute_query(q,(did,),True,True); return "\n\n".join([row['chunk_text'] for row in r]) if r else None
    def log_retrieval(self, qt: str, f: Optional[Dict], mcids: List[uuid.UUID], ac: str):
        lid=uuid.uuid4(); dq="INSERT INTO retrieval_logs (log_id,query,filters,matched_chunk_ids,agent_context) VALUES (%s,%s,%s,%s,%s);"; self.execute_query(dq,(lid,qt,Json(f or {}),mcids,ac))
    def close(self):
        if self.conn and not self.conn.closed: self.conn.close()
