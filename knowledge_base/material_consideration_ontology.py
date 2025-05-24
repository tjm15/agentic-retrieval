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

    def _load_ontology(self):
        if not os.path.exists(MC_ONTOLOGY_DIR):
            os.makedirs(MC_ONTOLOGY_DIR)
            print(f"Created MC Ontology dir: {MC_ONTOLOGY_DIR}")
            # Optionally, create some default individual files here if the directory is empty
            # For example, create an empty HousingDelivery.json or a minimal one.
            # self._create_minimal_default_files_if_empty() # New helper

        for filename in os.listdir(MC_ONTOLOGY_DIR):
            if filename.endswith(".json") and filename != "main_material_considerations.json": # Ensure the old main file is skipped
                filepath = os.path.join(MC_ONTOLOGY_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        # Each file now contains a single JSON object, not a list
                        entry = json.load(f)
                        if "id" in entry:
                            self.ontology[entry["id"]] = entry
                        else:
                            print(f"WARN: Entry in {filepath} is missing an 'id' field.")
                except json.JSONDecodeError as e:
                    print(f"ERROR loading MC ontology from {filepath}: Invalid JSON - {e}")
                except Exception as e:
                    print(f"ERROR loading MC ontology from {filepath}: {e}")
    
    # def _create_minimal_default_files_if_empty(self):
    #     # Example: Create a few essential empty/minimal files if the directory is truly empty
    #     # This is just a conceptual placeholder
    #     if not os.listdir(MC_ONTOLOGY_DIR):
    #         minimal_housing = {"id": "HousingDelivery", "display_name_template": "Housing for {app_name}"}
    #         with open(os.path.join(MC_ONTOLOGY_DIR, "HousingDelivery.json"), 'w') as f:
    #             json.dump(minimal_housing, f, indent=2)
    #         print("INFO: Created minimal default HousingDelivery.json as ontology directory was empty.")


    def get_consideration_details(self, mc_id: str) -> Optional[Dict[str, Any]]:
        return self.ontology.get(mc_id)

    def get_all_consideration_ids(self) -> List[str]:
        return list(self.ontology.keys())

    def get_default_considerations_for_report_type(self, report_type: str) -> List[str]:
        """
        Get a default set of material consideration IDs for a given report type.
        This serves as a fallback when the LLM scan returns no specific themes.
        
        Args:
            report_type: The report type (e.g., "Default_MajorHybrid")
            
        Returns:
            List of material consideration IDs that are typically relevant for this report type
        """
        # Define default sets based on report type
        if "MajorHybrid" in report_type or "Major" in report_type:
            # Comprehensive set for major developments
            default_set = [
                "HousingDelivery",
                "DesignQualityAndTownscape", 
                "HeritageImpact",
                "TransportAndAccessibility",
                "SustainabilityAndEnvironment", # Assuming this will be a separate file too
                "EconomyAndEmployment",       # Assuming this will be a separate file too
                "CommunityAndPublicRealm",    # Assuming this will be a separate file too
                "NeighbourAmenity",           # Assuming this will be a separate file too
                "FloodRisk"                   # Assuming this will be a separate file too
            ]
        elif "Minor" in report_type or "Householder" in report_type:
            # More focused set for smaller developments
            default_set = [
                "DesignQualityAndTownscape",
                "NeighbourAmenity",
                "HeritageImpact"
            ]
        elif "Commercial" in report_type or "Employment" in report_type:
            # Commercial-focused set
            default_set = [
                "EconomyAndEmployment",
                "DesignQualityAndTownscape",
                "TransportAndAccessibility",
                "SustainabilityAndEnvironment",
                "NeighbourAmenity"
            ]
        else:
            # Generic fallback - core planning considerations
            default_set = [
                "HousingDelivery",
                "DesignQualityAndTownscape",
                "HeritageImpact",
                "TransportAndAccessibility",
                "NeighbourAmenity"
            ]
            
        # Filter to only include IDs that exist in our ontology (i.e., have a corresponding .json file)
        available_defaults = [mc_id for mc_id in default_set if mc_id in self.ontology]
        
        if len(available_defaults) < len(default_set):
            missing_defaults = set(default_set) - set(available_defaults)
            print(f"WARN: Some default considerations for report type '{report_type}' are not loaded: {missing_defaults}. Check if corresponding JSON files exist in {MC_ONTOLOGY_DIR}.")

        print(f"INFO: Providing {len(available_defaults)} default material considerations for report type '{report_type}'")
        return available_defaults

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
            # Match against trigger_keywords_for_llm_scan
            if any(theme_l in kw.lower() for kw in mc_data.get("trigger_keywords_for_llm_scan", [])): return mc_id
            # Match against key_evidence_docs
            if any(theme_l in kw.lower() for kw in mc_data.get("key_evidence_docs", [])): return mc_id
            # Match against relevant_policy_themes
            if any(theme_l in policy_theme.lower() for policy_theme in mc_data.get("relevant_policy_themes", [])): return mc_id
        
        print(f"WARN: No direct ontology match for LLM-scanned theme: '{theme_from_llm_scan}'")
        return None
