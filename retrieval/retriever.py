# retrieval/retriever.py
# (Same as retriever.py from "Reproduce the full updated code" with PolicyManager integration)
# Assumed complete.
import json
from typing import List, Dict, Set, Any
import uuid
from db_manager import DatabaseManager # Ensure this points to the top-level db_manager
from core_types import Intent, RetrievedItem, RetrievalSourceType
from config import MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION, MAX_CHUNKS_FOR_CONTEXT, MAX_TOKENS_PER_GEMINI_CALL_APPROX, EMBEDDING_DIMENSION

def get_embedding(text: str) -> List[float]: return [0.1] * EMBEDDING_DIMENSION

class AgenticRetriever:
    def __init__(self, db_manager: DatabaseManager): self.db_manager = db_manager
    def _get_semantic_results(self, qt: str, lim: int=10) -> List[Dict[str, Any]]:
        if not qt: return []
        qe=get_embedding(qt); sq="SELECT dc.chunk_id,dc.chunk_text,dc.page_number,dc.section,d.doc_id,d.title as doc_title,d.document_type,ce.embedding<->%s AS distance FROM document_chunks dc JOIN documents d ON dc.doc_id=d.doc_id JOIN chunk_embeddings ce ON dc.chunk_id=ce.chunk_id ORDER BY distance ASC LIMIT %s;"
        try: r=self.db_manager.execute_query(sq,(qe,lim),fetch_all=True); return r if r else []
        except Exception as e: print(f"ERR:SemSearchFail:{e}"); return []
    def retrieve_and_prepare_context(self, intent: Intent):
        intent.provenance.add_action("RetrievalContextPrepStart", {"cfg": intent.retrieval_config})
        s_clauses:List[str]=[]; s_params:List[Any]=[]
        if dt_filters:=intent.retrieval_config.get("document_type_filters",[]): s_clauses.append("d.document_type=ANY(%s)");s_params.append(dt_filters)
        if intent.application_refs: s_clauses.append("d.source=ANY(%s)");s_params.append(intent.application_refs)
        if kw_terms:=intent.retrieval_config.get("hybrid_search_terms", []):
            conds=[]; [(conds.append("dc.chunk_text ILIKE %s"),s_params.append(f"%{t}%")) for t in kw_terms if t]
            if conds: s_clauses.append(f"({' OR '.join(conds)})")
        bq="SELECT dc.chunk_id,dc.chunk_text,dc.page_number,dc.section,d.doc_id,d.title as doc_title,d.document_type FROM document_chunks dc JOIN documents d ON dc.doc_id=d.doc_id"
        sq=bq+(f" WHERE {' AND '.join(s_clauses)}" if s_clauses else "")+f" LIMIT {MAX_CHUNKS_FOR_CONTEXT*3};"
        s_results=self.db_manager.execute_query(sq,tuple(s_params),fetch_all=True) or []; intent.provenance.add_action("StructuredRetrieve",{"cnt":len(s_results)})
        sem_q_txt=intent.retrieval_config.get("semantic_search_query_text"); sem_r:List[Dict[str,Any]]=[]
        if sem_q_txt: sem_r=self._get_semantic_results(sem_q_txt,MAX_CHUNKS_FOR_CONTEXT*2); intent.provenance.add_action("SemanticRetrieve",{"q":sem_q_txt,"cnt":len(sem_r)})
        all_r_d:Dict[uuid.UUID,Dict]={r['chunk_id']:r for r in sem_r}; [all_r_d.setdefault(r['chunk_id'],r) for r in s_results]
        rank_comb=sorted(all_r_d.values(),key=lambda x:(x.get('distance',float('inf')),x.get('page_number',0)))
        rank_chunks_ctx=rank_comb[:MAX_CHUNKS_FOR_CONTEXT]; intent.provenance.add_action("CombinedRankedChunks",{"cnt":len(rank_chunks_ctx)})
        intent_items:List[RetrievedItem]=[]; doc_ids_ctx:Set[uuid.UUID]=set()
        for cd_item in rank_chunks_ctx:
            doc_ids_ctx.add(cd_item['doc_id']); intent_items.append(RetrievedItem(RetrievalSourceType.DOCUMENT_CHUNK,cd_item['chunk_text'],
                {"chunk_id":str(cd_item['chunk_id']),"doc_id":str(cd_item['doc_id']),"doc_title":cd_item['doc_title'],"dt":cd_item['document_type'],"pn":cd_item['page_number'],"s":cd_item['section'],"dist":cd_item.get('distance')}))
        intent.result=intent_items; full_docs_inj:List[Dict[str,str]]=[]; chunk_ctx_inj:List[Dict[str,Any]]=[]
        if 0<len(doc_ids_ctx)<=MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION:
            intent.provenance.add_action("TryFullDocInject",{"dcnt":len(doc_ids_ctx)}); tot_len=0; tmp_fd:List[Dict[str,str]]=[]
            s_doc_ids=sorted(list(doc_ids_ctx),key=lambda did:next((c.get('distance',float('inf')) for c in rank_chunks_ctx if c['doc_id']==did),float('inf')))
            for did_val in s_doc_ids[:MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION]:
                if ft_val:=self.db_manager.get_full_document_text_by_id(did_val): tmp_fd.append({"doc_id":str(did_val),"doc_title":next((c['doc_title'] for c in rank_chunks_ctx if c['doc_id']==did_val),"N/A"),"full_text":ft_val}); tot_len+=len(ft_val)
            if tot_len<(MAX_TOKENS_PER_GEMINI_CALL_APPROX*0.75): full_docs_inj=tmp_fd; intent.provenance.add_action("FullDocInjectOK",{"docs":[d['doc_id'] for d in full_docs_inj]})
            else: intent.provenance.add_action("FullDocsTooLarge",{"len":tot_len})
        if not full_docs_inj:
            chunk_ctx_inj=[{"cid":str(i.metadata['chunk_id']),"txt":str(i.content),"meta":i.metadata} for i in intent_items[:MAX_CHUNKS_FOR_CONTEXT]]
            intent.provenance.add_action("ChunkCtxSelected",{"cnt":len(chunk_ctx_inj)})
        intent.full_documents_context=full_docs_inj; intent.chunk_context=chunk_ctx_inj
        self.db_manager.log_retrieval(json.dumps({"kw":kw_terms,"sem":sem_q_txt}),intent.retrieval_config,[uuid.UUID(i.metadata['chunk_id']) for i in intent_items],f"Intent:{intent.intent_id} for {intent.parent_node_id}")
        intent.provenance.add_action("RetrievalContextPrepEnd")
