# agents/base_agent.py
import time
import json
from typing import Any, Dict, List
from config import GEMINI_API_KEY
import google.generativeai as genai
from core_types import Intent # Keep ProvenanceLog on Intent

class BaseSubsidiaryAgent:
    def __init__(self, agent_name: str, model_name: str):
        self.agent_name = agent_name
        self.model_name = model_name
        print(f"INFO: Initialized BaseSubsidiaryAgent: {self.agent_name} with model {self.model_name}.")

    def _prepare_gemini_content(self, intent: Intent, agent_specific_prompt_prefix: str) -> list:
        # (Same logic as in the previous agents.py _prepare_gemini_content)
        parts: List[Any] = [agent_specific_prompt_prefix]
        # Add policy summaries if present on the intent
        if intent.llm_policy_context_summary:
            intent.provenance.add_action(f"Agent {self.agent_name} using policy summaries.", {"count": len(intent.llm_policy_context_summary)})
            parts.append("\n\n--- Key Relevant Policies Summary Start ---\n")
            for policy_info in intent.llm_policy_context_summary:
                parts.append(f"\nPolicy ID: {policy_info['id']} (Title: {policy_info.get('title', 'N/A')})\nSummary: {policy_info['summary']}\n")
            parts.append("\n--- Key Relevant Policies Summary End ---\n")

        if intent.full_documents_context:
            intent.provenance.add_action(f"Agent {self.agent_name} using full document context.", {"docs": [d['doc_id'] for d in intent.full_documents_context]})
            for doc_data in intent.full_documents_context:
                parts.append(f"\n\n--- Full Document Start (ID: {doc_data['doc_id']}, Title: {doc_data.get('doc_title', 'N/A')}) ---\n{doc_data['full_text']}\n--- Full Document End ---\n")
        elif intent.chunk_context:
            intent.provenance.add_action(f"Agent {self.agent_name} using chunk context.", {"chunk_count": len(intent.chunk_context)})
            parts.append("\n\n--- Relevant Document Chunks Start ---\n")
            for chunk_data in intent.chunk_context:
                parts.append(f"\n-- Chunk (ID: {chunk_data['chunk_id']}, Doc: {chunk_data['metadata'].get('doc_title', 'N/A')}, Page: {chunk_data['metadata'].get('page_number', 'N/A')}) --\n{chunk_data['chunk_text']}\n")
            parts.append("\n--- Relevant Document Chunks End ---\n")
        else: parts.append("\n\n--- No specific document context provided to agent. ---\n")
        return parts

    def process(self, intent: Intent, agent_input_data: Dict, agent_specific_prompt_prefix: str) -> Dict[str, Any]:
        intent.provenance.add_action(f"Agent '{self.agent_name}' processing started", {"inputs": list(agent_input_data.keys())})
        gemini_content_parts = self._prepare_gemini_content(intent, agent_specific_prompt_prefix)
        try:
            time.sleep(0.6)
            response = genai.models.generate_content(
                model=self.model_name,
                contents=gemini_content_parts,
                generation_config={"temperature": 0.1},
                request_options={'timeout': 120},
                api_key=GEMINI_API_KEY
            )
            candidates = getattr(response, 'candidates', None)
            if not candidates or not getattr(candidates[0], 'content', None) or not getattr(candidates[0].content, 'parts', None):
                block_reason = getattr(getattr(response, 'prompt_feedback', None), 'block_reason', 'Unknown')
                raise Exception(f"Agent '{self.agent_name}' Gemini call blocked/empty. Reason: {block_reason}")
            generated_text_or_json_str = "".join([getattr(part, 'text', str(part)) for part in candidates[0].content.parts])
            intent.provenance.add_action(f"Agent '{self.agent_name}' Gemini call successful")
            agent_output = {"generated_raw": generated_text_or_json_str}
            if agent_input_data.get("expected_output_mime_type") == "application/json":
                try:
                    agent_output["structured_payload"] = json.loads(generated_text_or_json_str)
                except json.JSONDecodeError:
                    agent_output["structured_payload_error"] = "Failed to parse agent JSON output"
            return {
                "agent_name": self.agent_name,
                "model_used": self.model_name,
                "agent_output": agent_output,
                "input_echo": agent_input_data
            }
        except Exception as e:
            error_msg = f"Agent '{self.agent_name}' Gemini call failed: {type(e).__name__} - {e}"
            intent.provenance.add_action(error_msg, {"exception_type": type(e).__name__})
            print(f"ERROR: {error_msg}")
            raise
