# mrm/mrm_orchestrator.py
# Modular Reasoning Machine (MRM) Orchestrator - V9
# Integrates IntentDefiner, NodeProcessor, and all knowledge base managers.

import json
import time
import uuid
from google.generativeai.generative_models import GenerativeModel # MODIFIED: Corrected import path
from typing import Dict, List, Optional, Any

# Core application components
from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog # Assuming ProvenanceLog has a to_dict or similar method for serialization
from db_manager import DatabaseManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from knowledge_base.policy_manager import PolicyManager
from retrieval.retriever import AgenticRetriever
from .intent_definer import IntentDefiner
from .node_processor import NodeProcessor

from agents.visual_heritage_agent import VisualHeritageAgent # MODIFIED: Corrected class name
from agents.base_agent import BaseSubsidiaryAgent 

from config import (
    GEMINI_API_KEY, MRM_MODEL_NAME, SUBSIDIARY_AGENT_MODEL_NAME,
    DB_CONFIG, REPORT_TEMPLATE_DIR, MC_ONTOLOGY_DIR, POLICY_KB_DIR
)

if not GEMINI_API_KEY:
    raise ValueError("CRITICAL: GEMINI_API_KEY not found. Please set it in your environment or .env file.")
# Assuming genai.configure is the correct way to set the API key for the version of the library used.
# If not, this might need to be genai.API_KEY = GEMINI_API_KEY or similar.
# genai.configure(api_key=GEMINI_API_KEY) # REMOVED: API key is typically handled by GOOGLE_API_KEY env var

subsidiary_llm_instance = GenerativeModel(SUBSIDIARY_AGENT_MODEL_NAME)
mrm_core_llm_instance = GenerativeModel(MRM_MODEL_NAME)


