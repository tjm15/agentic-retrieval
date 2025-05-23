# db_manager.py
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import List, Dict, Any, Optional
import uuid
from config import DB_CONFIG, EMBEDDING_DIMENSION

def get_embedding(text: str) -> List[float]:
    # In a real system, this would call an actual embedding model
    # For now, using a placeholder that returns a fixed-size vector.
    # print(f"INFO: (DB_Manager) Generating dummy embedding for: '{text[:30]}...'") # Can be verbose
    return [0.1] * EMBEDDING_DIMENSION

class DatabaseManager:
    def __init__(self, db_config=DB_CONFIG):
        self.db_config = db_config
        self.conn = None
        self._connect()
        # In a real system with pgvector, you might call register_vector(self.conn) here
        # from pgvector.psycopg2 import register_vector

    def _connect(self):
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.autocommit = True # Simplifies, otherwise manage transactions explicitly
            # print("INFO: Database connection established.") # Can be verbose
        except psycopg2.Error as e:
            print(f"ERROR: Database connection failed: {e}")
            raise

    def execute_query(self, query: str, params: Optional[tuple] = None, fetch_one: bool = False, fetch_all: bool = False) -> Any:
        if not self.conn or self.conn.closed:
            # print("WARN: DB connection was closed. Reconnecting.") # For debugging
            self._connect()
        # Ensure connection is now established before proceeding
        if not self.conn:
             raise RuntimeError("Database connection could not be re-established.")
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch_one:
                    return cur.fetchone()
                if fetch_all:
                    return cur.fetchall()
                return None # For INSERT/UPDATE without RETURNING, or if no fetch type specified
        except psycopg2.Error as e:
            print(f"ERROR: DB Query failed: {type(e).__name__} - {e}")
            print(f"Query: {query[:500]}...")
            print(f"Params: {params}")
            # Depending on the error, you might want to raise it, or return a specific error indicator
            raise # Re-raise for now to make issues visible

    def add_document(self, filename: str, title: Optional[str], document_type: Optional[str], source: Optional[str], page_count: Optional[int], tags: Optional[List[str]] = None) -> uuid.UUID:
        doc_id_val = uuid.uuid4()
        query = """
        INSERT INTO documents (doc_id, filename, title, document_type, source, page_count, upload_date, tags)
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s) RETURNING doc_id;
        """
        result = self.execute_query(query, (doc_id_val, filename, title, document_type, source, page_count, tags or []), fetch_one=True)
        return result['doc_id'] if result else doc_id_val # Fallback if RETURNING not supported/fails

    def add_document_chunk(self, doc_id: uuid.UUID, page_number: Optional[int], chunk_text: str, section: Optional[str] = None, tags: Optional[List[str]] = None) -> uuid.UUID:
        chunk_id_val = uuid.uuid4()
        query = """
        INSERT INTO document_chunks (chunk_id, doc_id, page_number, section, chunk_text, tags)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING chunk_id;
        """
        result = self.execute_query(query, (chunk_id_val, doc_id, page_number, section, chunk_text, tags or []), fetch_one=True)
        chunk_id_to_return = result['chunk_id'] if result else chunk_id_val
        
        embedding_val = get_embedding(chunk_text) # Uses EMBEDDING_DIMENSION from config
        emb_query = "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (%s, %s);"
        self.execute_query(emb_query, (chunk_id_to_return, embedding_val)) # Ensure embedding_val is a list
        return chunk_id_to_return

    def get_full_document_text_by_id(self, doc_id: uuid.UUID) -> Optional[str]:
        query = "SELECT chunk_text FROM document_chunks WHERE doc_id = %s ORDER BY page_number, created_at;" # created_at for tie-breaking
        results = self.execute_query(query, (doc_id,), fetch_all=True)
        return "\n\n".join([row['chunk_text'] for row in results]) if results else None

    def log_retrieval(self, query_text: str, filters: Optional[Dict], matched_chunk_ids: List[uuid.UUID], agent_context: str):
        log_id_val = uuid.uuid4()
        # Ensure matched_chunk_ids is a list of UUIDs, not strings, if your DB expects UUID array directly
        # psycopg2 handles Python UUID objects correctly for UUID SQL type.
        db_query = """
        INSERT INTO retrieval_logs (log_id, query, filters, matched_chunk_ids, agent_context)
        VALUES (%s, %s, %s, %s, %s);
        """
        self.execute_query(db_query, (log_id_val, query_text, Json(filters or {}), matched_chunk_ids, agent_context))

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()
            # print("INFO: Database connection closed.") # Can be verbose
