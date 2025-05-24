# mrm/node_processor.py
import json
import time
from typing import Dict, Optional, Any, List, Tuple 
from google import genai
from typing import cast
from google.genai.types import GenerateContentConfigDict

from config import MRM_CORE_GEN_CONFIG, MRM_MODEL_NAME, CACHE_ENABLED

from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog
from retrieval.retriever import AgenticRetriever
from agents.base_agent import BaseSubsidiaryAgent
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from cache.gemini_cache import GeminiResponseCache

class NodeProcessor:
    def __init__(self, api_key: str, retriever: AgenticRetriever, subsidiary_agents: Dict[str, BaseSubsidiaryAgent], policy_manager: PolicyManager):
        self.client = genai.Client(api_key=api_key)
        self.model_name = MRM_MODEL_NAME
        self.generation_config = MRM_CORE_GEN_CONFIG
        self.retriever = retriever
        self.subsidiary_agents = subsidiary_agents
        self.policy_manager = policy_manager
        
        # Initialize cache if enabled
        self.cache = GeminiResponseCache() if CACHE_ENABLED else None
        
        print(f"INFO: NodeProcessor initialized.")
        if CACHE_ENABLED:
            print(f"INFO: NodeProcessor caching enabled")

    def _prepare_mrm_synthesis_content(self, intent: Intent, mrm_task_prompt: str) -> List[Any]:
        parts: List[Any] = [mrm_task_prompt]
        if intent.context_data_from_prior_steps:
            intent.provenance.add_action("NodeProcessor using context from prior steps.", {"keys": list(intent.context_data_from_prior_steps.keys())})
            parts.append("\\\\n\\\\n--- Context from Previous Reasoning Steps Start ---\\\\n")
            for k,v in intent.context_data_from_prior_steps.items():
                parts.append(f"\\\\n-- Prior Step Output: {k} --\\\\n{json.dumps(v, indent=1, default=str)}\\\\n")
            parts.append("\\\\n--- Context End ---\\\\n")
        if intent.llm_policy_context_summary:
            intent.provenance.add_action("NodeProcessor using policy summaries.", {"count": len(intent.llm_policy_context_summary)})
            parts.append("\\\\n\\\\n---Key Policies Summary---\\\\n")
            for p in intent.llm_policy_context_summary:
                parts.append(f"ID:{p['id']} T:{p.get('title')}\\nS:{p['summary']}\\n")
            parts.append("---End Policies---\\\\n")
        if intent.full_documents_context:
            intent.provenance.add_action("NodeProcessor using full docs.", {"docs": [d['doc_id'] for d in intent.full_documents_context]})
            for d in intent.full_documents_context: 
                parts.append(f"\\\\n---FullDoc ID:{d['doc_id']},T:{d.get('doc_title')}---\\\\n{d['full_text']}\\\\n---EndDoc---\\\\n")
        elif intent.chunk_context:
            intent.provenance.add_action("NodeProcessor using chunks.", {"cnt": len(intent.chunk_context)})
            parts.append("\\\\n---Doc Chunks---\\\\n")
            for c in intent.chunk_context:
                parts.append(f"\\\\n--Chunk ID:{c['chunk_id']},Doc:{c['metadata'].get('doc_title')},Pg:{c['metadata'].get('page_number')}--\\\\n{c['chunk_text']}\\\\n")
            parts.append("---End Chunks---\\\\n")
        if not any([intent.full_documents_context, intent.chunk_context, intent.context_data_from_prior_steps, intent.llm_policy_context_summary]):
            parts.append("\\\\n---No specific document, prior step, or policy context for synthesis.---\\\\n")
        return parts

    def _check_satisfaction(self, intent: Intent) -> Tuple[bool, Optional[str]]:
        intent.provenance.add_action("Satisfaction check", {"criteria_len": len(intent.satisfaction_criteria)})
        for criterion in intent.satisfaction_criteria:
            crit_type = criterion.get("type","").upper()
            if "EVIDENCED_ASSESSMENT" in crit_type or "LLM_DEFINED_INTENT_SATISFACTION" in crit_type or "GENERIC_COMPLETION" in crit_type:
                if not intent.synthesized_text_output and not intent.structured_json_output: return False, "No output from LLM/Agent."
            elif "SCHEMA_POPULATED" in crit_type and intent.data_requirements.get("schema"):
                if not isinstance(intent.structured_json_output, dict): return False, "Expected JSON for schema check."
                if intent.data_requirements["schema"] and not all(k in intent.structured_json_output for k in intent.data_requirements["schema"]):
                    return False, f"JSON missing schema keys: {list(intent.data_requirements['schema'].keys())}"
        intent.provenance.add_action("Satisfaction check passed (NodeProcessor)")
        return True, None

    def _estimate_confidence(self, intent: Intent) -> float:
        score = 0.75
        if intent.status == IntentStatus.FAILED: return 0.05
        if intent.status == IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED: score -= 0.35
        has_ctx = intent.full_documents_context or intent.chunk_context or intent.context_data_from_prior_steps or intent.llm_policy_context_summary
        if not has_ctx : score -= 0.25
        elif len(intent.chunk_context or []) < 2 and not intent.full_documents_context and not intent.context_data_from_prior_steps : score -= 0.1
        if not intent.synthesized_text_output and not intent.structured_json_output: return 0.05
        elif len(intent.synthesized_text_output or "") < 30 : score -= 0.2
        if intent.structured_json_output and intent.structured_json_output.get("error"): score -=0.3
        return max(0.0, min(1.0, score))

    def _should_attempt_auto_clarification(self, intent: Optional[Intent], reason: Optional[str]) -> bool: 
        if not intent or not intent.error_message : return False 
        if any(kw in intent.error_message.lower() for kw in ["not found", "ambiguous", "insufficient", "criteria not met", "unclear"]):
            retry_count = getattr(intent, '_clarification_attempts', 0)
            return retry_count < 1
        return False

    def process_intent(self, intent: Intent):
        intent.status = IntentStatus.IN_PROGRESS
        intent.provenance.add_action("Intent processing started by NodeProcessor V8+")
        agent_report_content: Optional[Dict] = None

        needs_app_doc_retrieval = ( # MODIFIED: Wrapped in parentheses for multi-line
            "RETRIEVE" in intent.task_type or
            (
                ("ASSESS" in intent.task_type or "SYNTHESIZE" in intent.task_type) and
                not intent.task_type == "SYNTHESIZE_SUMMARY_OF_SUB_NODES"
            )
        )
        if needs_app_doc_retrieval:
            try: self.retriever.retrieve_and_prepare_context(intent)
            except Exception as e: intent.status = IntentStatus.FAILED; intent.error_message = f"App Doc Retrieval failed: {e}"

        if intent.status != IntentStatus.FAILED and intent.agent_to_invoke:
            agent_policy_reqs = intent.agent_input_data.get("agent_policy_context_requirements") 
            if isinstance(agent_policy_reqs, dict):
                themes = agent_policy_reqs.get("themes", [])
                keywords_or_ids = agent_policy_reqs.get("specific_policy_ids_or_keywords", [])
                if themes or keywords_or_ids:
                    intent.provenance.add_action(f"NodeProcessor retrieving policy context for agent \'{intent.agent_to_invoke}\'")
                    retrieved_clauses = self.policy_manager.search_policies(
                        themes=themes, keywords=keywords_or_ids, limit=3
                    )
                    if retrieved_clauses:
                        intent.agent_input_data["retrieved_policy_clauses_for_agent"] = retrieved_clauses 
                        intent.provenance.add_action(f"Retrieved {len(retrieved_clauses)} policy clauses for agent.", {"ids": [p.get('policy_id_tag', p.get('id')) for p in retrieved_clauses]})

        if intent.status != IntentStatus.FAILED and intent.agent_to_invoke:
            if intent.agent_to_invoke in self.subsidiary_agents:
                agent = self.subsidiary_agents[intent.agent_to_invoke]
                try:
                    agent_prompt_prefix = intent.agent_input_data.get("agent_specific_prompt_prefix", f"Task for {agent.agent_name}: {intent.assessment_focus}")
                    agent_report_content = agent.process(intent, intent.agent_input_data, agent_prompt_prefix)
                    intent.provenance.add_action(f"Agent \'{intent.agent_to_invoke}\' successful")
                except Exception as e: intent.status = IntentStatus.FAILED; intent.error_message = f"Agent {intent.agent_to_invoke} failed: {e}"
            else: intent.status = IntentStatus.FAILED; intent.error_message = f"Agent \'{intent.agent_to_invoke}\' not found."

        if intent.status != IntentStatus.FAILED and ("SYNTHESIZE" in intent.task_type or "ASSESS" in intent.task_type or "BALANCE" in intent.task_type):
            mrm_synthesis_prompt = (f"Task: '{intent.task_type}'. Node: {intent.parent_node_id}. Focus: '{intent.assessment_focus}'. App Refs: {intent.application_refs}. Output: {intent.output_format_request}.")
            if intent.data_requirements.get("schema"): mrm_synthesis_prompt += f" Expected JSON Schema: {json.dumps(intent.data_requirements['schema'], indent=1)}"
            if agent_report_content: mrm_synthesis_prompt += f"\n\n---Agent Report ({intent.agent_to_invoke})---\n{json.dumps(agent_report_content, indent=1, default=str)}\n---End Report---"
            gemini_mrm_content = self._prepare_mrm_synthesis_content(intent, mrm_synthesis_prompt)
            try:
                intent.provenance.add_action("MRM Synthesis (Gemini Pro) call", {"prompt_len": sum(len(str(p)) for p in gemini_mrm_content)})
                config = cast(GenerateContentConfigDict, dict(MRM_CORE_GEN_CONFIG))  # Use centralized config
                if "JSON" in intent.output_format_request.upper() or intent.data_requirements.get("schema"):
                    config["response_mime_type"] = "application/json"
                
                # Try cache first if enabled
                if self.cache:
                    # Convert gemini_mrm_content to a hashable prompt string for caching
                    prompt_for_cache = "\n".join([str(part) for part in gemini_mrm_content])
                    # Convert config to dictionary format for cache compatibility
                    config_dict = dict(config)
                    cached_response = self.cache.get(prompt_for_cache, config_dict, self.model_name)
                    if cached_response:
                        print(f"DEBUG: NodeProcessor using cached MRM synthesis response for {intent.parent_node_id}")
                        response = cached_response
                    else:
                        print(f"DEBUG: NodeProcessor no cache hit, making MRM synthesis request for {intent.parent_node_id} - may take 2-5 minutes...")
                        response = self.client.models.generate_content(
                            model=self.model_name,
                            contents=gemini_mrm_content,
                            config=config
                        )
                        print(f"DEBUG: NodeProcessor received MRM synthesis response for {intent.parent_node_id}")
                        # Cache the response
                        self.cache.put(prompt_for_cache, config_dict, self.model_name, response)
                else:
                    # No caching, make direct API call
                    print(f"DEBUG: NodeProcessor sending MRM synthesis request for {intent.parent_node_id} - may take 2-5 minutes...")
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=gemini_mrm_content,
                        config=config
                    )
                    print(f"DEBUG: NodeProcessor received MRM synthesis response for {intent.parent_node_id}")
                text = getattr(response, "text", None)
                if not text and hasattr(response, "candidates") and response.candidates:
                    first_candidate = response.candidates[0]
                    content = getattr(first_candidate, "content", None)
                    parts = getattr(content, "parts", None) if content else None
                    if parts:
                        text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
                if not text or not isinstance(text, str):
                    raise ValueError("No valid text response from Gemini API.")
                # Handle JSON response
                if config.get("response_mime_type") == "application/json" and isinstance(text, str):
                    try:
                        intent.structured_json_output = json.loads(text)
                        intent.synthesized_text_output = json.dumps(intent.structured_json_output, indent=2, default=str)
                    except json.JSONDecodeError:
                        intent.provenance.add_action("MRM JSON parse fail")
                        intent.synthesized_text_output=text
                        intent.structured_json_output={"err":"JSON fail","raw":text}
                else:
                    intent.synthesized_text_output = text
                    intent.structured_json_output = {"summary": (text or "")[:500]+"..."}
                intent.provenance.add_action("MRM Synthesis OK")
            except Exception as e:
                intent.status = IntentStatus.FAILED
                intent.error_message = f"MRM Synth fail: {e}"
        
        elif intent.status != IntentStatus.FAILED: 
            if agent_report_content: intent.structured_json_output = agent_report_content; intent.synthesized_text_output = json.dumps(agent_report_content, indent=2, default=str)
            elif needs_app_doc_retrieval: intent.structured_json_output = {"retrieved_summary": {"chunks": len(intent.chunk_context or []), "docs": len(intent.full_documents_context or [])}}; intent.synthesized_text_output = f"Retrieved {len(intent.chunk_context or [])} chunks / {len(intent.full_documents_context or [])} docs."
            else: intent.provenance.add_action("WARN: Intent no primary action.")

        if intent.status != IntentStatus.FAILED:
            satisfied, reason = self._check_satisfaction(intent)
            if not satisfied: intent.status = IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED; intent.error_message = intent.error_message or reason or "NodeProc: Satisfaction criteria fail."
            else: intent.status = IntentStatus.COMPLETED_SUCCESS
        
        intent.confidence_score = self._estimate_confidence(intent)
        intent.provenance.complete(intent.status.value, {"conf": intent.confidence_score, "out_prev": str(intent.structured_json_output)[:100]})
