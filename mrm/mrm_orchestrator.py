# mrm/mrm_orchestrator.py
# Modular Reasoning Machine (MRM) Orchestrator - V10 (Refactored)
# Main orchestration coordinator using modular components

import time
import asyncio
from typing import Dict, List, Any

# Core application components
from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog
from db_manager import DatabaseManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from knowledge_base.policy_manager import PolicyManager
from retrieval.retriever import AgenticRetriever
from mrm.intent_definer import IntentDefiner
from mrm.node_processor import NodeProcessor

# Modular components
from mrm.application_context_manager import ApplicationContextManager
from mrm.reasoning_tree_builder import ReasoningTreeBuilder
from mrm.dynamic_node_expander import DynamicNodeExpander
from mrm.parallel_processor import ParallelProcessor
from mrm.report_generator import ReportGenerator

from agents.visual_heritage_agent import VisualHeritageAgent
from agents.policy_analysis_agent import PolicyAnalysisAgent, DefaultPlanningAnalystAgent, LLMPlanningPolicyAnalyst
from agents.base_agent import BaseSubsidiaryAgent 

from config import GEMINI_API_KEY, MRM_MODEL_NAME, SUBSIDIARY_AGENT_MODEL_NAME, DB_CONFIG, REPORT_TEMPLATE_DIR, MC_ONTOLOGY_DIR, POLICY_KB_DIR, PARALLEL_ASYNC_LLM_MODE, MAX_CONCURRENT_LLM_CALLS

if not GEMINI_API_KEY:
    raise ValueError("CRITICAL: GEMINI_API_KEY not found. Please set it in your environment or .env file.")