class MRMOrchestrator:
    MAX_CLARIFICATION_ATTEMPTS_PER_NODE = 2

    def __init__(self, db_manager: DatabaseManager,
                 report_template_manager: ReportTemplateManager,
                 mc_ontology_manager: MaterialConsiderationOntology,
                 policy_manager: PolicyManager):
        
        self.db_manager = db_manager
        self.report_template_manager = report_template_manager
        self.mc_ontology_manager = mc_ontology_manager
        self.policy_manager = policy_manager
        
        print(f"INFO: MRMOrchestrator initializing with DB: {type(db_manager).__name__}, PolicyMgr: {type(policy_manager).__name__}")

        self.retriever = AgenticRetriever(self.db_manager)
        print(f"INFO: AgenticRetriever initialized with DB: {type(db_manager).__name__}")

        self.subsidiary_agents: Dict[str, BaseSubsidiaryAgent] = {
            "VisualHeritageAssessment_GeminiFlash_V1": VisualHeritageAssessmentAgent(subsidiary_llm_instance),
        }
        print(f"INFO: Initialized {len(self.subsidiary_agents)} subsidiary agents: {list(self.subsidiary_agents.keys())}")

        self.intent_definer = IntentDefiner(self.policy_manager)
        print(f"INFO: IntentDefiner initialized with PolicyManager: {type(policy_manager).__name__}")

        self.node_processor = NodeProcessor(
            mrm_model_instance=mrm_core_llm_instance,
            retriever=self.retriever,
            subsidiary_agents=self.subsidiary_agents,
            policy_manager=self.policy_manager
        )
        print(f"INFO: NodeProcessor initialized with MRM Model: {mrm_core_llm_instance.model_name}, Retriever, {len(self.subsidiary_agents)} agents, and PolicyManager.")

        self.application_context_cache: Dict[str, Dict[str, Any]] = {}
        self.overall_provenance_logs: List[ProvenanceLog] = []

    def _get_or_create_application_context_summary(self, application_refs: List[str], app_display_name: str) -> Dict[str, Any]:
        cache_key = f"app_summary_{'_'.join(sorted(application_refs))}"
        if cache_key in self.application_context_cache:
            return self.application_context_cache[cache_key]
        
        site_desc_query = "SELECT chunk_text FROM document_chunks dc JOIN documents d ON dc.doc_id = d.doc_id WHERE d.source = ANY(%s) AND (d.document_type ILIKE %s OR dc.tags @> ARRAY[%s]) ORDER BY d.upload_date DESC, dc.page_number ASC LIMIT 1"
        
        site_text_row = self.db_manager.execute_query(site_desc_query, (application_refs, "%SiteDescription%", "site_description"), fetch_one=True)
        site_summary = site_text_row['chunk_text'][:500] + "..." if site_text_row and site_text_row['chunk_text'] else f"No detailed site description found for {app_display_name} via placeholder query."

        proposal_text_row = self.db_manager.execute_query(site_desc_query, (application_refs, "%ProposalDescription%", "proposal_summary"), fetch_one=True)
        proposal_summary = proposal_text_row['chunk_text'][:500] + "..." if proposal_text_row and proposal_text_row['chunk_text'] else f"No detailed proposal description found for {app_display_name} via placeholder query."

        summary = {
            "application_name": app_display_name,
            "application_identifiers": application_refs,
            "site_summary_placeholder": site_summary,
            "proposal_summary_placeholder": proposal_summary,
            "key_documents_hint": ["ApplicationForm.pdf", "PlanningStatement.pdf", "DesignAccessStatement.pdf"]
        }
        self.application_context_cache[cache_key] = summary
        return summary

    def _build_reasoning_tree_from_template(self, template_data: Dict, application_refs: List[str], app_display_name: str, parent_node_id_prefix: str = "") -> ReasoningNode:
        root_node_id = f"{parent_node_id_prefix}ROOT_{template_data.get('report_type_id', 'GenericReport')}"
        root = ReasoningNode(
            node_id=root_node_id,
            description=template_data.get("description", "Root of the Planning Report")
        )
        root.application_refs = application_refs

        def build_node_recursive(section_data: Dict, current_parent_id: str) -> ReasoningNode:
            node_id_suffix = section_data.get("node_id", str(uuid.uuid4())[:8])
            full_node_id = f"{current_parent_id}/{node_id_suffix}" if current_parent_id else node_id_suffix
            
            node = ReasoningNode(
                node_id=full_node_id,
                description=section_data.get("description", "No description provided.")
            )
            node.application_refs = application_refs
            node.node_type_tag = section_data.get("node_type_tag")
            node.generic_material_considerations = section_data.get("generic_material_considerations", [])
            node.specific_policy_focus_ids = section_data.get("specific_policy_focus_ids", [])
            node.key_evidence_document_types = section_data.get("key_evidence_document_types", [])
            node.linked_ontology_entry_id = section_data.get("linked_ontology_entry_id")
            node.is_dynamic_parent_node = section_data.get("is_dynamic_parent_node", False)
            node.agent_to_invoke_hint = section_data.get("agent_to_invoke_hint")
            node.depends_on_nodes = [f"{current_parent_id}/{dep}" if dep and not dep.startswith(root_node_id) and not dep.startswith("ROOT_") else dep for dep in section_data.get("depends_on_nodes", [])]
            node.data_requirements_schema_hint = section_data.get("data_requirements_schema_hint")


            if node.linked_ontology_entry_id:
                mc_details = self.mc_ontology_manager.get_consideration_details(node.linked_ontology_entry_id)
                if mc_details:
                    node.description = mc_details.get("display_name_template", node.description).replace("{app_name}", app_display_name)
                    node.generic_material_considerations.extend(mc_details.get("primary_tags", []))
                    node.specific_policy_focus_ids.extend(mc_details.get("relevant_policy_themes", []))
                    node.key_evidence_document_types.extend(mc_details.get("key_evidence_docs", []))
                    if not node.agent_to_invoke_hint and mc_details.get("agent_to_invoke_hint"):
                        node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
                    if not node.data_requirements_schema_hint and mc_details.get("data_schema_hint"):
                        node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
                else:
                    print(f"WARN: Ontology entry ID '{node.linked_ontology_entry_id}' for node '{full_node_id}' not found.")

            if "sub_sections" in section_data:
                for sub_section_data in section_data["sub_sections"]:
                    sub_node = build_node_recursive(sub_section_data, full_node_id)
                    node.add_sub_node(sub_node)
            return node

        for section in template_data.get("sections", []):
            root.add_sub_node(build_node_recursive(section, root_node_id))
        
        return root

    def _process_node_and_children_recursively(self, node: ReasoningNode, 
                                               application_refs: List[str], app_display_name: str,
                                               report_type: str, 
                                               app_context_summary: Dict[str, Any],
                                               processed_node_outputs: Dict[str, Any],
                                               clarification_attempt_counts: Dict[str, int]):
        
        node_provenance = ProvenanceLog(None, f"MRM Orchestration for Node: {node.node_id}")
        node.node_level_provenance = node_provenance
        self.overall_provenance_logs.append(node_provenance)
        node_provenance.add_action(f"Processing node: {node.node_id} (Type: {node.node_type_tag})")

        dependencies_met = True
        direct_dependency_outputs_for_intent = {}
        if node.depends_on_nodes:
            node_provenance.add_action(f"Checking {len(node.depends_on_nodes)} dependencies: {node.depends_on_nodes}")
            for dep_id in node.depends_on_nodes:
                dep_output_data = processed_node_outputs.get(dep_id, {})
                dep_status_value = dep_output_data.get("status")

                # MODIFIED: Corrected multi-line condition
                if (dep_id not in processed_node_outputs or 
                    dep_status_value not in [IntentStatus.COMPLETED_SUCCESS.value, IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED.value]):
                    dependencies_met = False
                    node_provenance.add_action(f"Dependency {dep_id} not met. Status: {dep_status_value}. Skipping.")
                    break
                else:
                    dep_output = processed_node_outputs[dep_id]
                    direct_dependency_outputs_for_intent[dep_id] = {
                        "node_id": dep_id,
                        "status": dep_output.get("status"),
                        "text_summary": dep_output.get("final_synthesized_text_preview"),
                        "structured_data_keys": list(dep_output.get("final_structured_data", {}).keys()) if dep_output.get("final_structured_data") else []
                    }
        
        if not dependencies_met:
            node.status = IntentStatus.SKIPPED
            if node.node_level_provenance: 
                 node.node_level_provenance.complete("SKIPPED", {"reason": "Dependencies not met."})
            processed_node_outputs[node.node_id] = {
                "status": node.status.value, "node_id": node.node_id, 
                "error": "Skipped due to unmet dependencies." # ReasoningNode doesn't have error_message
            }
            return

        dynamic_parent_intent = None 
        if node.is_dynamic_parent_node:
            node_provenance.add_action(f"Node {node.node_id} is dynamic parent. Defining intent for sub-node identification.")
            dynamic_parent_intent_spec = self.intent_definer.define_intent_spec_via_llm(
                node=node, application_refs=application_refs, application_display_name=app_display_name,
                report_type=report_type, site_summary_context=app_context_summary.get("site_summary_placeholder"),
                proposal_summary_context=app_context_summary.get("proposal_summary_placeholder"),
                direct_dependency_outputs=direct_dependency_outputs_for_intent,
                node_provenance=node_provenance
            )
            if dynamic_parent_intent_spec:
                dynamic_parent_intent = Intent(**dynamic_parent_intent_spec)
                node.intents_issued.append(dynamic_parent_intent)
                if node_provenance: node_provenance.intent_id = dynamic_parent_intent.intent_id
                dynamic_parent_intent.provenance = node_provenance
                self.node_processor.process_intent(dynamic_parent_intent)

                if dynamic_parent_intent.status == IntentStatus.COMPLETED_SUCCESS and dynamic_parent_intent.structured_json_output:
                    # MODIFIED: Corrected multi-line condition
                    identified_sub_themes = (dynamic_parent_intent.structured_json_output.get("identified_material_considerations") or 
                                             dynamic_parent_intent.structured_json_output.get("identified_themes_for_assessment"))
                    
                    if isinstance(identified_sub_themes, list):
                        node_provenance.add_action(f"Dynamically identified {len(identified_sub_themes)} sub-themes.", {"themes": identified_sub_themes})
                        for theme_info in identified_sub_themes:
                            theme_name = theme_info.get("theme_name", str(theme_info)) if isinstance(theme_info, dict) else str(theme_info)
                            ontology_match_id = theme_info.get("ontology_match_id") if isinstance(theme_info, dict) else None
                            if not ontology_match_id and self.mc_ontology_manager: ontology_match_id = self.mc_ontology_manager.find_matching_consideration_id(theme_name)

                            sub_node_id_suffix = ontology_match_id if ontology_match_id else theme_name.replace(" ", "_").replace("/", "_")[:30]
                            sub_node_id = f"{node.node_id}/DYNAMIC_{sub_node_id_suffix}"
                            sub_node_description = f"Detailed Assessment: {theme_name} for {app_display_name}"
                            if ontology_match_id: sub_node_description = f"Detailed Assessment for {ontology_match_id}: {theme_name} ({app_display_name})"

                            dynamic_sub_node = ReasoningNode(node_id=sub_node_id, description=sub_node_description)
                            dynamic_sub_node.application_refs = application_refs
                            dynamic_sub_node.node_type_tag = "MaterialConsideration_DynamicItem"
                            dynamic_sub_node.linked_ontology_entry_id = ontology_match_id
                            
                            if ontology_match_id and self.mc_ontology_manager:
                                mc_details = self.mc_ontology_manager.get_consideration_details(ontology_match_id)
                                if mc_details:
                                    dynamic_sub_node.generic_material_considerations.extend(mc_details.get("primary_tags", []))
                                    dynamic_sub_node.specific_policy_focus_ids.extend(mc_details.get("relevant_policy_themes", []))
                                    dynamic_sub_node.key_evidence_document_types.extend(mc_details.get("key_evidence_docs", []))
                                    dynamic_sub_node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
                                    dynamic_sub_node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
                            else: dynamic_sub_node.generic_material_considerations.append(theme_name)
                            node.add_sub_node(dynamic_sub_node)
                            node_provenance.add_action(f"Created dynamic sub-node: {dynamic_sub_node.node_id} for '{theme_name}'. Ontology: {ontology_match_id}")
                    else: node_provenance.add_action(f"Dynamic parent '{node.node_id}' no structured sub-themes.", {"type": type(identified_sub_themes).__name__})
                else: node_provenance.add_action(f"Dynamic parent '{node.node_id}' intent failed. Status: {dynamic_parent_intent.status.value if dynamic_parent_intent else 'N/A'}", {"error": dynamic_parent_intent.error_message if dynamic_parent_intent and hasattr(dynamic_parent_intent, 'error_message') else 'Intent spec failed earlier or error message not available.'})
            else: node_provenance.add_action(f"Failed to define intent spec for dynamic parent {node.node_id}.")
            
            node.final_synthesized_text = dynamic_parent_intent.synthesized_text_output if dynamic_parent_intent else "Dynamic sub-node identification did not complete."
            node.final_structured_data = dynamic_parent_intent.structured_json_output if dynamic_parent_intent else {"error": "Dynamic sub-node identification failed."}
            node.status = dynamic_parent_intent.status if dynamic_parent_intent else IntentStatus.FAILED
            node.confidence_score = dynamic_parent_intent.confidence_score if dynamic_parent_intent else 0.1

        if node.sub_nodes:
            for sub_node_key, sub_node_obj in node.sub_nodes.items():
                self._process_node_and_children_recursively(
                    sub_node_obj, application_refs, app_display_name, report_type, 
                    app_context_summary, processed_node_outputs, clarification_attempt_counts
                )
        
        should_process_main_intent_for_this_node = True
        if node.is_dynamic_parent_node:
            if not (node.sub_nodes and node.node_type_tag and "Parent" in node.node_type_tag):
                should_process_main_intent_for_this_node = False
                node_provenance.add_action(f"Node {node.node_id} dynamic parent; child-finding done or not a typical parent. No summary intent needed.")


        current_intent = None 
        if should_process_main_intent_for_this_node:
            node_provenance.add_action(f"Defining main processing intent for node {node.node_id}.")
            child_outputs_for_intent = {}
            if node.sub_nodes: 
                for sk, sv_node in node.sub_nodes.items():
                    if sv_node.node_id in processed_node_outputs:
                        child_output = processed_node_outputs[sv_node.node_id]
                        child_outputs_for_intent[sv_node.node_id] = {
                            "node_id": sv_node.node_id, "description": sv_node.description,
                            "status": child_output.get("status"),
                            "text_summary_preview": child_output.get("final_synthesized_text_preview"),
                            "structured_data_keys": list(child_output.get("final_structured_data", {}).keys()) if child_output.get("final_structured_data") else [],
                            "confidence": child_output.get("confidence_score")
                        }
            context_from_prior_steps = {**direct_dependency_outputs_for_intent, **child_outputs_for_intent}

            current_intent_spec = self.intent_definer.define_intent_spec_via_llm(
                node=node, application_refs=application_refs, application_display_name=app_display_name,
                report_type=report_type, site_summary_context=app_context_summary.get("site_summary_placeholder"),
                proposal_summary_context=app_context_summary.get("proposal_summary_placeholder"),
                direct_dependency_outputs=context_from_prior_steps, 
                node_provenance=node_provenance
            )

            if current_intent_spec:
                current_intent = Intent(**current_intent_spec)
                node.intents_issued.append(current_intent)
                if node_provenance: node_provenance.intent_id = current_intent.intent_id
                current_intent.provenance = node_provenance
                current_intent.context_data_from_prior_steps = context_from_prior_steps
                self.node_processor.process_intent(current_intent)

                clarification_attempts = clarification_attempt_counts.get(node.node_id, 0)
                # MODIFIED: Corrected multi-line condition
                while (current_intent.status == IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED and 
                       clarification_attempts < self.MAX_CLARIFICATION_ATTEMPTS_PER_NODE):
                    clarification_attempts += 1
                    clarification_attempt_counts[node.node_id] = clarification_attempts
                    current_intent_error_message = current_intent.error_message if hasattr(current_intent, 'error_message') else "Clarification needed."
                    node_provenance.add_action(f"Clarification attempt {clarification_attempts}/{self.MAX_CLARIFICATION_ATTEMPTS_PER_NODE} for {node.node_id}.", {"reason": current_intent_error_message})


                    clarif_provenance = ProvenanceLog(current_intent.intent_id, f"Clarif Intent for Node {node.node_id}, Attempt {clarification_attempts}")
                    if node_provenance: clarif_provenance.add_action("Parent Node Log ID", {"id": str(node_provenance.log_id)})
                    self.overall_provenance_logs.append(clarif_provenance)

                    clarification_spec = self.intent_definer.define_clarification_intent_spec_via_llm(
                        original_intent=current_intent, clarification_reason=current_intent_error_message,
                        node_provenance=clarif_provenance
                    )
                    if clarification_spec:
                        clarification_intent = Intent(**clarification_spec)
                        node.intents_issued.append(clarification_intent)
                        if clarif_provenance: clarif_provenance.intent_id = clarification_intent.intent_id
                        clarification_intent.provenance = clarif_provenance
                        
                        clarification_intent.llm_policy_context_summary = getattr(current_intent, 'llm_policy_context_summary', [])
                        clarification_intent.full_documents_context = getattr(current_intent, 'full_documents_context', [])
                        clarification_intent.chunk_context = getattr(current_intent, 'chunk_context', [])
                        clarification_intent.context_data_from_prior_steps = getattr(current_intent, 'context_data_from_prior_steps', {})
                        
                        self.node_processor.process_intent(clarification_intent)
                        current_intent = clarification_intent 
                    else:
                        node_provenance.add_action("Failed to define clarification intent spec. Halting loop.")
                        current_intent.status = IntentStatus.FAILED
                        current_intent.error_message = (current_intent_error_message or "") + "; Clarification spec failed."
                        break 
                
                node.final_synthesized_text = current_intent.synthesized_text_output if current_intent else None
                node.final_structured_data = current_intent.structured_json_output if current_intent else None
                node.status = current_intent.status if current_intent else IntentStatus.FAILED
                node.confidence_score = current_intent.confidence_score if current_intent else 0.0
                if node_provenance: node_provenance.add_action(f"Node {node.node_id} main intent done. Status: {node.status.value if node.status else 'N/A'}, Conf: {node.confidence_score}")
            else:
                node.status = IntentStatus.FAILED
                # ReasoningNode does not have error_message, so we can't set it here.
                # Consider adding it to ReasoningNode or logging the error differently.
                if node_provenance: node_provenance.add_action(f"ERROR: Failed to define intent spec for {node.node_id}. FAILED.")
                node.confidence_score = 0.05
        
        if node.sub_nodes and not should_process_main_intent_for_this_node: 
             node.update_status_based_on_children_and_intents()
             if node_provenance: node_provenance.add_action(f"Node {node.node_id} status updated based on children/intents. New Status: {node.status.value if node.status else 'N/A'}")

        # MODIFIED: Use FAILED as fallback, as UNKNOWN is not in IntentStatus
        node_status_value = node.status.value if node.status and hasattr(node.status, 'value') else IntentStatus.FAILED.value
        # MODIFIED: ReasoningNode does not have error_message. Intent object has it.
        error_for_output = None
        if current_intent and current_intent.status == IntentStatus.FAILED:
            error_for_output = current_intent.error_message
        elif node.status == IntentStatus.FAILED and not current_intent : # If node failed before an intent was fully processed
            error_for_output = "Node processing failed before intent completion."

        processed_node_outputs[node.node_id] = {
            "status": node_status_value,
            "node_id": node.node_id,
            "final_synthesized_text_preview": (node.final_synthesized_text[:250] + "...") if node.final_synthesized_text else None,
            "final_structured_data": node.final_structured_data,
            "confidence_score": node.confidence_score,
            "error": error_for_output
        }
        if node_provenance: node_provenance.complete(node_status_value, {"final_confidence_orch": node.confidence_score, "output_keys": list(processed_node_outputs[node.node_id].keys())})


    def orchestrate_report_generation(self, report_type_key: str, application_refs: List[str], application_display_name: str) -> Dict[str, Any]:
        overall_orchestration_provenance = ProvenanceLog(None, f"MRM Orchestration Started for Report: {report_type_key}, App: {application_display_name}")
        self.overall_provenance_logs.append(overall_orchestration_provenance)
        start_time = time.time()
        overall_orchestration_provenance.add_action("Fetching report template and application context.")

        template = self.report_template_manager.get_template(report_type_key)
        if not template:
            err_msg = f"No report template for type: {report_type_key}"
            overall_orchestration_provenance.complete("FAILED", {"error": err_msg})
            print(f"ERROR: {err_msg}")
            raise ValueError(err_msg)

        app_context_summary = self._get_or_create_application_context_summary(application_refs, application_display_name)
        overall_orchestration_provenance.add_action("App context summary prepared.", {"summary_preview": str(app_context_summary)[:200]+"..."})

        root_reasoning_node = self._build_reasoning_tree_from_template(template, application_refs, application_display_name)
        overall_orchestration_provenance.add_action("Reasoning tree built.", {"root_id": root_reasoning_node.node_id, "children": len(root_reasoning_node.sub_nodes or {})})
        
        processed_node_outputs: Dict[str, Any] = {}
        clarification_attempt_counts: Dict[str, int] = {}

        if root_reasoning_node.sub_nodes: 
            for child_node_key, child_node_obj in root_reasoning_node.sub_nodes.items():
                self._process_node_and_children_recursively(
                    child_node_obj, 
                    application_refs, 
                    application_display_name, 
                    report_type_key, 
                    app_context_summary, 
                    processed_node_outputs, 
                    clarification_attempt_counts
                )
        
        root_reasoning_node.update_status_based_on_children_and_intents()
        overall_orchestration_provenance.add_action("All nodes processed. Root status updated.", {"root_status": root_reasoning_node.status.value if root_reasoning_node.status else 'N/A'})

        end_time = time.time()
        duration = end_time - start_time
        overall_orchestration_provenance.complete("COMPLETED_SUCCESS", {"duration_s": duration, "final_root_status": root_reasoning_node.status.value if root_reasoning_node.status else 'N/A'})
        
        # MODIFIED: Use __str__ for ProvenanceLog serialization as to_dict is not available
        # overall_provenance_log_dump = [str(log) for log in self.overall_provenance_logs]

        return {
            "report_type": report_type_key,
            "application_display_name": application_display_name,
            "application_refs": application_refs,
            "generation_duration_seconds": duration,
            "root_reasoning_node_dump": self._dump_node_to_dict(root_reasoning_node),
            "processed_node_outputs_summary": { 
                node_id: {
                    "status": data.get("status"), "confidence": data.get("confidence_score"), 
                    "error": data.get("error"), 
                    "text_preview": data.get("final_synthesized_text_preview")
                } for node_id, data in processed_node_outputs.items()
            },
            # "overall_provenance_log_dump": overall_provenance_log_dump # Optional
        }

    def _dump_node_to_dict(self, node: ReasoningNode) -> Dict[str, Any]:
        if not node:
            return {}
        
        dumped_sub_nodes = {}
        if node.sub_nodes: 
            for key, sub_node in node.sub_nodes.items():
                dumped_sub_nodes[key] = self._dump_node_to_dict(sub_node)

        dumped_intents_summary = []
        if node.intents_issued: 
            for intent_obj in node.intents_issued:
                if intent_obj: 
                    # MODIFIED: Use __str__ for Intent serialization as to_dict is not available
                    dumped_intents_summary.append(str(intent_obj)) 
                else:
                    dumped_intents_summary.append("NoneIntentInList")

        provenance_summary = None
        if node.node_level_provenance:
            # MODIFIED: Use __str__ for ProvenanceLog serialization as to_dict is not available
            provenance_summary = str(node.node_level_provenance)

        # ReasoningNode does not have error_message attribute.
        # The error related to a node's processing would typically be on the last Intent issued for it.
        node_error_message = None 
        if node.intents_issued and node.intents_issued[-1].status == IntentStatus.FAILED:
            node_error_message = node.intents_issued[-1].error_message
        elif node.status == IntentStatus.FAILED and not node.intents_issued: # If node failed early
             node_error_message = "Node processing failed before any intent was fully processed."

        return {
            "node_id": node.node_id,
            "description": node.description,
            "status": node.status.value if node.status and hasattr(node.status, 'value') else str(node.status),
            "node_type_tag": node.node_type_tag,
            "generic_material_considerations": node.generic_material_considerations or [],
            "specific_policy_focus_ids": node.specific_policy_focus_ids or [],
            "key_evidence_document_types": node.key_evidence_document_types or [],
            "linked_ontology_entry_id": node.linked_ontology_entry_id,
            "is_dynamic_parent_node": node.is_dynamic_parent_node,
            "agent_to_invoke_hint": node.agent_to_invoke_hint,
            "data_requirements_schema_hint": node.data_requirements_schema_hint,
            "depends_on_nodes": node.depends_on_nodes or [],
            "final_synthesized_text": node.final_synthesized_text,
            "final_structured_data": node.final_structured_data,
            "confidence_score": node.confidence_score,
            "error_message": node_error_message, 
            "application_refs": node.application_refs or [],
            "intents_issued_summary": dumped_intents_summary,
            "node_level_provenance_summary": provenance_summary,
            "sub_nodes": dumped_sub_nodes
        }

if __name__ == '__main__':
    print("MRM Orchestrator module loaded. Standalone execution would require mock setup.")
