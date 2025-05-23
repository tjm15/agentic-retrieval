# agents/base_agent.py
from typing import Dict, Any, Optional, List
from google import genai
from config import SUBSIDIARY_AGENT_GEN_CONFIG, VISUAL_HERITAGE_AGENT_GEN_CONFIG, SUBSIDIARY_AGENT_MODEL_NAME, GEMINI_API_KEY
import time
import json
from core_types import Intent

class BaseSubsidiaryAgent:
    def __init__(self, agent_name: str): 
        self.agent_name = agent_name
        self.model_name = SUBSIDIARY_AGENT_MODEL_NAME
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        print(f"INFO: Init BaseSubsidiaryAgent: {self.agent_name}")

    def _prepare_gemini_content(self, intent: Intent, prompt_prefix: str) -> List[Any]:
        parts: List[Any] = [prompt_prefix]
        
        if intent.llm_policy_context_summary:
            intent.provenance.add_action(f"Agent {self.agent_name} using {len(intent.llm_policy_context_summary)} general policy summaries.", 
                                         {"count": len(intent.llm_policy_context_summary)})
            parts.append("\n\n--- Overview of Relevant Policies ---")
            for p_summary in intent.llm_policy_context_summary:
                parts.append(f"Policy ID: {p_summary.get('id', 'N/A')}")
                if p_summary.get('title'): parts.append(f"Title: {p_summary['title']}")
                parts.append(f"Summary: {p_summary.get('summary', 'N/A')}\n")
            parts.append("--- End Overview of Relevant Policies ---\n")

        agent_specific_policies = intent.agent_input_data.get("retrieved_policy_clauses_for_agent", [])
        if agent_specific_policies:
            intent.provenance.add_action(f"Agent {self.agent_name} using {len(agent_specific_policies)} specifically retrieved policy clauses for this task.")
            parts.append("\n\n--- Specific Policy Clauses Relevant to This Task ---")
            for pol_clause in agent_specific_policies:
                parts.append(f"Policy Reference: {pol_clause.get('policy_id_tag', 'N/A')} (from document: {pol_clause.get('policy_document_source', 'N/A')})")
                parts.append(f"Text: {pol_clause.get('text_snippet', 'N/A')}\n")
            parts.append("--- End Specific Policy Clauses ---\n")
        
        if intent.full_documents_context:
            intent.provenance.add_action(f"Agent {self.agent_name} using full application documents.", 
                                         {"docs": [d.get('doc_id', d.get('doc_title', 'UnknownDoc')) for d in intent.full_documents_context]})
            for d_idx, d_content in enumerate(intent.full_documents_context):
                parts.append(f"\n--- Full Application Document Context {d_idx+1} (ID: {d_content.get('doc_id', 'N/A')}, Title: {d_content.get('doc_title', 'N/A')}) ---")
                parts.append(d_content.get('full_text', 'Document text not available.'))
                parts.append(f"--- End Full Application Document Context {d_idx+1} ---\n")
        elif intent.chunk_context:
            intent.provenance.add_action(f"Agent {self.agent_name} using application document chunks.", 
                                         {"count": len(intent.chunk_context)})
            parts.append("\n--- Relevant Application Document Chunks ---")
            for c_idx, c_data in enumerate(intent.chunk_context):
                meta = c_data.get('metadata', {})
                parts.append(f"Chunk {c_idx+1} (ID: {c_data.get('chunk_id', 'N/A')}, from Doc: {meta.get('doc_title', 'N/A')}, Page: {meta.get('page_number', 'N/A')})")
                parts.append(f"Text: {c_data.get('chunk_text', 'Chunk text not available.')}\n")
            parts.append("--- End Relevant Application Document Chunks ---\n")
        else:
            parts.append("\n--- No specific application document context provided to agent for this task. Rely on summaries and policies. ---")
            
        return parts

    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str,Any]:
        intent.provenance.add_action(f"Agent '{self.agent_name}' processing started.", 
                                     {"input_keys": list(agent_input_data.keys()), "focus": intent.assessment_focus})
        
        gemini_parts = self._prepare_gemini_content(intent, prompt_prefix)
        
        try:
            current_gen_config_dict = SUBSIDIARY_AGENT_GEN_CONFIG.copy()
            
            expected_mime_type = agent_input_data.get("expected_output_mime_type")
            if expected_mime_type == "application/json":
                current_gen_config_dict["response_mime_type"] = "application/json"
            
            time.sleep(0.7) 
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[gemini_parts],
                config=current_gen_config_dict  # type: ignore
            )

            # Robust response parsing
            raw_text = getattr(response, "text", None)
            if not raw_text and hasattr(response, "candidates") and response.candidates:
                first_candidate = response.candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    # Only join non-None, str parts
                    raw_text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
            if not raw_text or not isinstance(raw_text, str):
                raise ValueError("No valid text response from Gemini API.")

            intent.provenance.add_action(f"Agent '{self.agent_name}' LLM call successful.", {"output_length": len(raw_text)})

            output_payload = {"generated_raw": raw_text}
            if current_gen_config_dict["response_mime_type"] == "application/json":
                try:
                    output_payload["structured_payload"] = json.loads(raw_text)
                except json.JSONDecodeError as json_err:
                    intent.provenance.add_action(f"Agent '{self.agent_name}' failed to parse its JSON output.", {"error": str(json_err)})
                    output_payload["structured_payload_error"] = f"Failed to parse agent JSON output: {json_err}"
            
            return {
                "agent_name": self.agent_name,
                "agent_output": output_payload,
                "status": "SUCCESS",
                "error_message": None
            }
        except Exception as e:
            intent.provenance.add_action(f"Agent '{self.agent_name}' failed during LLM call or output processing.", 
                                         {"error_type": type(e).__name__, "error_message": str(e)})
            return {
                "agent_name": self.agent_name,
                "agent_output": None,
                "status": "FAILED",
                "error_message": f"Agent '{self.agent_name}' failed: {type(e).__name__} - {str(e)}"
            }

    def _call_llm(self, prompt: str, config: dict) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config  # type: ignore
            )
            # Robust response parsing
            text = getattr(response, "text", None)
            if not text and hasattr(response, "candidates") and response.candidates:
                first_candidate = response.candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    # Only join non-None, string parts
                    text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
            if not text or not isinstance(text, str):
                raise ValueError("No valid text response from Gemini API.")
            return text
        except Exception as e:
            print(f"ERROR in _call_llm: {e}")
            return ""
