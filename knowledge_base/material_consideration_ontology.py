# knowledge_base/material_consideration_ontology.py
import os
import json

class MaterialConsiderationOntology:
    def __init__(self, ontology_dir="./mc_ontology_data/"):
        self.ontology_dir = ontology_dir
        self.ontology_path = os.path.join(self.ontology_dir, "main_material_considerations.json")
        if not os.path.exists(self.ontology_path):
            self._create_default_ontology()

    def _create_default_ontology(self):
        os.makedirs(self.ontology_dir, exist_ok=True)
        default_ontology = {
            "heritage": {"id": "heritage", "label": "Heritage", "description": "Heritage and historic environment considerations."},
            "design": {"id": "design", "label": "Design", "description": "Design and appearance considerations."}
        }
        with open(self.ontology_path, "w") as f:
            json.dump(default_ontology, f, indent=2)

    def get_ontology(self):
        with open(self.ontology_path, "r") as f:
            return json.load(f)
