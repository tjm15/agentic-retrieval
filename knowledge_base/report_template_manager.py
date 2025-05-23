# knowledge_base/report_template_manager.py
import os
import json

class ReportTemplateManager:
    def __init__(self, template_dir="./report_templates/"):
        self.template_dir = template_dir
        self.default_template_path = os.path.join(self.template_dir, "default_major_hybrid.json")
        if not os.path.exists(self.default_template_path):
            self._create_default_template()

    def _create_default_template(self):
        os.makedirs(self.template_dir, exist_ok=True)
        default_template = {
            "report_type_id": "Default_MajorHybrid",
            "title": "Major Hybrid Planning Application Assessment",
            "sections": [
                {"id": "heritage", "title": "Heritage Assessment", "type": "heritage", "material_considerations": ["heritage"], "policy_ids": ["NPPF_Ch16_Heritage"]},
                {"id": "design", "title": "Design Assessment", "type": "design", "material_considerations": ["design"], "policy_ids": ["NPPF_Ch12_Design"]}
            ]
        }
        with open(self.default_template_path, "w") as f:
            json.dump(default_template, f, indent=2)

    def get_template(self, report_type_key):
        path = self.default_template_path # For now, only one template
        with open(path, "r") as f:
            return json.load(f)
