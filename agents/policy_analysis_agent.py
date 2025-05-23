# agents/policy_analysis_agent.py
# PolicyAnalysisAgent - Specialized agent for comprehensive policy framework analysis

from typing import Dict, Any
from agents.base_agent import BaseSubsidiaryAgent
from core_types import Intent
from config import SUBSIDIARY_AGENT_GEN_CONFIG
import json

class PolicyAnalysisAgent(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "PolicyAnalysisAgent"):
        super().__init__(agent_name)
        print(f"INFO: PolicyAnalysisAgent initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        Process policy framework analysis tasks with specialized prompting for policy interpretation,
        hierarchy analysis, and compliance assessment.
        """
        
        # Build specialized prompt for policy analysis
        custom_prompt_prefix = f"""You are a specialized Planning Policy Analysis Agent with expert knowledge of the UK planning system, policy hierarchy, and legal interpretation.

ANALYSIS TASK: {intent.assessment_focus}

Your role is to:
1. Analyze the policy framework hierarchy (National → Regional → Local → Supplementary)
2. Identify key policy requirements and tests applicable to this development
3. Assess policy compliance and potential conflicts
4. Provide clear guidance on policy weight and material considerations
5. Highlight any emerging or recently updated policies

CONTEXT:
- Application: {intent.application_refs[0] if intent.application_refs else 'Unknown'}
- Task Type: {intent.task_type}
- Data Requirements: {json.dumps(intent.data_requirements, indent=2) if intent.data_requirements else 'Standard policy analysis'}

SPECIFIC INSTRUCTIONS:
- Structure your analysis by policy tier (National/Regional/Local)
- Quote specific policy text where relevant
- Identify any policy tensions or contradictions
- Assess development plan compliance
- Consider material weight of policies based on adoption status and relevance
- Provide clear conclusions on policy support/objection to the proposal

Please provide a comprehensive policy analysis following the above framework:

"""

        return super().process(intent, agent_input_data, custom_prompt_prefix)

class DefaultPlanningAnalystAgent(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "default_planning_analyst_agent"):
        super().__init__(agent_name)
        print(f"INFO: DefaultPlanningAnalystAgent initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        General-purpose planning analysis agent for tasks that don't require specialized expertise.
        """
        
        custom_prompt_prefix = f"""You are a qualified Planning Officer with comprehensive knowledge of the UK planning system. You are analyzing a planning application for assessment purposes.

ASSESSMENT TASK: {intent.assessment_focus}

CONTEXT:
- Application Reference: {intent.application_refs[0] if intent.application_refs else 'Unknown'}
- Node Type: {intent.task_type}
- Focus Area: {intent.assessment_focus}

Your task is to provide a thorough planning assessment covering:
1. Relevant planning considerations
2. Policy compliance evaluation  
3. Material impacts and benefits
4. Recommendations based on planning merits

Please structure your response clearly with headings and provide evidence-based conclusions:

"""

        return super().process(intent, agent_input_data, custom_prompt_prefix)

class LLMPlanningPolicyAnalyst(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str = "LLM_PlanningPolicyAnalyst"):
        super().__init__(agent_name)
        print(f"INFO: LLMPlanningPolicyAnalyst initialized: {self.agent_name}")
    
    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        """
        Advanced LLM-powered policy analyst for complex policy interpretation and synthesis.
        """
        
        custom_prompt_prefix = f"""You are an advanced AI Planning Policy Analyst with deep expertise in policy interpretation, legal precedent, and planning law. You excel at synthesizing complex policy frameworks and providing nuanced analysis.

ADVANCED ANALYSIS TASK: {intent.assessment_focus}

ANALYTICAL FRAMEWORK:
1. Policy Hierarchy Analysis - Weight and relevance of each policy tier
2. Legal Interpretation - Consider statutory requirements and case law principles  
3. Policy Evolution - Account for emerging policies and recent updates
4. Precedent Analysis - Consider how similar applications have been determined
5. Strategic Context - Consider wider planning objectives and local context

APPLICATION CONTEXT:
- Reference: {intent.application_refs[0] if intent.application_refs else 'Unknown'}
- Assessment Focus: {intent.assessment_focus}
- Task Type: {intent.task_type}

EXPECTED OUTPUT:
- Provide sophisticated policy analysis with legal grounding
- Consider policy conflicts and how they should be resolved
- Assess strategic fit with local planning objectives
- Provide clear recommendations with detailed reasoning
- Structure analysis logically with clear conclusions

Please provide your advanced policy analysis:

"""

        return super().process(intent, agent_input_data, custom_prompt_prefix)
