# knowledge_base/material_consideration_ontology.py
import json
import os
from typing import Dict, List, Optional, Any
from config import MC_ONTOLOGY_DIR

class MaterialConsiderationOntology:
    def __init__(self):
        self.ontology: Dict[str, Dict[str, Any]] = {}
        self._load_ontology()
        print(f"INFO: MaterialConsiderationOntology initialized with {len(self.ontology)} entries.")

    def _create_default_ontology_if_needed(self):
        default_path = os.path.join(MC_ONTOLOGY_DIR, "main_material_considerations.json")
        if not os.path.exists(default_path):
            os.makedirs(MC_ONTOLOGY_DIR, exist_ok=True) # Ensure directory exists
            ontology_content = [ # Using the comprehensive list from the "Why is so much hardcoded" response
                {"id": "HousingDelivery", "id_suffix": "HousingDelivery", "display_name_template": "Housing Delivery (Quantum, Mix, Affordability, Density, Standards) for {app_name}", "primary_tags": ["housing_impact", "NPPF_Ch5"], "relevant_policy_themes": ["LondonPlan_H_Series", "LocalPlan_Housing"], "key_evidence_docs": ["HousingStatement", "AffordableHousingStatement", "DevelopmentSpecification", "ViabilityAssessment"], "data_schema_hint": {"total_homes_net":"int", "affordable_provision_summary":"str", "unit_mix_compliance":"str"}, "agent_to_invoke_hint": "HousingMetricsAgent"},
                {"id": "DesignQualityAndTownscape", "id_suffix": "DesignQualityAndTownscape", "display_name_template": "Design Quality, Urban Design, and Townscape Impact for {app_name}", "primary_tags": ["design_quality", "townscape_visual_impact", "NPPF_Ch12"], "relevant_policy_themes": ["LondonPlan_D_Series", "LocalPlan_DesignPolicies"], "key_evidence_docs": ["DAS_AllVolumes", "TVIA", "DesignCode"], "agent_to_invoke_hint": "VisualHeritageAssessment_GeminiFlash_V1"}, # Corrected from potential_agent_hint
                {"id": "HeritageImpact", "id_suffix": "HeritageImpact", "display_name_template": "Impact on Heritage Assets (Designated and Non-Designated, including Archaeology and Setting) for {app_name}", "primary_tags": ["heritage_conservation", "archaeology", "NPPF_Ch16"], "relevant_policy_themes": ["LondonPlan_HC_Series", "LocalPlan_HeritagePolicies"], "key_evidence_docs": ["HeritageImpactAssessment", "ArchaeologicalDBA", "ES_HeritageChapter"], "agent_to_invoke_hint": "VisualHeritageAssessment_GeminiFlash_V1"}, # Corrected from potential_agent_hint
                {"id": "TransportAndAccessibility", "id_suffix": "TransportAndAccessibility", "display_name_template": "Transport Impact, Accessibility, Parking, and Sustainable Travel for {app_name}", "primary_tags": ["transport_assessment", "sustainable_travel", "NPPF_Ch9"], "relevant_policy_themes": ["LondonPlan_T_Series", "LocalPlan_TransportPolicies"], "key_evidence_docs": ["TransportAssessment", "TravelPlan", "ParkingStrategy"]},
                {"id": "SustainabilityAndEnvironment", "id_suffix": "SustainabilityAndEnvironment", "display_name_template": "Sustainability, Energy, BNG, Climate Change, Air Quality, Noise, Water Mgt for {app_name}", "primary_tags": ["sustainability_strategy", "NPPF_Ch14_Ch15"], "relevant_policy_themes": ["LondonPlan_SI_GG_Series", "LocalPlan_EnvironmentClimate"], "key_evidence_docs": ["EnergyStatement", "SustainabilityStatement", "BNGReport", "FRA", "AQ_assessment", "Noise_assessment"]},
                {"id": "EconomyAndEmployment", "id_suffix": "EconomyAndEmployment", "display_name_template": "Economic Benefits, Job Creation, Commercial Strategy for {app_name}", "primary_tags": ["economic_impact", "NPPF_Ch6"], "relevant_policy_themes": ["LondonPlan_E_Series", "LocalPlan_Economy"], "key_evidence_docs": ["EconomicStatement", "EmploymentSkillsPlan"]},
                {"id": "CommunityAndPublicRealm", "id_suffix": "CommunityAndPublicRealm", "display_name_template": "Community Facilities, Public Realm, Open Space, Play Space for {app_name}", "primary_tags": ["community_infrastructure", "NPPF_Ch8"], "relevant_policy_themes": ["LondonPlan_S_D_Series", "LocalPlan_CommunityOpenSpace"], "key_evidence_docs": ["SCI", "OpenSpaceAssessment", "PublicRealmStrategy"]},
                {"id": "NeighbourAmenity", "id_suffix": "NeighbourAmenity", "display_name_template": "Impact on Neighbouring Amenity (Sunlight, Daylight, Privacy, Outlook, Noise) for {app_name}", "primary_tags": ["residential_amenity_impact", "NPPF_Amenity"], "relevant_policy_themes": ["LocalPlan_Amenity_Policies", "BRE_Guidelines_2022"], "key_evidence_docs": ["DaylightSunlightReport", "NoiseImpactAssessment_Operational"]},
                {"id": "FloodRisk", "id_suffix": "FloodRisk", "display_name_template": "Flood Risk Assessment and Water Management (SuDS) for {app_name}", "primary_tags": ["flood_risk", "suds", "NPPF_Ch14"], "relevant_policy_themes": ["LondonPlan_SI12_SI13", "LocalPlan_FloodRisk"], "key_evidence_docs": ["Flood Risk Assessment", "Drainage Strategy"]}, # Changed description_template to display_name_template, tags to primary_tags, policies to relevant_policy_themes, required_evidence_keywords to key_evidence_docs
                {"id": "AirQuality", "id_suffix": "AirQuality", "display_name_template": "Air Quality Impact and Mitigation for {app_name}", "primary_tags": ["air_quality", "NPPF_Ch15"], "relevant_policy_themes": ["LondonPlan_SI1", "LocalPlan_AirQuality"], "key_evidence_docs": ["Air Quality Assessment", "ES_AirQuality"]},
                {"id": "NoiseImpact", "id_suffix": "NoiseImpact", "display_name_template": "Noise Impact Assessment and Mitigation (Construction and Operational) for {app_name}", "primary_tags": ["noise_impact", "NPPF_Ch15"], "relevant_policy_themes": ["LondonPlan_SI1", "LocalPlan_Noise"], "key_evidence_docs": ["Noise Impact Assessment", "ES_Noise", "ConstructionManagementPlan"]},
                {"id": "BiodiversityNetGain", "id_suffix": "BiodiversityNetGain", "display_name_template": "Biodiversity Net Gain Assessment and Strategy for {app_name}", "primary_tags": ["bng", "ecology", "NPPF_Ch15"], "relevant_policy_themes": ["LondonPlan_G6", "LocalPlan_Biodiversity"], "key_evidence_docs": ["EcologicalImpactAssessment", "BNGReport", "LandscapeMasterplan"]},
            ]
            with open(default_path, 'w') as f: json.dump(ontology_content, f, indent=2)
            print(f"INFO: Created default MC ontology: {default_path}")

    def _load_ontology(self):
        if not os.path.exists(MC_ONTOLOGY_DIR): os.makedirs(MC_ONTOLOGY_DIR); print(f"Created MC Ontology dir: {MC_ONTOLOGY_DIR}")
        self._create_default_ontology_if_needed()
        for filename in os.listdir(MC_ONTOLOGY_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(MC_ONTOLOGY_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        data_list = json.load(f)
                        for entry in data_list:
                            if "id" in entry: self.ontology[entry["id"]] = entry
                except Exception as e: print(f"ERROR loading MC ontology from {filepath}: {e}")

    def get_consideration_details(self, mc_id: str) -> Optional[Dict[str, Any]]: return self.ontology.get(mc_id)
    
    def find_matching_consideration_id(self, theme_from_llm_scan: str) -> Optional[str]:
        theme_l = theme_from_llm_scan.lower()
        # Prioritize matching against explicit primary_tags from ontology entries first
        for mc_id, mc_data in self.ontology.items():
            if any(tag.lower() == theme_l for tag in mc_data.get("primary_tags", [])): return mc_id
        # Then try broader matching against other fields
        for mc_id, mc_data in self.ontology.items():
            if theme_l in mc_id.lower(): return mc_id # Match against ID itself
            if mc_data.get("display_name_template") and theme_l in mc_data["display_name_template"].lower().replace("{app_name}", "").strip(): return mc_id # Match in display name
            # Match if theme_l is a substring of any primary_tag (more general than exact match above)
            if any(theme_l in tag.lower() for tag in mc_data.get("primary_tags", [])): return mc_id
            # Match against key_evidence_docs
            if any(theme_l in kw.lower() for kw in mc_data.get("key_evidence_docs", [])): return mc_id
            # Match against relevant_policy_themes
            if any(theme_l in policy_theme.lower() for policy_theme in mc_data.get("relevant_policy_themes", [])): return mc_id
        
        print(f"WARN: No direct ontology match for LLM-scanned theme: '{theme_from_llm_scan}'")
        return None
