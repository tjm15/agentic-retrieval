# knowledge_base/report_template_manager.py
import json
import os
from typing import Dict, List, Optional
from config import REPORT_TEMPLATE_DIR # Assuming config.py is accessible

class ReportTemplateManager:
    def __init__(self):
        self.templates: Dict[str, Dict] = {}
        self._load_templates()
        print(f"INFO: ReportTemplateManager initialized with {len(self.templates)} templates.")

    def _create_default_major_hybrid_template_if_needed(self): # Renamed to be more specific
        default_path = os.path.join(REPORT_TEMPLATE_DIR, "default_major_hybrid.json") # Specific filename
        if not os.path.exists(default_path):
            os.makedirs(REPORT_TEMPLATE_DIR, exist_ok=True) # Ensure directory exists
            template_content = {
                "report_type_id": "Default_MajorHybrid", # This is the key for lookup
                "report_id_prefix": "MajorHybridApp",
                "description": "Default Standard Report for Major Hybrid Planning Applications",
                "sections": [
                    {
                      "node_id": "1.0_SiteAndApplication", "description": "Site Description, Proposal Details & Planning History",
                      "node_type_tag": "IntroductionBlock", "generic_material_considerations": ["site_context", "proposal_details", "planning_history"], "specific_policy_focus_ids": ["LocalPlan_IntroductoryPolicy"], "depends_on_nodes": [],
                      "sub_sections": [
                        {"node_id": "1.1_SiteLocationAndDescription", "description": "Site Location and Description", "node_type_tag": "SiteDescription", "generic_material_considerations": ["site_identification", "existing_conditions"], "specific_policy_focus_ids": ["LocalPlan_SiteContextPolicy"], "key_evidence_document_types": ["ApplicationForm", "SiteLocationPlan", "DAS_Context", "UserGuide_SiteOverview"]},
                        {"node_id": "1.2_ProposalInDetail", "description": "The Proposed Development (Detailed & Outline where applicable)", "node_type_tag": "ProposalSummary", "generic_material_considerations": ["development_quantum", "phasing", "hybrid_nature"], "specific_policy_focus_ids": ["LocalPlan_DevelopmentManagementPolicy"], "key_evidence_document_types": ["DAS_Proposal", "DevelopmentSpecification", "ParameterPlans", "UserGuide_ProposalDetails"]},
                        {"node_id": "1.3_RelevantPlanningHistory", "description": "Relevant Planning History", "node_type_tag": "PlanningHistory", "generic_material_considerations": ["precedent", "extant_permissions"], "key_evidence_document_types": ["PlanningStatement_HistorySection", "PreviousDecisionNotices"]}
                      ]
                    },
                    { "node_id": "2.0_ConsultationResponses", "description": "Summary of Consultation Responses", "node_type_tag": "ConsultationSummaryBlock", "depends_on_nodes": ["1.0_SiteAndApplication/1.2_ProposalInDetail"]}, # Example dependency
                    { "node_id": "3.0_PlanningPolicyFramework", "description": "Relevant Planning Policy Framework", "node_type_tag": "PolicyFrameworkSummaryBlock", "depends_on_nodes": []},
                    { "node_id": "4.0_AssessmentOfMaterialConsiderations", "description": "Officer's Assessment of Material Planning Considerations", "node_type_tag": "MaterialConsiderationsBlock_Parent", "is_dynamic_parent_node": True, "depends_on_nodes": ["1.0_SiteAndApplication/1.2_ProposalInDetail", "2.0_ConsultationResponses", "3.0_PlanningPolicyFramework"]},
                    { "node_id": "5.0_OtherMatters", "description": "Other Relevant Matters (e.g., CIL, Equalities)", "node_type_tag": "OtherConsiderationsBlock", "depends_on_nodes": ["4.0_AssessmentOfMaterialConsiderations"]},
                    { "node_id": "6.0_PlanningBalanceAndConclusion", "description": "Overall Planning Balance and Officer's Conclusion", "node_type_tag": "PlanningBalanceAndConclusionBlock", "depends_on_nodes": ["4.0_AssessmentOfMaterialConsiderations", "5.0_OtherMatters"]},
                    { "node_id": "7.0_Recommendation", "description": "Officer's Recommendation", "node_type_tag": "FinalRecommendationBlock", "depends_on_nodes": ["6.0_PlanningBalanceAndConclusion"]}
                ]
            }
            with open(default_path, 'w') as f: json.dump(template_content, f, indent=2)
            print(f"INFO: Created default template: {default_path}")
        # Add similar methods for other default templates like householder, etc.

    def _load_templates(self):
        if not os.path.exists(REPORT_TEMPLATE_DIR):
            os.makedirs(REPORT_TEMPLATE_DIR)
            print(f"INFO: Created report template directory: {REPORT_TEMPLATE_DIR}")
        
        self._create_default_major_hybrid_template_if_needed() # Ensure default exists
        # Add calls to create other default templates here if needed

        for filename in os.listdir(REPORT_TEMPLATE_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(REPORT_TEMPLATE_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        template_data = json.load(f)
                        report_type = template_data.get("report_type_id")
                        if report_type: self.templates[report_type] = template_data
                        else: # Fallback to filename if report_type_id is missing
                            filename_stem = filename.replace(".json", "")
                            self.templates[filename_stem] = template_data
                            print(f"WARN: Template {filename} missing 'report_type_id'. Using '{filename_stem}'.")
                except Exception as e: print(f"ERROR loading template {filepath}: {e}")
    
    def get_template(self, report_type: str) -> Optional[Dict]:
        template = self.templates.get(report_type)
        if not template:
            print(f"WARN: No specific template for '{report_type}'. Checking for general defaults.")
            if "major" in report_type.lower() and "hybrid" in report_type.lower():
                template = self.templates.get("Default_MajorHybrid")
            elif "householder" in report_type.lower(): # Example for future
                template = self.templates.get("Default_Householder") 
            # Add more fallback logic based on keywords in report_type
        
        if not template: print(f"ERROR: Report template for type '{report_type}' ultimately not found.")
        return template
