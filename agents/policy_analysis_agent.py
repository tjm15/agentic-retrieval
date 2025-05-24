# agents/policy_analysis_agent.py
# PolicyAnalysisAgent - Specialized agent for comprehensive policy framework analysis

from typing import Dict, Any
from agents.base_agent import BaseSubsidiaryAgent
from core_types import Intent
from config import SUBSIDIARY_AGENT_GEN_CONFIG
import json

def load_prompt_from_file(file_path: str) -> str:
    with open(file_path, 'r') as f:
        return f.read()

class PolicyAnalysisAgent(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "PolicyAnalysisAgent"):
        super().__init__(agent_name)
        self.prompt_template = load_prompt_from_file("/home/tim-mayoh/repos/agentic-retrieval/prompts/policy_analysis_agent_prompt.txt")
        print(f"INFO: PolicyAnalysisAgent initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        Process policy framework analysis tasks with specialized prompting for policy interpretation,
        hierarchy analysis, and compliance assessment.
        """
        
        # Build specialized prompt for policy analysis
        custom_prompt_prefix = self.prompt_template.format(
            assessment_focus=intent.assessment_focus,
            application_ref=intent.application_refs[0] if intent.application_refs else 'Unknown',
            task_type=intent.task_type,
            data_requirements_json=json.dumps(intent.data_requirements, indent=2) if intent.data_requirements else 'Standard policy analysis'
        )

        return super().process(intent, agent_input_data, custom_prompt_prefix)

class DefaultPlanningAnalystAgent(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "default_planning_analyst_agent"):
        super().__init__(agent_name)
        self.prompt_template = load_prompt_from_file("/home/tim-mayoh/repos/agentic-retrieval/prompts/default_planning_analyst_agent_prompt.txt")
        print(f"INFO: DefaultPlanningAnalystAgent initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        General-purpose planning analysis agent for tasks that don't require specialized expertise.
        """
        
        custom_prompt_prefix = self.prompt_template.format(
            assessment_focus=intent.assessment_focus,
            application_ref=intent.application_refs[0] if intent.application_refs else 'Unknown',
            task_type=intent.task_type
        )

        return super().process(intent, agent_input_data, custom_prompt_prefix)

class LLMPlanningPolicyAnalyst(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "LLM_PlanningPolicyAnalyst"):
        super().__init__(agent_name)
        self.prompt_template = load_prompt_from_file("/home/tim-mayoh/repos/agentic-retrieval/prompts/llm_planning_policy_analyst_prompt.txt")
        print(f"INFO: LLMPlanningPolicyAnalyst initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        Advanced LLM-powered policy analyst for complex policy interpretation and synthesis.
        """
        
        custom_prompt_prefix = self.prompt_template.format(
            assessment_focus=intent.assessment_focus,
            application_ref=intent.application_refs[0] if intent.application_refs else 'Unknown',
            task_type=intent.task_type
        )

        return super().process(intent, agent_input_data, custom_prompt_prefix)
