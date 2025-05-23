# knowledge_base/policy_manager.py
import json
import os
from typing import List, Dict, Optional, Any
from uuid import UUID

from db_manager import DatabaseManager, get_embedding as db_get_embedding
from config import POLICY_KB_DIR, EMBEDDING_DIMENSION


class PolicyManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        print(f"INFO: PolicyManager initialized (uses database for policy storage).")
        self._ensure_default_policies_ingested_if_needed()

    def _ensure_default_policies_ingested_if_needed(self):
        # Check for a known policy document source to see if ingestion might have happened.
        # This is a simple check; a more robust system might use a dedicated metadata table.
        query = "SELECT doc_id FROM documents WHERE source = %s AND document_type = %s LIMIT 1;"
        # Using a specific source name expected from sample JSON, e.g., "NPPF_SAMPLE" if nppf_sample.json exists
        # Or make it more generic if multiple default files are expected.
        # For this example, let's assume "NPPF_SAMPLE" is a key default policy set.
        nppf_check = self.db_manager.execute_query(query, ("NPPF_SAMPLE", "PolicyDocument_NPPF"), fetch_one=True)
        if not nppf_check:
            print("WARN: Default NPPF policies not found in DB via PolicyManager check. Attempting dummy ingestion from all JSONs in POLICY_KB_DIR.")
            self._ingest_sample_policies_from_json() 
        else:
            print("INFO: A policy document (e.g., NPPF_SAMPLE) seems to exist in DB. Assuming policies are ingested.")


    def _ingest_sample_policies_from_json(self):
        if not os.path.exists(POLICY_KB_DIR): 
            print(f"INFO: Policy KB dir {POLICY_KB_DIR} not found. Skipping ingestion.")
            return
        
        for filename in os.listdir(POLICY_KB_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(POLICY_KB_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        policy_list = json.load(f)
                        # Determine document source name from filename (e.g., "NPPF_SAMPLE" from "nppf_sample.json")
                        doc_source_name = filename.replace(".json", "").upper() 
                        doc_title = f"Policy Document: {doc_source_name}"
                        # Determine document type (e.g., "PolicyDocument_NPPF" from "NPPF_SAMPLE")
                        doc_type_prefix = doc_source_name.split('_')[0] if '_' in doc_source_name else doc_source_name
                        doc_type = f"PolicyDocument_{doc_type_prefix}"
                        
                        # Check if this "document collection" already exists to avoid re-ingestion
                        existing_doc_query = "SELECT doc_id FROM documents WHERE filename = %s AND source = %s AND document_type = %s LIMIT 1;"
                        existing_doc = self.db_manager.execute_query(existing_doc_query, (filename, doc_source_name, doc_type), fetch_one=True)
                        
                        if existing_doc:
                            print(f"Policy doc collection for '{filename}' (source: {doc_source_name}) already in DB. Skipping ingestion for this file.")
                            continue

                        doc_id = self.db_manager.add_document(
                            filename=filename, 
                            title=doc_title, 
                            document_type=doc_type, 
                            source=doc_source_name, 
                            page_count=len(policy_list), 
                            tags=["policy_document", doc_type_prefix.lower()]
                        )
                        print(f"INFO: Ingesting policies from {filename} as doc_id {doc_id} (Source: {doc_source_name}, Type: {doc_type})")
                        for i, pol_data in enumerate(policy_list):
                            pol_id_tag = pol_data.get("id", f"{doc_source_name}_Item_{i+1}")
                            # Construct chunk text carefully
                            chunk_text_parts = []
                            if pol_data.get("title"): chunk_text_parts.append(f"Policy Title: {pol_data['title']}")
                            if pol_data.get("id"): chunk_text_parts.append(f"Policy ID: {pol_data['id']}")
                            if pol_data.get("text_summary"): chunk_text_parts.append(f"Summary: {pol_data['text_summary']}")
                            full_text = pol_data.get('full_text', pol_data.get('text_summary')) # Fallback full_text to summary
                            if full_text: chunk_text_parts.append(f"Full Text: {full_text}")
                            
                            chunk_txt_final = "\n\n".join(chunk_text_parts)
                            if not chunk_txt_final: chunk_txt_final = "No text content provided for this policy item."

                            chunk_tags = ["policy_clause", pol_id_tag] + pol_data.get("keywords", [])
                            if pol_data.get("source_document"): chunk_tags.append(f"src_doc:{pol_data['source_document'].replace(' ', '_')}")
                            if pol_data.get("chapter_or_section_ref"): chunk_tags.append(f"ref:{pol_data['chapter_or_section_ref'].replace(' ', '_')}")

                            self.db_manager.add_document_chunk(
                                doc_id=doc_id, 
                                page_number=i + 1, # Using index as a pseudo page number
                                chunk_text=chunk_txt_final, 
                                section=pol_id_tag, # Storing policy ID in section for easier lookup
                                tags=list(set(chunk_tags)) # Ensure unique tags
                            )
                        print(f"Successfully ingested {len(policy_list)} policy items from {filename} under doc_id {doc_id}.")
                except Exception as e: 
                    print(f"ERROR ingesting policies from {filepath}: {type(e).__name__} - {e}")

    def search_policies(self, themes: Optional[List[str]]=None, keywords: Optional[List[str]]=None, 
                        semantic_query: Optional[str]=None, policy_ids: Optional[List[str]]=None, 
                        document_sources: Optional[List[str]]=None, limit: int=5) -> List[Dict[str, Any]]:
        sql_clauses: List[str] = []
        sql_params: List[Any] = []

        # Filter by document_type (must be a policy document)
        # Policy documents are identified by type "PolicyDocument_%"
        sql_clauses.append("d.document_type ILIKE %s")
        sql_params.append("PolicyDocument_%")

        if document_sources:
            # document_sources might be like "NPPF", "LocalPlan", etc.
            # These correspond to d.source like "NPPF_SAMPLE", "LOCAL_PLAN_CORE_STRATEGY"
            source_conditions = []
            for src_keyword in document_sources:
                source_conditions.append("d.source ILIKE %s")
                sql_params.append(f"%{src_keyword}%")
            if source_conditions:
                sql_clauses.append(f"({' OR '.join(source_conditions)})")
        
        if policy_ids:
            # policy_ids are stored in dc.section or as a tag
            id_conditions = []
            for pid in policy_ids:
                id_conditions.append("(dc.section = %s OR %s = ANY(dc.tags))")
                sql_params.extend([pid, pid])
            if id_conditions:
                sql_clauses.append(f"({' OR '.join(id_conditions)})")

        all_text_terms = list(set((themes or []) + (keywords or [])))
        text_search_conditions = []
        if all_text_terms:
            for term in all_text_terms:
                if term and isinstance(term, str):
                    text_search_conditions.append("(dc.chunk_text ILIKE %s OR %s = ANY(dc.tags))")
                    sql_params.extend([f"%{term}%", term])
            if text_search_conditions:
                sql_clauses.append(f"({' OR '.join(text_search_conditions)})")
        
        cols_to_select = "dc.chunk_id, dc.chunk_text, dc.page_number, dc.section as policy_id_tag, dc.tags as chunk_tags, d.doc_id, d.title as policy_document_title, d.document_type as policy_document_type, d.source as policy_document_source"
        base_query_select = f"SELECT {cols_to_select}"
        from_join_clause = " FROM document_chunks dc JOIN documents d ON dc.doc_id = d.doc_id"
        
        final_query_parts = [base_query_select]

        if semantic_query:
            # Use the get_embedding function imported from db_manager
            query_embedding = db_get_embedding(semantic_query) 
            final_query_parts[0] += ", ce.embedding <-> %s AS distance" # Add distance to SELECT
            from_join_clause += " JOIN chunk_embeddings ce ON dc.chunk_id = ce.chunk_id"
            # pgvector expects list for embedding param, insert at the beginning of sql_params
            sql_params.insert(0, list(query_embedding)) 
            order_by_clause = "ORDER BY distance ASC"
        else:
            order_by_clause = "ORDER BY d.source, dc.page_number" # Default order if no semantic query

        final_query_parts.append(from_join_clause)
        if sql_clauses:
            final_query_parts.append(f"WHERE {' AND '.join(sql_clauses)}")
        final_query_parts.append(order_by_clause)
        final_query_parts.append(f"LIMIT %s")
        sql_params.append(limit)

        final_query = " ".join(final_query_parts)
        
        try:
            results = self.db_manager.execute_query(final_query, tuple(sql_params), fetch_all=True)
            # print(f"DEBUG: Policy search query: {final_query} with params {sql_params}")
            # print(f"DEBUG: Policy search results count: {len(results if results else [])}")
            
            output_list = []
            if results:
                for r in results:
                    output_list.append({
                        "policy_clause_id": str(r["chunk_id"]), 
                        "policy_id_tag": r["policy_id_tag"], # This is from dc.section
                        "policy_document_title": r["policy_document_title"],
                        "policy_document_source": r["policy_document_source"], # e.g. NPPF_SAMPLE
                        "text_snippet": r["chunk_text"], 
                        "semantic_distance": r.get("distance"), # Will be None if not semantic_query
                        "tags": r.get("chunk_tags", [])
                    })
            return output_list
        except Exception as e:
            print(f"ERROR during policy search: {type(e).__name__} - {e}")
            print(f"Failed Query: {final_query}")
            print(f"Failed Params: {sql_params}")
            return []

    def get_policy_details_by_id_tag(self, policy_id_tag: str) -> Optional[Dict[str, Any]]:
        # This method aims to get more structured details if available, 
        # potentially by reconstructing from the chunk or if policies were stored more atomically.
        # For now, it's similar to get_policy_full_text_by_id_tag but could be expanded.
        query = """
        SELECT dc.chunk_id, dc.chunk_text, dc.section as policy_id_tag, d.title as doc_title, d.source as doc_source
        FROM document_chunks dc
        JOIN documents d ON dc.doc_id = d.doc_id
        WHERE dc.section = %s AND d.document_type ILIKE 'PolicyDocument_%'
        LIMIT 1;
        """
        result = self.db_manager.execute_query(query, (policy_id_tag,), fetch_one=True)
        if result:
            # Attempt to parse structured info if stored in chunk_text or infer from context
            # For now, returning the main fields
            return {
                "policy_id_tag": result["policy_id_tag"],
                "text_content": result["chunk_text"],
                "document_title": result["doc_title"],
                "document_source": result["doc_source"],
                "chunk_id": str(result["chunk_id"])
            }
        return None

    def get_policy_full_text_by_id_tag(self, policy_id_tag: str) -> Optional[str]:
        # Assumes the 'section' in document_chunks stores the unique policy ID tag
        # and the chunk_text for that section contains the relevant text.
        query = """
        SELECT chunk_text 
        FROM document_chunks dc
        JOIN documents d ON dc.doc_id = d.doc_id
        WHERE dc.section = %s AND d.document_type ILIKE 'PolicyDocument_%' 
        LIMIT 1;
        """
        result = self.db_manager.execute_query(query, (policy_id_tag,), fetch_one=True)
        return result['chunk_text'] if result else None

    # This method was in the target IntentDefiner, but not in this PolicyManager.
    # Adding a basic version for compatibility, though IntentDefiner should ideally
    # be updated to use search_policies more directly.
    def get_policies_by_tags_and_keywords(self, tags: List[str], keywords: List[str], limit: int = 7) -> List[Dict[str, Any]]:
        """
        Simplified search for IntentDefiner compatibility.
        Returns policies matching ANY of the provided tags or keywords.
        The structure returned is adapted to what IntentDefiner's prompt expects.
        """
        # print(f"DEBUG: PolicyManager.get_policies_by_tags_and_keywords called with tags: {tags}, keywords: {keywords}")
        
        # Use existing search_policies, combining tags and keywords into its 'themes' or 'keywords'
        combined_terms = list(set((tags or []) + (keywords or [])))
        
        # We need to map the output of search_policies to the format IntentDefiner expects:
        # [{"id": p['id'], "title": p.get('title'), "summary": p.get('text_summary')}]
        # search_policies returns: {"policy_id_tag": ..., "text_snippet": ...}
        
        raw_results = self.search_policies(themes=combined_terms, keywords=combined_terms, limit=limit)
        
        # print(f"DEBUG: Raw results from search_policies in get_policies_by_tags_and_keywords: {len(raw_results)}")

        # Transform results
        transformed_results = []
        for res in raw_results:
            # Heuristic to extract a title and summary from text_snippet if possible
            title_cand = res.get("policy_id_tag", "Policy Detail") # Use ID tag as a fallback title
            summary_cand = res.get("text_snippet", "")
            
            # Try to find "Policy Title:" or "Summary:" in the snippet
            # This is a heuristic based on how _ingest_sample_policies_from_json structures chunk_text
            lines = summary_cand.split('\n')
            extracted_title = None
            extracted_summary = None

            for line in lines:
                if line.lower().startswith("policy title:"):
                    extracted_title = line[len("policy title:"):].strip()
                elif line.lower().startswith("summary:"):
                    extracted_summary = line[len("summary:"):].strip()
                    # If full text follows summary, try to keep summary concise
                    if "full text:" in summary_cand.lower():
                        extracted_summary = extracted_summary.split("Full Text:")[0].strip()
            
            if not extracted_summary and summary_cand: # Fallback if "Summary:" not found
                 extracted_summary = (summary_cand[:250] + '...') if len(summary_cand) > 250 else summary_cand


            transformed_results.append({
                "id": res.get("policy_id_tag"), # This is the unique ID for the policy clause/item
                "title": extracted_title or title_cand,
                "text_summary": extracted_summary or "Summary not available.", # Ensure there's always a summary
                # Include original source for context if needed by IntentDefiner later
                "policy_document_source": res.get("policy_document_source"),
                "original_snippet": res.get("text_snippet") # For debugging or more complex parsing
            })
        # print(f"DEBUG: Transformed results for IntentDefiner: {json.dumps(transformed_results, indent=1)}")
        return transformed_results
