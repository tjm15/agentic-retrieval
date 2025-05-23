# mrm/mrm_orchestrator.py
# This file should integrate IntentDefiner, NodeProcessor, and knowledge base managers.
# The actual implementation should be based on your latest design, but here's a conceptual scaffold:

from .intent_definer import IntentDefiner
from .node_processor import NodeProcessor
from core_types import ReasoningNode

class MRM:
    def __init__(self, db_manager, report_template_manager, mc_ontology_manager, policy_manager):
        self.db_manager = db_manager
        self.report_template_manager = report_template_manager
        self.mc_ontology_manager = mc_ontology_manager
        self.policy_manager = policy_manager
        self.intent_definer = IntentDefiner(report_template_manager, mc_ontology_manager, policy_manager)
        self.node_processor = NodeProcessor(db_manager, policy_manager)
        self.provenance_logs = []

    def orchestrate_full_report_generation(self, report_type_key, application_refs):
        # 1. Get the report template structure
        template = self.report_template_manager.get_template(report_type_key)
        # 2. Build the root ReasoningNode tree from the template
        root_node = self.intent_definer.build_reasoning_tree_from_template(template, application_refs)
        # 3. Process the reasoning tree (recursive intent issuing, agent calls, etc.)
        self.node_processor.process_reasoning_tree(root_node)
        # 4. Collect results and provenance
        self.provenance_logs.append(root_node.node_level_provenance)
        # 5. Return the final report structure
        return {
            "report_type": report_type_key,
            "application_refs": application_refs,
            "root_node": root_node,
            "provenance": [str(log) for log in self.provenance_logs if log]
        }

    def print_provenance_summary(self):
        print("\n--- Provenance Summary ---")
        for log in self.provenance_logs:
            print(str(log))
