# mrm/dynamic_node_expander.py
"""
Dynamic Node Expander for MRM Orchestrator
Handles dynamic material consideration expansion
"""

import traceback

from typing import Dict, List, Any

from core_types import ReasoningNode, Intent, IntentStatus, ProvenanceLog
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from mrm.intent_definer import IntentDefiner
from mrm.node_processor import NodeProcessor


class DynamicNodeExpander:
    """Handles dynamic expansion of material consideration nodes."""
    
    def __init__(self, 
                 mc_ontology_manager: MaterialConsiderationOntology,
                 intent_definer: IntentDefiner,
                 node_processor: NodeProcessor):
        self.mc_ontology_manager = mc_ontology_manager
        self.intent_definer = intent_definer
        self.node_processor = node_processor
    
    def expand_dynamic_node(self, 
                           parent_node: ReasoningNode, 
                           application_refs: List[str], 
                           app_display_name: str, 
                           app_context_summary: Dict[str, Any] | None,
                           report_type: str = "Default_MajorHybrid") -> bool:
        """
        Dynamically expand a material consideration parent node by creating child nodes
        based on application-specific material considerations identified via LLM scanning.
        
        Args:
            parent_node: The dynamic parent node to expand
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            app_context_summary: Application context summary
            report_type: Type of report being generated
            
        Returns:
            True if expansion was successful, False otherwise
        """
        if not parent_node.is_dynamic_parent_node:
            print(f"WARN: Node {parent_node.node_id} is not marked as dynamic parent")
            return False
            
        print(f"INFO: Dynamically expanding material consideration node: {parent_node.node_id}")
        
        # Create an intent to identify application-specific material considerations
        dynamic_provenance = ProvenanceLog(None, f"Dynamic expansion for node: {parent_node.node_id}")
        
        try:
            dynamic_parent_intent_spec = self.intent_definer.define_intent_spec_via_llm(
                node=parent_node, 
                application_refs=application_refs, 
                application_display_name=app_display_name,
                report_type=report_type,
                site_summary_context=app_context_summary.get("site_summary_placeholder", "") if app_context_summary else "",
                proposal_summary_context=app_context_summary.get("proposal_summary_placeholder", "") if app_context_summary else "",
                direct_dependency_outputs={},
                node_provenance=dynamic_provenance
            )
            
            if not dynamic_parent_intent_spec:
                print(f"WARN: Failed to generate intent spec for dynamic parent {parent_node.node_id}")
                return False
                
            # Add required parameters that might be missing from LLM-generated spec
            if 'parent_node_id' not in dynamic_parent_intent_spec:
                dynamic_parent_intent_spec['parent_node_id'] = parent_node.node_id
            if 'application_refs' not in dynamic_parent_intent_spec:
                dynamic_parent_intent_spec['application_refs'] = application_refs
                
            # Create and process the intent
            dynamic_parent_intent = Intent(**dynamic_parent_intent_spec)
            parent_node.intents_issued.append(dynamic_parent_intent)
            
            # Process the intent to identify material considerations
            self.node_processor.process_intent(dynamic_parent_intent)
            
            if (dynamic_parent_intent.status == IntentStatus.COMPLETED_SUCCESS and 
                dynamic_parent_intent.structured_json_output):
                
                return self._create_dynamic_sub_nodes(
                    parent_node, 
                    dynamic_parent_intent, 
                    application_refs, 
                    app_display_name,
                    report_type
                )
            else:
                error_msg = (getattr(dynamic_parent_intent, 'error_message', None) or 'Intent processing failed')
                print(f"WARN: Dynamic parent '{parent_node.node_id}' intent failed. Status: {dynamic_parent_intent.status.value}. Error: {error_msg}")
                return False
                
        except Exception as e:
            print(f"ERROR: Exception during dynamic expansion of {parent_node.node_id}: {e}")
            traceback.print_exc()
            return False
    
    def _create_dynamic_sub_nodes(self, 
                                 parent_node: ReasoningNode, 
                                 dynamic_parent_intent: Intent, 
                                 application_refs: List[str], 
                                 app_display_name: str,
                                 report_type: str = "MajorHybrid") -> bool:
        """Create dynamic sub-nodes based on identified material considerations."""
        # Extract identified themes/material considerations
        structured_output = dynamic_parent_intent.structured_json_output
        if not structured_output:
            print(f"WARN: Dynamic parent '{parent_node.node_id}' has no structured output")
            return False
            
        identified_sub_themes = (
            structured_output.get("identified_material_considerations") or 
            structured_output.get("identified_themes_for_assessment", [])
        )
        
        if not isinstance(identified_sub_themes, list):
            print(f"WARN: Dynamic parent '{parent_node.node_id}' did not return structured sub-themes. Type: {type(identified_sub_themes).__name__}")
            return False
        
        if not identified_sub_themes:
            print(f"WARN: No sub-themes identified for dynamic parent '{parent_node.node_id}'. Using fallback defaults.")
            # Fallback: Use default material considerations for this report type
            return self._create_fallback_sub_nodes(parent_node, application_refs, app_display_name, report_type)
        
        print(f"INFO: Dynamically identified {len(identified_sub_themes)} sub-themes for {parent_node.node_id}")
        
        # Create child nodes for each identified theme
        for theme_info in identified_sub_themes:
            self._create_single_dynamic_sub_node(
                parent_node, 
                theme_info, 
                application_refs, 
                app_display_name
            )
        
        return True
    
    def _create_fallback_sub_nodes(self, 
                                  parent_node: ReasoningNode, 
                                  application_refs: List[str], 
                                  app_display_name: str,
                                  report_type: str = "MajorHybrid") -> bool:
        """Create fallback sub-nodes using default material considerations when LLM scan returns empty."""
        print(f"INFO: Creating fallback sub-nodes for {parent_node.node_id}")
        
        # Extract report type from parent node context if available
        report_type = getattr(parent_node, 'report_type', 'MajorHybrid')
        
        # Get default material considerations for this report type
        try:
            default_considerations = self.mc_ontology_manager.get_default_considerations_for_report_type(report_type)
            
            if not default_considerations:
                print(f"WARN: No default considerations found for report type '{report_type}'. Using generic fallback.")
                default_considerations = self.mc_ontology_manager.get_default_considerations_for_report_type('Generic')
            
            if not default_considerations:
                print(f"ERROR: No fallback considerations available. Cannot create sub-nodes.")
                return False
                
            print(f"INFO: Using {len(default_considerations)} default considerations as fallback")
            
            # Create sub-nodes for each default consideration
            for consideration_id in default_considerations:
                try:
                    # Get consideration details from ontology
                    consideration_details = self.mc_ontology_manager.get_consideration_details(consideration_id)
                    if consideration_details:
                        theme_name = consideration_details.get('title', consideration_id)
                        
                        # Create theme info in the same format as LLM output
                        theme_info = {
                            "theme_name": theme_name,
                            "ontology_match_id": consideration_id
                        }
                        
                        self._create_single_dynamic_sub_node(
                            parent_node, 
                            theme_info, 
                            application_refs, 
                            app_display_name
                        )
                    else:
                        print(f"WARN: Could not get details for consideration {consideration_id}")
                        
                except Exception as e:
                    print(f"WARN: Failed to create fallback sub-node for {consideration_id}: {e}")
                    
            print(f"INFO: Successfully created {len(parent_node.sub_nodes)} fallback sub-nodes")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to create fallback sub-nodes: {e}")
            traceback.print_exc()
            return False
    
    def _create_single_dynamic_sub_node(self, 
                                       parent_node: ReasoningNode, 
                                       theme_info: Any, 
                                       application_refs: List[str], 
                                       app_display_name: str):
        """Create a single dynamic sub-node for a material consideration theme."""
        # Extract theme information
        if isinstance(theme_info, dict):
            theme_name = theme_info.get("theme_name", str(theme_info))
            ontology_match_id = theme_info.get("ontology_match_id")
        else:
            theme_name = str(theme_info)
            ontology_match_id = None
        
        # Try to find ontology match if not provided
        if not ontology_match_id and self.mc_ontology_manager:
            try:
                ontology_match_id = self.mc_ontology_manager.find_matching_consideration_id(theme_name)
            except Exception as e:
                print(f"WARN: Failed to find ontology match for '{theme_name}': {e}")
                ontology_match_id = None

        # Create unique sub-node ID
        sub_node_id_suffix = (ontology_match_id if ontology_match_id 
                             else theme_name.replace(" ", "_").replace("/", "_")[:30])
        sub_node_id = f"{parent_node.node_id}/DYNAMIC_{sub_node_id_suffix}"
        
        if ontology_match_id:
            sub_node_description = f"Detailed Assessment for {ontology_match_id}: {theme_name} ({app_display_name})"
        else:
            sub_node_description = f"Detailed Assessment: {theme_name} for {app_display_name}"

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
            self._apply_ontology_details_to_dynamic_node(dynamic_sub_node, ontology_match_id)
        else:
            # Fallback if no ontology match
            dynamic_sub_node.generic_material_considerations.append(theme_name)
        
        # Add the sub-node to the parent
        parent_node.add_sub_node(dynamic_sub_node)
        print(f"INFO: Created dynamic sub-node: {dynamic_sub_node.node_id} for '{theme_name}'. Ontology: {ontology_match_id or 'None'}")
    
    def _apply_ontology_details_to_dynamic_node(self, node: ReasoningNode, ontology_match_id: str):
        """Apply ontology details to a dynamic sub-node."""
        try:
            mc_details = self.mc_ontology_manager.get_consideration_details(ontology_match_id)
            if mc_details:
                node.generic_material_considerations.extend(
                    mc_details.get("primary_tags", [])
                )
                node.specific_policy_focus_ids.extend(
                    mc_details.get("relevant_policy_themes", [])
                )
                node.key_evidence_document_types.extend(
                    mc_details.get("key_evidence_docs", [])
                )
                node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
                node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
            else:
                print(f"WARN: No ontology details found for ID: {ontology_match_id}")
        except Exception as e:
            print(f"WARN: Failed to apply ontology details for {ontology_match_id}: {e}")
    
    def expand_all_dynamic_nodes(self, 
                                root_node: ReasoningNode, 
                                application_refs: List[str], 
                                app_display_name: str, 
                                app_context_summary: Dict[str, Any] | None,
                                report_type: str = "Default_MajorHybrid") -> List[ReasoningNode]:
        """
        Find and expand all dynamic parent nodes in a reasoning tree.
        
        Args:
            root_node: Root node of the reasoning tree
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            app_context_summary: Application context summary
            report_type: Type of report being generated
            
        Returns:
            List of dynamic parent nodes that were processed
        """
        def get_all_nodes(node: ReasoningNode) -> List[ReasoningNode]:
            """Get all nodes in the tree."""
            all_nodes = [node]
            for sub_node in node.sub_nodes.values():
                all_nodes.extend(get_all_nodes(sub_node))
            return all_nodes
        
        all_nodes = get_all_nodes(root_node)
        dynamic_parents = [node for node in all_nodes if node.is_dynamic_parent_node]
        
        print(f"INFO: Found {len(dynamic_parents)} dynamic parent nodes to expand")
        
        for parent_node in dynamic_parents:
            try:
                self.expand_dynamic_node(
                    parent_node, 
                    application_refs, 
                    app_display_name, 
                    app_context_summary, 
                    report_type
                )
            except Exception as e:
                print(f"ERROR: Failed to expand dynamic node {parent_node.node_id}: {e}")
                traceback.print_exc()
        
        return dynamic_parents
