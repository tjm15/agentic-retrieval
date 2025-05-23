# knowledge_base/policy_manager.py
import json
import os
from typing import List, Dict, Optional, Any
from uuid import UUID

from db_manager import DatabaseManager
from config import POLICY_KB_DIR

class PolicyManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        print(f"INFO: PolicyManager initialized to query policies from the database.")
        self._ensure_default_policies_ingested_if_needed()

    def _ensure_default_policies_ingested_if_needed(self):
        query = "SELECT doc_id FROM documents WHERE source = %s AND document_type = %s LIMIT 1;"
        nppf_check = self.db_manager.execute_query(query, ("NPPF", "PolicyDocument_NPPF"), fetch_one=True)
        if not nppf_check:
            print("WARN: Default NPPF policies not found in DB. Attempting dummy ingestion from policy_kb/nppf_sample.json.")
            self._ingest_sample_policies_from_json()

    def _ingest_sample_policies_from_json(self):
        sample_path = os.path.join(POLICY_KB_DIR, "nppf_sample.json")
        if not os.path.exists(sample_path):
            print(f"INFO: Policy KB file {sample_path} not found. Skipping sample policy ingestion.")
            return
        try:
            with open(sample_path, 'r') as f:
                policy_list = json.load(f)
            doc_title = "Policy Document: NPPF"
            doc_type = "PolicyDocument_NPPF"
            doc_source = "NPPF"
            existing_doc = self.db_manager.execute_query(
                "SELECT doc_id FROM documents WHERE title = %s AND source = %s LIMIT 1;",
                (doc_title, doc_source), fetch_one=True
            )
            if existing_doc:
                print(f"Policy document '{doc_title}' already ingested. Skipping.")
                return
            doc_id = self.db_manager.add_document(
                fn="nppf_sample.json",
                t=doc_title,
                dt=doc_type,
                s=doc_source,
                pc=len(policy_list),
                tags=["policy", "nppf"]
            )
            for i, policy_data in enumerate(policy_list):
                policy_id_tag = policy_data.get("id", f"NPPF_Policy_{i+1}")
                chunk_text = f"Policy ID: {policy_id_tag}\nTitle: {policy_data.get('title', 'N/A')}\nSummary: {policy_data.get('text_summary', '')}\nFull Text (if available): {policy_data.get('full_text', policy_data.get('text_summary', ''))}"
                self.db_manager.add_document_chunk(
                    did=doc_id,
                    pn=i+1,
                    ct=chunk_text,
                    s=policy_id_tag,
                    tags=["policy_clause", policy_id_tag] + policy_data.get("keywords", [])
                )
            print(f"Successfully ingested {len(policy_list)} policy clauses from nppf_sample.json under doc_id {doc_id}.")
        except Exception as e:
            print(f"ERROR ingesting sample policies: {e}")

    def search_policies(self,
                        themes: Optional[List[str]] = None,
                        keywords: Optional[List[str]] = None,
                        semantic_query: Optional[str] = None,
                        policy_ids: Optional[List[str]] = None,
                        document_sources: Optional[List[str]] = None,
                        limit: int = 5) -> List[Dict[str, Any]]:
        sql_clauses: List[str] = []
        sql_params: List[Any] = []
        policy_doc_type_patterns = ["PolicyDocument_%"]
        if document_sources:
            policy_doc_type_patterns = [f"PolicyDocument_{src.split('_')[0]}" for src in document_sources] + [f"PolicyDocument_{src}" for src in document_sources]
        sql_clauses.append( "(" + " OR ".join(["d.document_type ILIKE %s"] * len(policy_doc_type_patterns)) + ")")
        for pattern in policy_doc_type_patterns: sql_params.append(pattern)
        if document_sources:
            sql_clauses.append("d.source = ANY(%s)")
            sql_params.append(document_sources)
        if policy_ids:
            policy_id_conditions = []
            for p_id in policy_ids:
                policy_id_conditions.append("(dc.section = %s OR %s = ANY(dc.tags))")
                sql_params.extend([p_id, p_id])
            if policy_id_conditions:
                sql_clauses.append(f"({' OR '.join(policy_id_conditions)})")
        all_keywords = list(set((themes or []) + (keywords or [])))
        if all_keywords:
            keyword_text_conditions = []
            for term in all_keywords:
                if term:
                    keyword_text_conditions.append("(dc.chunk_text ILIKE %s OR %s = ANY(dc.tags))")
                    sql_params.extend([f"%{term}%", term])
            if keyword_text_conditions:
                sql_clauses.append(f"({' OR '.join(keyword_text_conditions)})")
        base_query = """
        SELECT dc.chunk_id, dc.chunk_text, dc.page_number, dc.section as policy_id_tag, 
               d.doc_id, d.title as policy_document_title, d.document_type as policy_document_type, d.source as policy_document_source
        FROM document_chunks dc
        JOIN documents d ON dc.doc_id = d.doc_id
        """
        final_query = base_query
        if sql_clauses:
            final_query += " WHERE " + " AND ".join(sql_clauses)
        final_query += f" LIMIT %s;"
        sql_params.append(limit)
        try:
            results = self.db_manager.execute_query(final_query, tuple(sql_params), fetch_all=True)
            formatted_results = []
            if results:
                for row in results:
                    formatted_results.append({
                        "policy_clause_id": str(row["chunk_id"]),
                        "policy_id_tag": row["policy_id_tag"],
                        "policy_document_title": row["policy_document_title"],
                        "policy_document_source": row["policy_document_source"],
                        "text_snippet": row["chunk_text"]
                    })
            return formatted_results if formatted_results else []
        except Exception as e:
            print(f"ERROR during policy search: {e}")
            return []

    def get_policy_full_text_by_id_tag(self, policy_id_tag: str) -> Optional[str]:
        query = "SELECT chunk_text FROM document_chunks WHERE section = %s AND doc_id IN (SELECT doc_id FROM documents WHERE document_type ILIKE 'PolicyDocument_%') LIMIT 1;"
        result = self.db_manager.execute_query(query, (policy_id_tag,), fetch_one=True)
        return result['chunk_text'] if result else None
