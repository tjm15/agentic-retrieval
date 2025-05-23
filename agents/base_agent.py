# agents/base_agent.py
from typing import Dict, Any, Optional, List
from google.generativeai.generative_models import GenerativeModel # MODIFIED: Corrected import path
from google.generativeai.types import GenerationConfig
import time
import json
from core_types import Intent
from config import SUBSIDIARY_AGENT_GEN_CONFIG

class BaseSubsidiaryAgent:
    def __init__(self, agent_name: str, model_instance: GenerativeModel): # MODIFIED: Use direct import
        self.agent_name = agent_name
        self.model = model_instance
        print(f"INFO: Init BaseSubsidiaryAgent: {self.agent_name} with model {self.model.model_name}")

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
            
            generation_config_obj = GenerationConfig(**current_gen_config_dict) # MODIFIED: Use imported GenerationConfig
            
            time.sleep(0.7) 
            response = self.model.generate_content(gemini_parts, generation_config=generation_config_obj)

            if not response.candidates or not response.candidates[0].content.parts:
                feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                block_reason = feedback.block_reason if feedback and hasattr(feedback, 'block_reason') else 'Unknown'
                safety_ratings_str = str(feedback.safety_ratings) if feedback and hasattr(feedback, 'safety_ratings') else 'N/A'
                error_detail = f"Agent '{self.agent_name}' LLM call resulted in no content. Block Reason: {block_reason}. Safety Ratings: {safety_ratings_str}"
                intent.provenance.add_action(error_detail, {"block_reason": block_reason, "safety_ratings": safety_ratings_str})
                raise Exception(error_detail)

            raw_output_text = "".join([part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')])
            intent.provenance.add_action(f"Agent '{self.agent_name}' LLM call successful.", {"output_length": len(raw_output_text)})

            output_payload = {"generated_raw": raw_output_text}
            if generation_config_obj.response_mime_type == "application/json":
                try:
                    output_payload["structured_payload"] = json.loads(raw_output_text)
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
