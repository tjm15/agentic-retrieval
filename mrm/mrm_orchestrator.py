# mrm/mrm_orchestrator.py
# Modular Reasoning Machine (MRM) Orchestrator - V9
# Integrates IntentDefiner, NodeProcessor, and all knowledge base managers.

import json
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from google import genai
from typing import Dict, List, Optional, Any, Set, Tuple

# Core application components
from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog
from db_manager import DatabaseManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from knowledge_base.policy_manager import PolicyManager
from retrieval.retriever import AgenticRetriever
from mrm.intent_definer import IntentDefiner
from mrm.node_processor import NodeProcessor

from agents.visual_heritage_agent import VisualHeritageAgent # MODIFIED: Corrected class name
from agents.policy_analysis_agent import PolicyAnalysisAgent, DefaultPlanningAnalystAgent, LLMPlanningPolicyAnalyst
from agents.base_agent import BaseSubsidiaryAgent 

from config import GEMINI_API_KEY, MRM_MODEL_NAME, SUBSIDIARY_AGENT_MODEL_NAME, DB_CONFIG, REPORT_TEMPLATE_DIR, MC_ONTOLOGY_DIR, POLICY_KB_DIR, PARALLEL_ASYNC_LLM_MODE, MAX_CONCURRENT_LLM_CALLS

if not GEMINI_API_KEY:
    raise ValueError("CRITICAL: GEMINI_API_KEY not found. Please set it in your environment or .env file.")
