# mrm/node_processor.py
import json
import time
from typing import Dict, Optional, Any, List, Tuple 
from typing import cast

from config import MRM_CORE_GEN_CONFIG, MRM_MODEL_NAME, CACHE_ENABLED, create_llm_client

from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog
from retrieval.retriever import AgenticRetriever
from agents.base_agent import BaseSubsidiaryAgent
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from cache.gemini_cache import GeminiResponseCache

class NodeProcessor:
    def __init__(self, api_key: str, retriever: AgenticRetriever, subsidiary_agents: Dict[str, BaseSubsidiaryAgent], policy_manager: PolicyManager):
        # Use the new LLM client with fallback support
        self.llm_client = create_llm_client()
        self.model_name = MRM_MODEL_NAME
        self.generation_config = MRM_CORE_GEN_CONFIG
        self.retriever = retriever
        self.subsidiary_agents = subsidiary_agents
        self.policy_manager = policy_manager
        
        # Initialize cache if enabled
        self.cache = GeminiResponseCache() if CACHE_ENABLED else None
        
        print(f"INFO: NodeProcessor initialized with LLM client: {self.llm_client.__class__.__name__}")
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
                intent.provenance.add_action("MRM Synthesis (LLM) call", {"prompt_len": sum(len(str(p)) for p in gemini_mrm_content)})
                config = dict(MRM_CORE_GEN_CONFIG)  # Use centralized config
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
                        # Convert cached response to text format
                        text = getattr(cached_response, "text", None)
                        if not text and hasattr(cached_response, "candidates") and cached_response.candidates:
                            first_candidate = cached_response.candidates[0]
                            content = getattr(first_candidate, "content", None)
                            parts = getattr(content, "parts", None) if content else None
                            if parts:
                                text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
                        response_text = text or ""
                    else:
                        print(f"DEBUG: NodeProcessor no cache hit, making MRM synthesis request for {intent.parent_node_id} - may take 2-5 minutes...")
                        llm_response = self.llm_client.generate_content(
                            contents=gemini_mrm_content,
                            config=config,
                            model=self.model_name
                        )
                        response_text = llm_response.text
                        print(f"DEBUG: NodeProcessor received MRM synthesis response using {llm_response.provider} ({llm_response.model_used}) for {intent.parent_node_id}")
                        # Cache the response in original format if possible
                        if hasattr(llm_response, 'raw_response') and llm_response.raw_response:
                            self.cache.put(prompt_for_cache, config_dict, self.model_name, llm_response.raw_response)
                else:
                    # No caching, make direct API call
                    print(f"DEBUG: NodeProcessor sending MRM synthesis request for {intent.parent_node_id} - may take 2-5 minutes...")
                    llm_response = self.llm_client.generate_content(
                        contents=gemini_mrm_content,
                        config=config,
                        model=self.model_name
                    )
                    response_text = llm_response.text
                    print(f"DEBUG: NodeProcessor received MRM synthesis response using {llm_response.provider} ({llm_response.model_used}) for {intent.parent_node_id}")
                
                if not response_text or not isinstance(response_text, str):
                    raise ValueError("No valid text response from LLM API.")
                # Handle JSON response
                if config.get("response_mime_type") == "application/json" and isinstance(response_text, str):
                    try:
                        intent.structured_json_output = json.loads(response_text)
                        intent.synthesized_text_output = json.dumps(intent.structured_json_output, indent=2, default=str)
                    except json.JSONDecodeError:
                        intent.provenance.add_action("MRM JSON parse fail")
                        intent.synthesized_text_output = response_text
                        intent.structured_json_output = {"err":"JSON fail","raw":response_text}
                else:
                    intent.synthesized_text_output = response_text
                    intent.structured_json_output = {"summary": (response_text or "")[:500]+"..."}
                intent.provenance.add_action("MRM Synthesis OK")
            except Exception as e:
                intent.status = IntentStatus.FAILED
                intent.error_message = f"MRM Synth fail: {e}"
        
        elif intent.status != IntentStatus.FAILED: 
            if agent_report_content: 
                intent.structured_json_output = agent_report_content
                intent.synthesized_text_output = json.dumps(agent_report_content, indent=2, default=str)
            elif needs_app_doc_retrieval: 
                intent.structured_json_output = {"retrieved_summary": {"chunks": len(intent.chunk_context or []), "docs": len(intent.full_documents_context or [])}}
                intent.synthesized_text_output = f"Retrieved {len(intent.chunk_context or [])} chunks / {len(intent.full_documents_context or [])} docs."
            else: 
                # Fallback: If no primary action was taken, attempt basic synthesis
                intent.provenance.add_action("WARN: Intent no primary action specified. Attempting fallback synthesis.")
                
                # Check if this should have had an agent but didn't
                if any(keyword in intent.task_type.upper() for keyword in ["ASSESS", "SYNTHESIZE", "ANALYZE", "BALANCE"]) and not intent.agent_to_invoke:
                    intent.provenance.add_action("WARN: Task type suggests analysis needed but no agent specified. Using default agent.")
                    # Use default planning analyst as fallback
                    if "default_planning_analyst_agent" in self.subsidiary_agents:
                        try:
                            agent = self.subsidiary_agents["default_planning_analyst_agent"]
                            agent_prompt_prefix = f"Fallback analysis task: {intent.assessment_focus}"
                            agent_report_content = agent.process(intent, intent.agent_input_data, agent_prompt_prefix)
                            intent.structured_json_output = agent_report_content
                            intent.synthesized_text_output = json.dumps(agent_report_content, indent=2, default=str)
                            intent.provenance.add_action("Fallback agent processing successful")
                        except Exception as e:
                            intent.provenance.add_action(f"Fallback agent failed: {e}")
                            # Still provide basic output to prevent total failure
                            intent.structured_json_output = {"status": "incomplete", "reason": "Agent specification failed"}
                            intent.synthesized_text_output = f"Unable to complete analysis: {intent.assessment_focus}. Reason: Agent specification failed."
                    else:
                        # No fallback agent available, provide minimal output
                        intent.structured_json_output = {"status": "incomplete", "reason": "No suitable processing method"}
                        intent.synthesized_text_output = f"Unable to process intent: {intent.assessment_focus}. No suitable processing method identified."
                else:
                    # For non-analysis tasks, provide basic completion
                    intent.structured_json_output = {"status": "completed", "task_type": intent.task_type}
                    intent.synthesized_text_output = f"Task completed: {intent.assessment_focus}"

        if intent.status != IntentStatus.FAILED:
            satisfied, reason = self._check_satisfaction(intent)
            if not satisfied: intent.status = IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED; intent.error_message = intent.error_message or reason or "NodeProc: Satisfaction criteria fail."
            else: intent.status = IntentStatus.COMPLETED_SUCCESS
        
        intent.confidence_score = self._estimate_confidence(intent)
        intent.provenance.complete(intent.status.value, {"conf": intent.confidence_score, "out_prev": str(intent.structured_json_output)[:100]})