class MRMOrchestrator:
    """
    Main MRM Orchestrator - Coordinates all modular components for report generation.
    
    This class acts as the main coordinator, delegating specific responsibilities
    to specialized modular components for better maintainability and testability.
    """
    MAX_CLARIFICATION_ATTEMPTS_PER_NODE = 2

    def __init__(self, db_manager: DatabaseManager,
                 report_template_manager: ReportTemplateManager,
                 mc_ontology_manager: MaterialConsiderationOntology,
                 policy_manager: PolicyManager):
        
        # Core dependencies
        self.db_manager = db_manager
        self.report_template_manager = report_template_manager
        self.mc_ontology_manager = mc_ontology_manager
        self.policy_manager = policy_manager
        
        print(f"INFO: MRMOrchestrator initializing with DB: {type(db_manager).__name__}, PolicyMgr: {type(policy_manager).__name__}")

        # Initialize retriever
        self.retriever = AgenticRetriever(self.db_manager)
        print(f"INFO: AgenticRetriever initialized with DB: {type(db_manager).__name__}")

        # Initialize subsidiary agents
        self.subsidiary_agents: Dict[str, BaseSubsidiaryAgent] = {
            "VisualHeritageAssessment_GeminiFlash_V1": VisualHeritageAgent(agent_name="VisualHeritageAssessment_GeminiFlash_V1"),
            "PolicyAnalysisAgent": PolicyAnalysisAgent(agent_name="PolicyAnalysisAgent"),
            "default_planning_analyst_agent": DefaultPlanningAnalystAgent(agent_name="default_planning_analyst_agent"),
            "LLM_PlanningPolicyAnalyst": LLMPlanningPolicyAnalyst(agent_name="LLM_PlanningPolicyAnalyst"),
        }
        print(f"INFO: Initialized {len(self.subsidiary_agents)} subsidiary agents: {list(self.subsidiary_agents.keys())}")

        # Initialize core processing components
        self.intent_definer = IntentDefiner(
            policy_manager=self.policy_manager,
            api_key=GEMINI_API_KEY
        )
        print(f"INFO: IntentDefiner initialized with PolicyManager: {type(policy_manager).__name__}")

        self.node_processor = NodeProcessor(
            api_key=GEMINI_API_KEY,
            retriever=self.retriever,
            subsidiary_agents=self.subsidiary_agents,
            policy_manager=self.policy_manager
        )
        print(f"INFO: NodeProcessor initialized with MRM Model: {MRM_MODEL_NAME}, Retriever, {len(self.subsidiary_agents)} agents, and PolicyManager.")

        # Initialize modular components
        self.context_manager = ApplicationContextManager(self.db_manager)
        self.tree_builder = ReasoningTreeBuilder(self.report_template_manager, self.mc_ontology_manager)
        self.dynamic_expander = DynamicNodeExpander(self.mc_ontology_manager, self.intent_definer, self.node_processor)
        self.parallel_processor = ParallelProcessor(PARALLEL_ASYNC_LLM_MODE, MAX_CONCURRENT_LLM_CALLS)
        self.report_generator = ReportGenerator()
        
        print(f"INFO: Modular components initialized:")
        print(f"  - ApplicationContextManager")
        print(f"  - ReasoningTreeBuilder") 
        print(f"  - DynamicNodeExpander")
        print(f"  - ParallelProcessor (Async LLM: {'ENABLED' if PARALLEL_ASYNC_LLM_MODE else 'DISABLED'})")
        print(f"  - ReportGenerator")

        # State management
        self.overall_provenance_logs: List[ProvenanceLog] = []

    def orchestrate_report_generation(self, 
                                     report_type_key: str, 
                                     application_refs: List[str], 
                                     application_display_name: str) -> Dict[str, Any]:
        """
        Synchronous report generation orchestration (original behavior).
        
        Args:
            report_type_key: Type of report template to use
            application_refs: List of application reference IDs
            application_display_name: Display name for the application
            
        Returns:
            Dictionary containing the final report
        """
        start_time = time.time()
        self.overall_provenance_logs = []
        
        prov = ProvenanceLog(
            None, 
            f"MRM Sync Report Generation: {application_display_name} ({report_type_key})"
        )
        self.overall_provenance_logs.append(prov)
        prov.add_action(f"Starting synchronous orchestration for {len(application_refs)} application refs")
        
        try:
            # Get application context using modular component
            app_context_summary = self.context_manager.get_or_create_application_context_summary(
                application_refs, application_display_name
            )
            
            # Build reasoning tree using modular component
            template = self.tree_builder.get_template(report_type_key)
            if not template:
                raise ValueError(f"Report template '{report_type_key}' not found")
            
            root_node = self.tree_builder.build_reasoning_tree_from_template(
                template, application_refs, application_display_name
            )
            
            # Expand dynamic parent nodes using modular component
            self.dynamic_expander.expand_all_dynamic_nodes(
                root_node, application_refs, application_display_name, 
                app_context_summary, report_type_key
            )
            
            # Process nodes sequentially (synchronous)
            processed_node_outputs = {}
            clarification_attempt_counts = {}
            
            # Get all nodes and process them in dependency order
            all_nodes = self.tree_builder.get_all_nodes_in_graph(root_node)
            max_iterations = 10
            
            for iteration in range(max_iterations):
                ready_nodes = self.parallel_processor.get_ready_nodes(all_nodes, processed_node_outputs)
                
                if not ready_nodes:
                    print(f"INFO: No more ready nodes. Orchestration complete after {iteration + 1} iterations.")
                    break
                
                print(f"INFO: Processing iteration {iteration + 1}: {len(ready_nodes)} nodes")
                
                # Process nodes sequentially
                for node in ready_nodes:
                    self._process_node_sync(
                        node, application_refs, application_display_name,
                        report_type_key, app_context_summary, 
                        processed_node_outputs, clarification_attempt_counts
                    )
                    
                    # Update processed outputs
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
            
            # Update final status
            root_node.update_status_based_on_children_and_intents()
            
            elapsed = time.time() - start_time
            prov.complete("SYNC_ORCHESTRATION_COMPLETE", {
                "total_elapsed_seconds": round(elapsed, 2),
                "final_root_status": root_node.status.value,
                "total_provenance_logs": len(self.overall_provenance_logs)
            })
            
            # Generate final report using modular component
            return self.report_generator.generate_sync_report_response(
                root_node, elapsed, self.overall_provenance_logs
            )
            
        except Exception as e:
            prov.complete("ERROR", {"error": str(e)})
            return self.report_generator.generate_error_response(e)

    def _process_node_sync(self, node: ReasoningNode, 
                          application_refs: List[str], 
                          app_display_name: str,
                          report_type: str, 
                          app_context_summary: Dict[str, Any],
                          processed_node_outputs: Dict[str, Any],
                          clarification_attempt_counts: Dict[str, int]):
        """Process a single node synchronously."""
        node_provenance = ProvenanceLog(None, f"MRM Synchronous Processing for Node: {node.node_id}")
        node.node_level_provenance = node_provenance
        self.overall_provenance_logs.append(node_provenance)
        node_provenance.add_action(f"Processing node: {node.node_id} (Type: {node.node_type_tag})")

        # Check dependencies
        dependencies_met = True
        direct_dependency_outputs_for_intent = {}
        if node.depends_on_nodes:
            node_provenance.add_action(f"Checking {len(node.depends_on_nodes)} dependencies: {node.depends_on_nodes}")
            for dep_id in node.depends_on_nodes:
                dep_output_data = processed_node_outputs.get(dep_id, {})
                dep_status_value = dep_output_data.get("status")

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
            return

        # Process regular node (non-dynamic parent)
        if not node.is_dynamic_parent_node:
            # Define intent for this node
            intent_spec = self.intent_definer.define_intent_spec_via_llm(
                node=node, 
                application_refs=application_refs, 
                application_display_name=app_display_name,
                report_type=report_type, 
                site_summary_context=app_context_summary.get("site_summary_placeholder"),
                proposal_summary_context=app_context_summary.get("proposal_summary_placeholder"),
                direct_dependency_outputs=direct_dependency_outputs_for_intent,
                node_provenance=node_provenance
            )
            
            if intent_spec:
                # Add required parameters
                intent_spec['parent_node_id'] = node.node_id
                intent_spec['application_refs'] = node.application_refs
                
                intent = Intent(**intent_spec)
                node.intents_issued.append(intent)
                if node_provenance: 
                    node_provenance.intent_id = intent.intent_id
                intent.provenance = node_provenance
                
                # Process the intent
                self.node_processor.process_intent(intent)
                
                # Update node with results
                if intent.status == IntentStatus.COMPLETED_SUCCESS:
                    node.final_synthesized_text = intent.synthesized_text_output
                    node.final_structured_data = intent.structured_json_output
                    node.confidence_score = intent.confidence_score
                    node.status = IntentStatus.COMPLETED_SUCCESS
                elif intent.status == IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED:
                    node.status = IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED
                    # Could implement clarification logic here
                else:
                    node.status = IntentStatus.FAILED
                    
                node_provenance.add_action(f"Node processing complete. Status: {node.status.value}")
            else:
                node.status = IntentStatus.FAILED
                node_provenance.add_action("Failed to generate intent spec for node")
        
        # Complete provenance
        if node.node_level_provenance:
            node.node_level_provenance.complete(node.status.value, {"confidence": node.confidence_score})

    async def generate_async_report(self, application_refs: List[str], 
                                  app_display_name: str,
                                  report_type: str = "Default_MajorHybrid",
                                  max_parallel_nodes: int = 5) -> Dict[str, Any]:
        """
        Main async entry point for generating reports with parallel processing.
        Uses modular components for better maintainability.
        
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
        prov.add_action(f"Parallel Async LLM Mode: {'ENABLED' if self.parallel_processor.parallel_async_llm_mode else 'DISABLED'}")
        if self.parallel_processor.parallel_async_llm_mode:
            prov.add_action(f"Max Concurrent LLM Calls: {self.parallel_processor.max_concurrent_llm_calls}")
        
        try:
            # Get application context using modular component
            app_context_summary = self.context_manager.get_or_create_application_context_summary(
                application_refs, app_display_name
            )
            
            # Build reasoning tree using modular component
            template = self.tree_builder.get_template(report_type)
            if not template:
                raise ValueError(f"Report template '{report_type}' not found")
            
            root_node = self.tree_builder.build_reasoning_tree_from_template(
                template, application_refs, app_display_name
            )
            
            # Expand dynamic parent nodes using modular component
            await self._expand_dynamic_nodes_async(
                root_node, application_refs, app_display_name, 
                app_context_summary, report_type
            )
            
            # Process nodes with parallel execution using modular component
            processed_node_outputs = await self.parallel_processor.run_orchestration_loop(
                all_nodes_func=lambda: self.tree_builder.get_all_nodes_in_graph(root_node),
                process_func=self._process_node_async_wrapper,
                max_parallel_nodes=max_parallel_nodes,
                application_refs=application_refs,
                app_display_name=app_display_name,
                report_type=report_type,
                app_context_summary=app_context_summary,
                clarification_attempt_counts={}
            )
            
            # Update final status
            root_node.update_status_based_on_children_and_intents()
            
            elapsed = time.time() - start_time
            prov.complete("ASYNC_ORCHESTRATION_COMPLETE", {
                "total_elapsed_seconds": round(elapsed, 2),
                "final_root_status": root_node.status.value,
                "total_provenance_logs": len(self.overall_provenance_logs),
                "max_parallel_nodes": max_parallel_nodes
            })
            
            # Generate final report using modular component
            processing_metadata = {
                "parallel_processing": True,
                "max_parallel_nodes": max_parallel_nodes,
                **self.parallel_processor.get_processing_stats()
            }
            
            return self.report_generator.generate_async_report_response(
                root_node, elapsed, self.overall_provenance_logs, processing_metadata
            )
            
        except Exception as e:
            prov.complete("ERROR", {"error": str(e)})
            processing_metadata = {
                "parallel_processing": True,
                "max_parallel_nodes": max_parallel_nodes,
                **self.parallel_processor.get_processing_stats()
            }
            return self.report_generator.generate_error_response(e, processing_metadata)

    async def _expand_dynamic_nodes_async(self, 
                                        root_node: ReasoningNode, 
                                        application_refs: List[str], 
                                        app_display_name: str, 
                                        app_context_summary: Dict[str, Any],
                                        report_type: str):
        """Expand dynamic nodes with async support."""
        dynamic_parents = self.dynamic_expander.expand_all_dynamic_nodes(
            root_node, application_refs, app_display_name, 
            app_context_summary, report_type
        )
        print(f"INFO: Expanded {len(dynamic_parents)} dynamic parent nodes")

    def _process_node_async_wrapper(self, 
                                   node: ReasoningNode,
                                   processed_node_outputs: Dict[str, Any],
                                   application_refs: List[str],
                                   app_display_name: str,
                                   report_type: str,
                                   app_context_summary: Dict[str, Any],
                                   clarification_attempt_counts: Dict[str, int]):
        """Wrapper for async node processing that maintains the same interface."""
        self._process_node_sync(
            node, application_refs, app_display_name,
            report_type, app_context_summary, 
            processed_node_outputs, clarification_attempt_counts
        )

    # Legacy methods removed - functionality moved to modular components:
    # - _process_node_and_children_recursively -> moved to ParallelProcessor and _process_node_sync
    # - _async_llm_call_with_semaphore -> moved to ParallelProcessor
    # - _process_node_async -> moved to ParallelProcessor
    # - _process_nodes_parallel -> moved to ParallelProcessor
    # - _get_all_nodes_in_graph -> moved to ReasoningTreeBuilder
    # - _get_ready_nodes -> moved to ParallelProcessor
    # - _generate_final_report_text -> moved to ReportGenerator
    # - _dynamically_expand_mc_node -> moved to DynamicNodeExpander
    # - duplicate generate_async_report -> replaced with modular version