# Assuming genai.configure is the correct way to set the API key for the version of the library used.
# If not, this might need to be genai.API_KEY = GEMINI_API_KEY or similar.
# genai.configure(api_key=GEMINI_API_KEY) # REMOVED: API key is typically handled by GOOGLE_API_KEY env var

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
            "VisualHeritageAssessment_GeminiFlash_V1": VisualHeritageAgent(agent_name="VisualHeritageAssessment_GeminiFlash_V1"),
            "PolicyAnalysisAgent": PolicyAnalysisAgent(agent_name="PolicyAnalysisAgent"),
            "default_planning_analyst_agent": DefaultPlanningAnalystAgent(agent_name="default_planning_analyst_agent"),
            "LLM_PlanningPolicyAnalyst": LLMPlanningPolicyAnalyst(agent_name="LLM_PlanningPolicyAnalyst"),
        }
        print(f"INFO: Initialized {len(self.subsidiary_agents)} subsidiary agents: {list(self.subsidiary_agents.keys())}")

        self.intent_definer = IntentDefiner(
            policy_manager=self.policy_manager,
            api_key=GEMINI_API_KEY
        )
        print(f"INFO: IntentDefiner initialized with PolicyManager: {type(policy_manager).__name__}")

        # Instantiate NodeProcessor and agents with correct config usage
        self.node_processor = NodeProcessor(
            api_key=GEMINI_API_KEY,
            retriever=self.retriever,
            subsidiary_agents=self.subsidiary_agents,
            policy_manager=self.policy_manager
        )
        print(f"INFO: NodeProcessor initialized with MRM Model: {MRM_MODEL_NAME}, Retriever, {len(self.subsidiary_agents)} agents, and PolicyManager.")

        self.application_context_cache: Dict[str, Dict[str, Any]] = {}
        self.overall_provenance_logs: List[ProvenanceLog] = []
        
        # Configure parallel async LLM mode
        self.parallel_async_llm_mode = PARALLEL_ASYNC_LLM_MODE
        self.max_concurrent_llm_calls = MAX_CONCURRENT_LLM_CALLS
        self._llm_semaphore = asyncio.Semaphore(self.max_concurrent_llm_calls) if self.parallel_async_llm_mode else None
        
        print(f"INFO: Parallel Async LLM Mode: {'ENABLED' if self.parallel_async_llm_mode else 'DISABLED'}")
        if self.parallel_async_llm_mode:
            print(f"INFO: Max Concurrent LLM Calls: {self.max_concurrent_llm_calls}")

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
            node.thematic_policy_descriptors = section_data.get("thematic_policy_descriptors", [])
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
                            
                            if not ontology_match_id and self.mc_ontology_manager:
                                ontology_match_id = self.mc_ontology_manager.find_matching_consideration_id(theme_name)

                            sub_node_id_suffix = (ontology_match_id if ontology_match_id 
                                                 else theme_name.replace(" ", "_").replace("/", "_")[:30])
                            sub_node_id = f"{node.node_id}/DYNAMIC_{sub_node_id_suffix}"
                            sub_node_description = f"Detailed Assessment: {theme_name} for {app_display_name}"
                            
                            if ontology_match_id:
                                sub_node_description = f"Detailed Assessment for {ontology_match_id}: {theme_name} ({app_display_name})"

                            dynamic_sub_node = ReasoningNode(
                                node_id=sub_node_id, 
                                description=sub_node_description
                            )
                            dynamic_sub_node.application_refs = application_refs
                            dynamic_sub_node.node_type_tag = "MaterialConsideration_DynamicItem"
                            dynamic_sub_node.linked_ontology_entry_id = ontology_match_id
                            
                            if ontology_match_id and self.mc_ontology_manager:
                                mc_details = self.mc_ontology_manager.get_consideration_details(ontology_match_id)
                                if mc_details:
                                    dynamic_sub_node.generic_material_considerations.extend(
                                        mc_details.get("primary_tags", [])
                                    )
                                    dynamic_sub_node.specific_policy_focus_ids.extend(
                                        mc_details.get("relevant_policy_themes", [])
                                    )
                                    dynamic_sub_node.key_evidence_document_types.extend(
                                        mc_details.get("key_evidence_docs", [])
                                    )
                                    dynamic_sub_node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
                                    dynamic_sub_node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
                            else:
                                dynamic_sub_node.generic_material_considerations.append(theme_name)
                            
                            node.add_sub_node(dynamic_sub_node)
                            node_provenance.add_action(
                                f"Created dynamic sub-node: {dynamic_sub_node.node_id} for '{theme_name}'. Ontology: {ontology_match_id}"
                            )
                    else:
                        node_provenance.add_action(
                            f"Dynamic parent '{node.node_id}' no structured sub-themes.", 
                            {"type": type(identified_sub_themes).__name__}
                        )
                else:
                    error_msg = (dynamic_parent_intent.error_message 
                               if dynamic_parent_intent and hasattr(dynamic_parent_intent, 'error_message') 
                               else 'Intent spec failed earlier or error message not available.')
                    node_provenance.add_action(
                        f"Dynamic parent '{node.node_id}' intent failed. Status: {dynamic_parent_intent.status.value if dynamic_parent_intent else 'N/A'}", 
                        {"error": error_msg}
                    )
            else:
                node_provenance.add_action(f"Failed to define intent spec for dynamic parent {node.node_id}.")

    async def _async_llm_call_with_semaphore(self, llm_callable, *args, **kwargs):
        """
        Execute an LLM call with semaphore control for parallel async mode.
        
        Args:
            llm_callable: The callable that makes the LLM call
            *args, **kwargs: Arguments to pass to the callable
            
        Returns:
            The result of the LLM call
        """
        if not self.parallel_async_llm_mode or not self._llm_semaphore:
            # Run synchronously if parallel async mode is disabled
            return llm_callable(*args, **kwargs)
        
        # Use semaphore to limit concurrent LLM calls
        async with self._llm_semaphore:
            # Run the LLM call in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, llm_callable, *args, **kwargs)

    async def _process_node_async(self, node: ReasoningNode,
                                application_refs: List[str],
                                app_display_name: str,
                                report_type: str,
                                app_context_summary: Dict[str, Any],
                                processed_node_outputs: Dict[str, Any],
                                clarification_attempt_counts: Dict[str, int]):
        """
        Async version of node processing with LLM calls wrapped in asyncio.
        """
        if self.parallel_async_llm_mode:
            # Use async LLM processing with semaphore control
            await self._async_llm_call_with_semaphore(
                self._process_node_and_children_recursively,
                node,
                application_refs,
                app_display_name,
                report_type,
                app_context_summary,
                processed_node_outputs,
                clarification_attempt_counts
            )
        else:
            # Run synchronously in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    self._process_node_and_children_recursively,
                    node,
                    application_refs,
                    app_display_name,
                    report_type,
                    app_context_summary,
                    processed_node_outputs,
                    clarification_attempt_counts
                )
        
        # Store the result in processed_outputs
        processed_node_outputs[node.node_id] = {
            "status": node.status.value,
            "node_id": node.node_id,
            "final_synthesized_text_preview": (
                node.final_synthesized_text[:200] + "..." 
                if node.final_synthesized_text and len(node.final_synthesized_text) > 200 
                else node.final_synthesized_text
            ),
            "final_structured_data": node.final_structured_data,
            "confidence_score": node.confidence_score
        }

    async def _process_nodes_parallel(self, nodes: List[ReasoningNode],
                                    application_refs: List[str],
                                    app_display_name: str,
                                    report_type: str,
                                    app_context_summary: Dict[str, Any],
                                    processed_node_outputs: Dict[str, Any],
                                    clarification_attempt_counts: Dict[str, int]):
        """
        Process multiple nodes concurrently with optional parallel async LLM mode.
        """
        tasks = []
        for node in nodes:
            task = self._process_node_async(
                node,
                application_refs,
                app_display_name,
                report_type,
                app_context_summary,
                processed_node_outputs,
                clarification_attempt_counts
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

    async def generate_async_report(self, application_refs: List[str], 
                                  app_display_name: str,
                                  report_type: str = "Default_MajorHybrid",
                                  max_parallel_nodes: int = 5) -> Dict[str, Any]:
        """
        Main async entry point for generating reports with parallel processing.
        Supports both parallel node processing and parallel async LLM mode.
        
        Args:
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            report_type: Type of report template to use
            max_parallel_nodes: Maximum number of nodes to process concurrently
            
        Returns:
            Dictionary containing the final report and metadata
        """
        start_time = time.time()
        self.overall_provenance_logs = []
        
        prov = ProvenanceLog(
            None, 
            f"MRM Async Report Generation: {app_display_name} ({report_type})"
        )
        self.overall_provenance_logs.append(prov)
        prov.add_action(f"Starting async orchestration for {len(application_refs)} application refs")
        prov.add_action(f"Parallel Async LLM Mode: {'ENABLED' if self.parallel_async_llm_mode else 'DISABLED'}")
        if self.parallel_async_llm_mode:
            prov.add_action(f"Max Concurrent LLM Calls: {self.max_concurrent_llm_calls}")
        
        try:
            # Get application context
            app_context_summary = self._get_or_create_application_context_summary(
                application_refs, app_display_name
            )
            
            # Build reasoning tree
            template = self.report_template_manager.get_template(report_type)
            if not template:
                raise ValueError(f"Report template '{report_type}' not found")
            
            root_node = self._build_reasoning_tree_from_template(
                template, application_refs, app_display_name
            )
            
            # Expand dynamic parent nodes
            all_nodes = self._get_all_nodes_in_graph(root_node)
            dynamic_parents = [node for node in all_nodes if node.is_dynamic_parent_node]
            
            for parent_node in dynamic_parents:
                print(f"INFO: Expanding dynamic parent node: {parent_node.node_id}")
                if self.parallel_async_llm_mode:
                    await self._async_llm_call_with_semaphore(
                        self._dynamically_expand_mc_node,
                        parent_node,
                        application_refs,
                        app_display_name,
                        app_context_summary
                    )
                else:
                    self._dynamically_expand_mc_node(
                        parent_node, application_refs, app_display_name, app_context_summary
                    )
            
            # Process nodes with parallel execution
            processed_node_outputs = {}
            clarification_attempt_counts = {}
            max_iterations = 10
            
            for iteration in range(max_iterations):
                all_nodes = self._get_all_nodes_in_graph(root_node)
                ready_nodes = self._get_ready_nodes(all_nodes, processed_node_outputs)
                
                if not ready_nodes:
                    break
                
                # Limit the number of nodes processed in parallel
                batch_size = min(len(ready_nodes), max_parallel_nodes)
                current_batch = ready_nodes[:batch_size]
                
                print(f"INFO: Processing batch {iteration + 1}: {len(current_batch)} nodes")
                
                await self._process_nodes_parallel(
                    current_batch,
                    application_refs,
                    app_display_name,
                    report_type,
                    app_context_summary,
                    processed_node_outputs,
                    clarification_attempt_counts
                )
            
            # Update final status
            root_node.update_status_based_on_children_and_intents()
            
            elapsed = time.time() - start_time
            prov.complete("ASYNC_ORCHESTRATION_COMPLETE", {
                "total_elapsed_seconds": round(elapsed, 2),
                "final_root_status": root_node.status.value,
                "total_provenance_logs": len(self.overall_provenance_logs),
                "max_parallel_nodes": max_parallel_nodes,
                "parallel_async_llm_mode": self.parallel_async_llm_mode,
                "max_concurrent_llm_calls": self.max_concurrent_llm_calls if self.parallel_async_llm_mode else None
            })
            
            # Generate final report
            final_report_text = self._generate_final_report_text(root_node)
            
            return {
                "status": "success",
                "reasoning_tree": root_node,
                "final_report_text": final_report_text,
                "report_metadata": {
                    "total_nodes": len(self._get_all_nodes_in_graph(root_node)),
                    "provenance_logs": len(self.overall_provenance_logs),
                    "parallel_processing": True,
                    "max_parallel_nodes": max_parallel_nodes,
                    "parallel_async_llm_mode": self.parallel_async_llm_mode,
                    "max_concurrent_llm_calls": self.max_concurrent_llm_calls if self.parallel_async_llm_mode else None,
                    "total_elapsed_seconds": round(elapsed, 2)
                }
            }
            
        except Exception as e:
            prov.complete("ERROR", {"error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "report_metadata": {
                    "parallel_processing": True,
                    "max_parallel_nodes": max_parallel_nodes,
                    "parallel_async_llm_mode": self.parallel_async_llm_mode
                }
            }

    def _get_all_nodes_in_graph(self, root_node: ReasoningNode) -> List[ReasoningNode]:
        """Get all nodes in the reasoning graph."""
        all_nodes = [root_node]
        for sub_node in root_node.sub_nodes.values():
            all_nodes.extend(self._get_all_nodes_in_graph(sub_node))
        return all_nodes

    def _get_ready_nodes(self, all_nodes: List[ReasoningNode], processed_outputs: Dict[str, Any]) -> List[ReasoningNode]:
        """Get nodes that are ready for processing (dependencies met)."""
        ready_nodes = []
        
        for node in all_nodes:
            # Skip if already processed
            if node.node_id in processed_outputs:
                continue
                
            # Skip if currently in progress or failed
            if node.status in [IntentStatus.IN_PROGRESS, IntentStatus.FAILED]:
                continue
                
            # Check if dependencies are met
            dependencies_met = True
            if node.depends_on_nodes:
                for dep_id in node.depends_on_nodes:
                    if dep_id not in processed_outputs:
                        dependencies_met = False
                        break
                    dep_status = processed_outputs[dep_id].get("status")
                    if dep_status not in [IntentStatus.COMPLETED_SUCCESS.value, 
                                        IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED.value]:
                        dependencies_met = False
                        break
            
            if dependencies_met:
                ready_nodes.append(node)
        
        return ready_nodes

    def _generate_final_report_text(self, root_node: ReasoningNode) -> str:
        """Generate the final report text from the processed reasoning tree."""
        def format_node_recursive(node: ReasoningNode, indent_level: int = 0) -> str:
            indent = "  " * indent_level
            result = f"{indent}# {node.node_id}\n"
            result += f"{indent}{node.description}\n"
            
            if node.status:
                result += f"{indent}Status: {node.status.value}\n"
            
            if node.confidence_score is not None:
                result += f"{indent}Confidence: {node.confidence_score:.2f}\n"
            
            if node.final_synthesized_text:
                result += f"{indent}Content:\n{node.final_synthesized_text}\n"
            
            result += "\n"
            
            # Process sub-nodes
            for sub_node in node.sub_nodes.values():
                result += format_node_recursive(sub_node, indent_level + 1)
            
            return result
        
        report_text = "# Planning Assessment Report\n\n"
        report_text += format_node_recursive(root_node)
        
        return report_text

    def _dynamically_expand_mc_node(self, parent_node: ReasoningNode, 
                                   application_refs: List[str], 
                                   app_display_name: str, 
                                   app_context_summary: Dict[str, Any]):
        """
        Dynamically expand a material consideration parent node by creating child nodes
        based on application-specific material considerations identified via LLM scanning.
        
        Args:
            parent_node: The dynamic parent node to expand
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            app_context_summary: Application context summary
        """
        if not parent_node.is_dynamic_parent_node:
            print(f"WARN: Node {parent_node.node_id} is not marked as dynamic parent")
            return
            
        print(f"INFO: Dynamically expanding material consideration node: {parent_node.node_id}")
        
        # Create an intent to identify application-specific material considerations
        dynamic_provenance = ProvenanceLog(None, f"Dynamic expansion for node: {parent_node.node_id}")
        dynamic_parent_intent_spec = self.intent_definer.define_intent_spec_via_llm(
            node=parent_node, 
            application_refs=application_refs, 
            application_display_name=app_display_name,
            report_type="Default_MajorHybrid",  # TODO: Pass actual report type
            site_summary_context=app_context_summary.get("site_summary_placeholder"),
            proposal_summary_context=app_context_summary.get("proposal_summary_placeholder"),
            direct_dependency_outputs={},
            node_provenance=dynamic_provenance
        )
        
        if not dynamic_parent_intent_spec:
            print(f"WARN: Failed to generate intent spec for dynamic parent {parent_node.node_id}")
            return
            
        # Add required parameters that are missing from LLM-generated spec
        dynamic_parent_intent_spec['parent_node_id'] = parent_node.node_id
        dynamic_parent_intent_spec['application_refs'] = parent_node.application_refs
            
        # Create and process the intent
        dynamic_parent_intent = Intent(**dynamic_parent_intent_spec)
        parent_node.intents_issued.append(dynamic_parent_intent)
        
        # Process the intent to identify material considerations
        self.node_processor.process_intent(dynamic_parent_intent)
        
        if (dynamic_parent_intent.status == IntentStatus.COMPLETED_SUCCESS and 
            dynamic_parent_intent.structured_json_output):
            
            # Extract identified themes/material considerations
            identified_sub_themes = (
                dynamic_parent_intent.structured_json_output.get("identified_material_considerations") or 
                dynamic_parent_intent.structured_json_output.get("identified_themes_for_assessment")
            )
            
            if isinstance(identified_sub_themes, list):
                print(f"INFO: Dynamically identified {len(identified_sub_themes)} sub-themes for {parent_node.node_id}")
                
                # Create child nodes for each identified theme
                for theme_info in identified_sub_themes:
                    theme_name = (theme_info.get("theme_name", str(theme_info)) 
                                if isinstance(theme_info, dict) else str(theme_info))
                    ontology_match_id = (theme_info.get("ontology_match_id") 
                                       if isinstance(theme_info, dict) else None)
                    
                    # Try to find ontology match if not provided
                    if not ontology_match_id and self.mc_ontology_manager:
                        ontology_match_id = self.mc_ontology_manager.find_matching_consideration_id(theme_name)

                    # Create unique sub-node ID
                    sub_node_id_suffix = (ontology_match_id if ontology_match_id 
                                         else theme_name.replace(" ", "_").replace("/", "_")[:30])
                    sub_node_id = f"{parent_node.node_id}/DYNAMIC_{sub_node_id_suffix}"
                    sub_node_description = f"Detailed Assessment: {theme_name} for {app_display_name}"
                    
                    if ontology_match_id:
                        sub_node_description = f"Detailed Assessment for {ontology_match_id}: {theme_name} ({app_display_name})"

                    # Create the dynamic sub-node
                    dynamic_sub_node = ReasoningNode(
                        node_id=sub_node_id, 
                        description=sub_node_description
                    )
                    dynamic_sub_node.application_refs = application_refs
                    dynamic_sub_node.node_type_tag = "MaterialConsideration_DynamicItem"
                    dynamic_sub_node.linked_ontology_entry_id = ontology_match_id
                    
                    # Populate with ontology details if available
                    if ontology_match_id and self.mc_ontology_manager:
                        mc_details = self.mc_ontology_manager.get_consideration_details(ontology_match_id)
                        if mc_details:
                            dynamic_sub_node.generic_material_considerations.extend(
                                mc_details.get("primary_tags", [])
                            )
                            dynamic_sub_node.specific_policy_focus_ids.extend(
                                mc_details.get("relevant_policy_themes", [])
                            )
                            dynamic_sub_node.key_evidence_document_types.extend(
                                mc_details.get("key_evidence_docs", [])
                            )
                            dynamic_sub_node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
                            dynamic_sub_node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
                    else:
                        # Fallback if no ontology match
                        dynamic_sub_node.generic_material_considerations.append(theme_name)
                    
                    # Add the sub-node to the parent
                    parent_node.add_sub_node(dynamic_sub_node)
                    print(f"INFO: Created dynamic sub-node: {dynamic_sub_node.node_id} for '{theme_name}'. Ontology: {ontology_match_id}")
            else:
                print(f"WARN: Dynamic parent '{parent_node.node_id}' did not return structured sub-themes. Type: {type(identified_sub_themes).__name__}")
        else:
            error_msg = (dynamic_parent_intent.error_message 
                       if hasattr(dynamic_parent_intent, 'error_message') 
                       else 'Intent processing failed')
            print(f"WARN: Dynamic parent '{parent_node.node_id}' intent failed. Status: {dynamic_parent_intent.status.value}. Error: {error_msg}")
