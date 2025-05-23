# knowledge_base/policy_manager.py
import os
import json

class PolicyManager:
    def __init__(self, policy_dir="./policy_kb/"):
        self.policy_dir = policy_dir
        self.policy_path = os.path.join(self.policy_dir, "nppf_sample.json")
        if not os.path.exists(self.policy_path):
            self._create_default_policy()

    def _create_default_policy(self):
        os.makedirs(self.policy_dir, exist_ok=True)
        default_policy = {
            "NPPF_Ch16_Heritage": {"id": "NPPF_Ch16_Heritage", "title": "NPPF Chapter 16: Conserving and enhancing the historic environment", "summary": "Policies for heritage protection and assessment."},
            "NPPF_Ch12_Design": {"id": "NPPF_Ch12_Design", "title": "NPPF Chapter 12: Achieving well-designed places", "summary": "Policies for good design in planning."}
        }
        with open(self.policy_path, "w") as f:
            json.dump(default_policy, f, indent=2)

    def get_policies(self):
        with open(self.policy_path, "r") as f:
            return json.load(f)
