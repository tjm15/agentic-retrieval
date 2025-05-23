# mrm/intent_definer.py
# (Same as intent_definer.py from "Reproduce full updated code" V8 response)
# Assumed complete.
import time
import json
from google import genai
from typing import Dict, List, Optional, Any

# Assuming these are correctly imported relative to this file's location
from core_types import ReasoningNode, Intent, ProvenanceLog
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from config import MRM_MODEL_NAME, INTENT_DEFINER_GEN_CONFIG

class IntentDefiner:
    def __init__(self, policy_manager: PolicyManager, api_key: str):
        self.policy_manager = policy_manager
        self.client = genai.Client(api_key=api_key)
        print(f"INFO: IntentDefiner initialized with Gemini client.")

    def define_intent_spec_via_llm(self, node: ReasoningNode, application_refs: List[str], application_display_name: str,
                                   report_type: str, site_summary_context: Optional[Dict], proposal_summary_context: Optional[Dict],
                                   direct_dependency_outputs: Optional[Dict], node_provenance: ProvenanceLog) -> Optional[Dict[str, Any]]:
        node_provenance.add_action("LLM-driven Intent definition started by IntentDefiner")
        relevant_policies = self.policy_manager.get_policies_by_tags_and_keywords(
            (node.specific_policy_focus_ids or []) + (node.generic_material_considerations or []), 
            (node.key_evidence_document_types or [])
        )
        policy_context_summary_for_prompt = [{"id": p['id'], "title": p.get('title'), "summary": p.get('text_summary')} for p in relevant_policies[:7]]

        intent_spec_prompt = f"""You are an expert Planning Assessment Orchestrator AI (MRM). Define the JSON specification for the *primary processing Intent* for the report section:
        Node ID: {node.node_id}, Description: \"{node.description}\"
        Node Type Tag (Primary Purpose): {node.node_type_tag}
        Generic Material Considerations: {node.generic_material_considerations}
        Specific Policy Focus IDs/Themes: {node.specific_policy_focus_ids}
        Key Evidence Document Types (Hints): {node.key_evidence_document_types}
        Suggested Agent (if any from template/ontology): {node.agent_to_invoke_hint}
        Linked Ontology Entry ID (if applicable): {node.linked_ontology_entry_id}
        Application Context: Report Type: {report_type}, App Name: \"{application_display_name}\", App Refs: {application_refs}
        Site Summary (brief): {json.dumps(site_summary_context, indent=1, default=str)[:300]}...
        Proposal Summary (brief): {json.dumps(proposal_summary_context, indent=1, default=str)[:300]}...
        Relevant Policies for this Node: {json.dumps(policy_context_summary_for_prompt, indent=1)}
        Outputs from Directly Prerequisite Nodes (brief): {json.dumps(direct_dependency_outputs, indent=1, default=str)[:300]}...
        Generate ONLY a valid JSON object for the Intent spec with keys: \"task_type\", \"assessment_focus\", \"policy_context_tags_to_consider\", \"retrieval_config\" ({{\"hybrid_search_terms\":[], \"semantic_search_query_text\":\"\", \"document_type_filters\":[]}}), \"data_requirements_schema\" (JSON schema), \"agent_to_invoke\", \"agent_input_data_preparation_notes\", \"output_format_request_for_llm\".
        Be highly specific and targeted based on node metadata and application context. For material consideration nodes (e.g. /HousingDelivery), ensure assessment_focus and data_requirements_schema are detailed for that topic. For summary nodes (e.g. MaterialConsiderationsBlock_Parent or PlanningBalanceAndConclusionBlock), task_type should be for synthesis of children/prior outputs with minimal new retrieval.
        """
        node_provenance.add_action("Prompting IntentDefiner LLM for Intent Spec", {"prompt_len": len(intent_spec_prompt)})
        try:
            time.sleep(1.0)
            response = self.client.models.generate_content(
                model=MRM_MODEL_NAME,
                contents=[intent_spec_prompt],
                config=INTENT_DEFINER_GEN_CONFIG  # type: ignore
            )
            # Robust response parsing
            raw_json_spec_text = getattr(response, "text", None)
            if not raw_json_spec_text and hasattr(response, "candidates") and response.candidates:
                first_candidate = response.candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    raw_json_spec_text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
            if not raw_json_spec_text or not isinstance(raw_json_spec_text, str):
                raise ValueError("No valid text response from Gemini API.")
            intent_spec_dict = json.loads(raw_json_spec_text)
            node_provenance.add_action("IntentDefiner LLM generated Intent Spec", {"keys": list(intent_spec_dict.keys())})
            if not all(k in intent_spec_dict for k in ["task_type", "assessment_focus", "retrieval_config"]):
                raise ValueError("LLM-gen Intent Spec missing required keys.")
            return intent_spec_dict
        except Exception as e:
            error_msg = f"LLM Intent Spec gen fail for {node.node_id}: {type(e).__name__}-{e}"
            print(f"ERROR:{error_msg}\nPromptStart:{intent_spec_prompt[:500]}...")
            node_provenance.complete("FAILED",{"error":error_msg})
            return None

    def define_clarification_intent_spec_via_llm(self, original_intent: Intent, clarification_reason: Optional[str], node_provenance: ProvenanceLog) -> Optional[Dict[str,Any]]:
        node_provenance.add_action("LLM defining clarification intent spec", {"original_reason": clarification_reason})
        prompt = f"""Intent for app \"{original_intent.application_refs[0] if original_intent.application_refs else 'N/A'}\" (Node: {original_intent.parent_node_id}, Task: {original_intent.task_type}) needs clarification. Reason: {clarification_reason or original_intent.error_message}. Original Output (summary): {str(original_intent.synthesized_text_output)[:300] if original_intent.synthesized_text_output else 'N/A'}. Generate a JSON spec for a *new, focused Intent* to address this. Output ONLY JSON spec with keys from main intent def prompt. New intent is for SAME parent_node_id: \"{original_intent.parent_node_id}\". Refine original elements to be more targeted."""
        try:
            time.sleep(0.8)
            response = self.client.models.generate_content(
                model=MRM_MODEL_NAME,
                contents=[prompt],
                config=INTENT_DEFINER_GEN_CONFIG  # type: ignore
            )
            raw_json_spec_text = getattr(response, "text", None)
            if not raw_json_spec_text and hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    raw_json_spec_text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
            if not raw_json_spec_text or not isinstance(raw_json_spec_text, str):
                raise ValueError("No valid text response from Gemini API.")
            spec = json.loads(raw_json_spec_text)
            node_provenance.add_action("Clarification spec generated by LLM.", {"original_intent_id": str(original_intent.intent_id), "spec_preview": raw_json_spec_text[:150]})
            spec["application_refs"] = original_intent.application_refs
            spec["parent_intent_id"] = original_intent.intent_id
            return spec
        except Exception as e:
            node_provenance.add_action("LLM failed clarification spec gen.", {"error": str(e)})
            print(f"ERROR defining clarification spec: {e}")
            return None
