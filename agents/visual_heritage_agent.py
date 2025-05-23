# agents/visual_heritage_agent.py
from typing import Dict, Any
import google.generativeai as genai # For model type hint
from .base_agent import BaseSubsidiaryAgent # Use BaseSubsidiaryAgent
from core_types import Intent # For type hinting

class VisualHeritageAssessmentAgentGemini(BaseSubsidiaryAgent):
    def __init__(self, model_instance: genai.GenerativeModel): # Expect model instance
        super().__init__("VisualHeritageAssessmentAgent_V1_Gemini", model_instance) # Pass model instance up

    def process(self, intent: Intent, agent_input_data: Dict) -> Dict[str, Any]:
        # agent_input_data comes from MRM's IntentDefiner, which used LLM to decide what this agent needs
        # Example: {"mrm_guidance_for_agent_input_prep": "Focus on Art Deco influences...",
        #           "visual_descriptions_text_query_result": "CGI shows...", (this would be populated by MRM sub-intents if complex)
        #           "relevant_heritage_policy_ids": ["NPPF_Ch16_Heritage", "LocalPolicy_CAX"] }

        guidance = agent_input_data.get("mrm_guidance_for_agent_input_prep", "General visual and heritage assessment.")
        visual_context = agent_input_data.get("visual_descriptions_text_query_result", "No specific visual descriptions provided by MRM for agent processing.")
        # Policy context is now primarily handled by _prepare_gemini_content using intent.llm_policy_context_summary

        prompt_prefix = (
            f"You are a specialist AI assistant for Visual Impact and Heritage Assessment in planning. "
            f"Your current task is to provide an assessment for: '{intent.assessment_focus}', guided by: '{guidance}'.\n"
            f"Available Visual Context (text descriptions):\n{visual_context}\n\n"
            f"Consider the provided document context (full docs or chunks) and relevant policies that follow this instruction. "
            f"Structure your response clearly, addressing potential visual impacts, effects on heritage assets (character, setting), "
            f"and adherence to relevant design/heritage principles inferred from context. "
            f"Output a detailed textual analysis. If possible, conclude with a summary of positive aspects and concerns.\n\n"
            f"YOUR DETAILED VISUAL AND HERITAGE ASSESSMENT:\n"
        )
        
        # The super().process call handles the Gemini API interaction using the prepared context on the Intent
        try:
            raw_agent_output_dict = super().process(intent, agent_input_data, prompt_prefix)
            
            # Post-process the agent's raw output if needed
            analysis_text = raw_agent_output_dict.get("agent_output", {}).get("generated_raw", "Agent analysis not generated.")
            
            # Simple structuring example
            final_structured_output = {
                "assessment_summary": analysis_text[:800] + "..." if analysis_text else "N/A",
                "key_visual_points": "Extracted via regex/keywords from analysis_text (conceptual)",
                "key_heritage_points": "Extracted via regex/keywords from analysis_text (conceptual)",
                "raw_llm_response_from_agent": analysis_text # Keep the full text
            }
            raw_agent_output_dict["agent_output"]["structured_summary"] = final_structured_output # Add to agent's output
            
            intent.provenance.add_action(f"Agent '{self.agent_name}' post-processing complete.", {"summary_len": len(final_structured_output["assessment_summary"])})
            return raw_agent_output_dict # Return the full dict from super().process, potentially with added fields
        except Exception as e:
            intent.provenance.add_action(f"Agent '{self.agent_name}' failed during its custom process method or post-processing.", {"error": str(e)})
            raise
