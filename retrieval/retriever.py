# retrieval/retriever.py
# (Same as retriever.py from "Reproduce the full updated code" with PolicyManager integration)
# Assumed complete.
import json
from typing import List, Dict, Set, Any
import uuid
from db_manager import DatabaseManager # Relative import for modular structure
from core_types import Intent, RetrievedItem, RetrievalSourceType
from config import MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION, MAX_CHUNKS_FOR_CONTEXT, MAX_TOKENS_PER_GEMINI_CALL_APPROX, EMBEDDING_DIMENSION

def get_embedding(text: str) -> List[float]: # Placeholder
    # In a real system, this would be a proper embedding model call
    # print(f"INFO: (Retriever) Generating dummy embedding for: '{text[:30]}...'")
    return [0.1] * EMBEDDING_DIMENSION

class AgenticRetriever:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def _get_semantic_results(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not query_text: return []
        query_embedding = get_embedding(query_text)
        # Note: Ensure your embeddings are normalized if using vector_cosine_ops for true cosine similarity.
        # For L2 distance (often used), vector_l2_ops is correct.
        # For dot product (inner product), vector_ip_ops (often for non-normalized or specific embeddings like OpenAI's).
        semantic_query = """
        SELECT dc.chunk_id, dc.chunk_text, dc.page_number, dc.section, 
               d.doc_id, d.title as doc_title, d.document_type,
               ce.embedding <-> %s AS distance 
        FROM document_chunks dc
        JOIN documents d ON dc.doc_id = d.doc_id
        JOIN chunk_embeddings ce ON dc.chunk_id = ce.chunk_id
        ORDER BY distance ASC
        LIMIT %s; 
        """
        try:
            # pgvector expects list for embedding, not tuple
            results = self.db_manager.execute_query(semantic_query, (list(query_embedding), limit), fetch_all=True)
            return results if results else []
        except Exception as e:
            print(f"ERROR: Semantic search failed: {type(e).__name__} - {e}")
            return []

    def retrieve_and_prepare_context(self, intent: Intent):
        intent.provenance.add_action("RetrievalContextPrepStart", {"cfg": intent.retrieval_config})
        sql_clauses: List[str] = []
        sql_params: List[Any] = []

        if doc_type_filters := intent.retrieval_config.get("document_type_filters"):
            if isinstance(doc_type_filters, list) and doc_type_filters:
                sql_clauses.append("d.document_type = ANY(%s)")
                sql_params.append(doc_type_filters)
        
        if intent.application_refs:
            # Assuming application_refs are stored in d.source. If it's a tag or filename, adjust query.
            sql_clauses.append("d.source = ANY(%s)") 
            sql_params.append(intent.application_refs)
        
        if keyword_terms := intent.retrieval_config.get("hybrid_search_terms"):
            if isinstance(keyword_terms, list) and keyword_terms:
                conditions = []
                for term in keyword_terms:
                    if term and isinstance(term, str): # Ensure term is valid
                        conditions.append("dc.chunk_text ILIKE %s")
                        sql_params.append(f"%{term}%")
                if conditions:
                    sql_clauses.append(f"({' OR '.join(conditions)})")

        base_q = "SELECT dc.chunk_id, dc.chunk_text, dc.page_number, dc.section, d.doc_id, d.title as doc_title, d.document_type FROM document_chunks dc JOIN documents d ON dc.doc_id = d.doc_id"
        structured_q = base_q + (f" WHERE {' AND '.join(sql_clauses)}" if sql_clauses else "") + f" LIMIT {MAX_CHUNKS_FOR_CONTEXT * 3};"
        
        structured_results = self.db_manager.execute_query(structured_q, tuple(sql_params), fetch_all=True) or []
        intent.provenance.add_action("StructuredRetrieve", {"count": len(structured_results)})

        semantic_q_text = intent.retrieval_config.get("semantic_search_query_text")
        semantic_results: List[Dict[str,Any]] = self._get_semantic_results(semantic_q_text, MAX_CHUNKS_FOR_CONTEXT*2) if semantic_q_text else []
        if semantic_q_text: intent.provenance.add_action("SemanticRetrieve",{"query": semantic_q_text,"count":len(semantic_results)})
        
        all_r_dict: Dict[uuid.UUID, Dict] = {r['chunk_id']: r for r in semantic_results} # Semantic first to prioritize its distance score
        for r_struct in structured_results: all_r_dict.setdefault(r_struct['chunk_id'], r_struct) # Add structured if not already present
        
        ranked_combined = sorted(all_r_dict.values(), key=lambda x: (x.get('distance', float('inf')), x.get('page_number', 0), str(x.get('chunk_id','')))) # Add chunk_id for stable sort
        
        ranked_chunks_for_ctx = ranked_combined[:MAX_CHUNKS_FOR_CONTEXT]
        intent.provenance.add_action("CombinedRankedChunks",{"count":len(ranked_chunks_for_ctx)})

        intent_items:List[RetrievedItem] = []; doc_ids_in_ctx:Set[uuid.UUID] = set()
        for cd_item in ranked_chunks_for_ctx:
            doc_ids_in_ctx.add(cd_item['doc_id'])
            intent_items.append(RetrievedItem(RetrievalSourceType.DOCUMENT_CHUNK,cd_item['chunk_text'],
                {"chunk_id":str(cd_item['chunk_id']),"doc_id":str(cd_item['doc_id']),"doc_title":cd_item['doc_title'], 
                 "document_type":cd_item['document_type'],"page_number":cd_item['page_number'], 
                 "section":cd_item['section'],"distance":cd_item.get('distance')}))
        intent.result = intent_items

        full_docs_inj:List[Dict[str,str]] = []; chunk_ctx_inj:List[Dict[str,Any]] = []
        tot_len=0 # Initialize tot_len
        if 0 < len(doc_ids_in_ctx) <= MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION:
            intent.provenance.add_action("TryFullDocInject",{"doc_count":len(doc_ids_in_ctx)}); tmp_fd:List[Dict[str,str]] = []
            sorted_doc_ids = sorted(list(doc_ids_in_ctx), key=lambda did_val:next((c.get('distance',float('inf')) for c in ranked_chunks_for_ctx if c['doc_id']==did_val),float('inf')))
            for doc_id_to_load in sorted_doc_ids[:MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION]:
                if full_txt_val := self.db_manager.get_full_document_text_by_id(doc_id_to_load): 
                    doc_title_val = next((c['doc_title'] for c in ranked_chunks_for_ctx if c['doc_id'] == doc_id_to_load),"N/A Document Title")
                    tmp_fd.append({"doc_id":str(doc_id_to_load),"doc_title": doc_title_val,"full_text":full_txt_val}); tot_len+=len(full_txt_val)
            
            # A very rough approximation of tokens for Gemini. Real token counting is more complex.
            # Assume 1 token ~ 4 chars.
            approx_tokens = tot_len / 4 
            if approx_tokens < (MAX_TOKENS_PER_GEMINI_CALL_APPROX * 0.75): # Leave 25% for prompt, output
                full_docs_inj=tmp_fd; intent.provenance.add_action("FullDocInjectOK",{"docs":[d['doc_id'] for d in full_docs_inj], "approx_tokens": approx_tokens})
            else: intent.provenance.add_action("FullDocsTooLarge",{"approx_tokens": approx_tokens, "limit": MAX_TOKENS_PER_GEMINI_CALL_APPROX * 0.75})
        
        if not full_docs_inj:
            chunk_ctx_inj=[{"chunk_id":str(item.metadata['chunk_id']),"chunk_text":str(item.content),"metadata":item.metadata} for item in intent_items[:MAX_CHUNKS_FOR_CONTEXT]]
            intent.provenance.add_action("ChunkCtxSelected",{"count":len(chunk_ctx_inj)})
        
        intent.full_documents_context=full_docs_inj; intent.chunk_context=chunk_ctx_inj
        
        log_query_text = json.dumps({"keywords": intent.retrieval_config.get("hybrid_search_terms", []), "semantic_query": semantic_q_text})
        log_matched_ids = [uuid.UUID(item.metadata['chunk_id']) for item in intent_items] # Convert back to UUID for DB log
        self.db_manager.log_retrieval(log_query_text, intent.retrieval_config, log_matched_ids, f"Intent:{intent.intent_id} for {intent.parent_node_id}")
        intent.provenance.add_action("RetrievalContextPrepEnd")
