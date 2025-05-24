# mrm/reasoning_tree_builder.py
"""
Reasoning Tree Builder for MRM Orchestrator
Handles template loading and reasoning tree construction
"""

import uuid
from typing import Dict, List, Any
from core_types import ReasoningNode
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology


class ReasoningTreeBuilder:
    """Builds reasoning trees from report templates."""
    
    def __init__(self, 
                 report_template_manager: ReportTemplateManager,
                 mc_ontology_manager: MaterialConsiderationOntology):
        self.report_template_manager = report_template_manager
        self.mc_ontology_manager = mc_ontology_manager
    
    def build_reasoning_tree_from_template(self, 
                                         template_data: Dict, 
                                         application_refs: List[str], 
                                         app_display_name: str, 
                                         parent_node_id_prefix: str = "") -> ReasoningNode:
        """
        Build a reasoning tree from a report template.
        
        Args:
            template_data: Report template data
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            parent_node_id_prefix: Prefix for parent node IDs
            
        Returns:
            Root ReasoningNode of the constructed tree
        """
        root_node_id = f"{parent_node_id_prefix}ROOT_{template_data.get('report_type_id', 'GenericReport')}"
        root = ReasoningNode(
            node_id=root_node_id,
            description=template_data.get("description", "Root of the Planning Report")
        )
        root.application_refs = application_refs

        def build_node_recursive(section_data: Dict, current_parent_id: str) -> ReasoningNode:
            """Recursively build nodes from template sections."""
            node_id_suffix = section_data.get("node_id", str(uuid.uuid4())[:8])
            full_node_id = f"{current_parent_id}/{node_id_suffix}" if current_parent_id else node_id_suffix
            
            node = ReasoningNode(
                node_id=full_node_id,
                description=section_data.get("description", "No description provided.")
            )
            node.application_refs = application_refs
            
            # Set node properties from template
            node.node_type_tag = section_data.get("node_type_tag")
            node.generic_material_considerations = section_data.get("generic_material_considerations", [])
            node.specific_policy_focus_ids = section_data.get("specific_policy_focus_ids", [])
            node.key_evidence_document_types = section_data.get("key_evidence_document_types", [])
            node.thematic_policy_descriptors = section_data.get("thematic_policy_descriptors", [])
            node.linked_ontology_entry_id = section_data.get("linked_ontology_entry_id")
            node.is_dynamic_parent_node = section_data.get("is_dynamic_parent_node", False)
            node.agent_to_invoke_hint = section_data.get("agent_to_invoke_hint")
            node.data_requirements_schema_hint = section_data.get("data_requirements_schema_hint")
            
            # Process dependencies
            node.depends_on_nodes = [
                f"{current_parent_id}/{dep}" if dep and not dep.startswith(root_node_id) and not dep.startswith("ROOT_") else dep 
                for dep in section_data.get("depends_on_nodes", [])
            ]

            # Apply ontology details if linked
            if node.linked_ontology_entry_id:
                self._apply_ontology_details(node, app_display_name)

            # Process sub-sections recursively
            if "sub_sections" in section_data:
                for sub_section_data in section_data["sub_sections"]:
                    sub_node = build_node_recursive(sub_section_data, full_node_id)
                    node.add_sub_node(sub_node)
                    
            return node

        # Build root node structure
        for section in template_data.get("sections", []):
            root.add_sub_node(build_node_recursive(section, root_node_id))
        
        return root
    
    def _apply_ontology_details(self, node: ReasoningNode, app_display_name: str):
        """Apply material consideration ontology details to a node."""
        if not node.linked_ontology_entry_id or not self.mc_ontology_manager:
            return
            
        mc_details = self.mc_ontology_manager.get_consideration_details(node.linked_ontology_entry_id)
        if mc_details:
            # Update description with template
            node.description = mc_details.get("display_name_template", node.description).replace("{app_name}", app_display_name)
            
            # Extend lists with ontology data
            node.generic_material_considerations.extend(mc_details.get("primary_tags", []))
            node.specific_policy_focus_ids.extend(mc_details.get("relevant_policy_themes", []))
            node.key_evidence_document_types.extend(mc_details.get("key_evidence_docs", []))
            
            # Set hints if not already present
            if not node.agent_to_invoke_hint and mc_details.get("agent_to_invoke_hint"):
                node.agent_to_invoke_hint = mc_details.get("agent_to_invoke_hint")
            if not node.data_requirements_schema_hint and mc_details.get("data_schema_hint"):
                node.data_requirements_schema_hint = mc_details.get("data_schema_hint")
        else:
            print(f"WARN: Ontology entry ID '{node.linked_ontology_entry_id}' for node '{node.node_id}' not found.")
    
    from typing import Optional

    def get_template(self, report_type: str) -> Optional[Dict]:
        """Get a report template by type."""
        return self.report_template_manager.get_template(report_type)
    
    def get_all_nodes_in_graph(self, root_node: ReasoningNode) -> List[ReasoningNode]:
        """Get all nodes in the reasoning graph."""
        all_nodes = [root_node]
        for sub_node in root_node.sub_nodes.values():
            all_nodes.extend(self.get_all_nodes_in_graph(sub_node))
        return all_nodes
