# agents/visual_heritage_agent.py
from typing import Dict, Any, List, Optional
from google import genai
from config import VISUAL_HERITAGE_AGENT_GEN_CONFIG, GEMINI_PRO_VISION_MODEL_NAME
import json 
from PIL import Image # Assuming PIL is installed
import io 

from agents.base_agent import BaseSubsidiaryAgent
from core_types import Intent, SecurityAssessment 

class VisualHeritageAgent(BaseSubsidiaryAgent):
    def __init__(self, agent_name: str):
        super().__init__(agent_name)
        self.model_name = GEMINI_PRO_VISION_MODEL_NAME  # Override with vision model
        print(f"INFO: Init VisualHeritageAgent: {self.agent_name} with model {GEMINI_PRO_VISION_MODEL_NAME}")
        
    def _prepare_image_parts(self, intent: Intent) -> List[Any]:
        image_parts = []
        if intent.image_context: # Now using the added attribute
            intent.provenance.add_action(f"Agent {self.agent_name} preparing {len(intent.image_context)} images.", 
                                         {"count": len(intent.image_context)})
            for img_idx, img_data in enumerate(intent.image_context):
                try:
                    if not isinstance(img_data, dict) or 'image_bytes' not in img_data or 'mime_type' not in img_data:
                        intent.provenance.add_action(f"Agent {self.agent_name} skipping image {img_idx+1} due to missing data.", {"image_index": img_idx})
                        print(f"WARNING: VisualHeritageAgent skipping image {img_idx+1}, data incomplete: {img_data.keys() if isinstance(img_data, dict) else 'Not a dict'}")
                        continue

                    image_bytes = img_data['image_bytes']
                    mime_type = img_data['mime_type']
                    
                    if not image_bytes or not mime_type.startswith("image/"):
                        intent.provenance.add_action(f"Agent {self.agent_name} skipping image {img_idx+1} due to invalid data/mime_type.", 
                                                     {"mime_type": mime_type, "image_index": img_idx})
                        print(f"WARNING: VisualHeritageAgent skipping image {img_idx+1}, invalid data or mime_type: {mime_type}")
                        continue

                    image_parts.append({"mime_type": mime_type, "data": image_bytes})
                    intent.provenance.add_action(f"Agent {self.agent_name} successfully prepared image {img_idx+1} for inclusion.", 
                                                 {"mime_type": mime_type, "image_index": img_idx})
                except Exception as e:
                    intent.provenance.add_action(f"Agent {self.agent_name} failed to process image {img_idx+1}.", 
                                                 {"error": str(e), "image_index": img_idx})
                    print(f"ERROR: VisualHeritageAgent failed to process image {img_idx+1}: {e}")
        else:
            intent.provenance.add_action(f"Agent {self.agent_name} found no images in Intent image_context.")
        return image_parts

    def process(self, intent: Intent, agent_input_data: Dict, prompt_prefix: str) -> Dict[str, Any]:
        intent.provenance.add_action(f"Agent '{self.agent_name}' (VisualHeritage) processing started.", 
                                     {"input_keys": list(agent_input_data.keys()), "focus": intent.assessment_focus})

        image_gemini_parts = self._prepare_image_parts(intent)

        final_gemini_parts = [prompt_prefix] 
        final_gemini_parts.extend(image_gemini_parts) 

        base_text_parts_without_initial_prefix = self._prepare_gemini_content(intent, "")
        if base_text_parts_without_initial_prefix and base_text_parts_without_initial_prefix[0] == "":
            final_gemini_parts.extend(base_text_parts_without_initial_prefix[1:])
        else:
            final_gemini_parts.extend(base_text_parts_without_initial_prefix)
        
        parts_summary_for_log = []
        for part in final_gemini_parts:
            if isinstance(part, str):
                parts_summary_for_log.append({"type": "text", "length": len(part)})
            elif isinstance(part, dict) and 'mime_type' in part:
                parts_summary_for_log.append({"type": "image", "mime_type": part['mime_type']})
            else:
                parts_summary_for_log.append({"type": "unknown"})
        intent.provenance.add_action(f"Agent '{self.agent_name}' prepared combined parts for LLM.", {"parts_summary": parts_summary_for_log})
        
        if image_gemini_parts and not any(isinstance(p, str) and p.strip() for p in final_gemini_parts if p != prompt_prefix):
            final_gemini_parts.append("\nDescribe the content of the image(s) in detail, focusing on elements relevant to its historical or cultural significance for planning and heritage assessments.")
            intent.provenance.add_action(f"Agent '{self.agent_name}' added generic image instruction as text parts were minimal.")

        try:
            current_gen_config_dict = VISUAL_HERITAGE_AGENT_GEN_CONFIG.copy()
            expected_mime_type = agent_input_data.get("expected_output_mime_type")
            if expected_mime_type == "application/json":
                 current_gen_config_dict["response_mime_type"] = "application/json"
            
            generation_config_obj = current_gen_config_dict

            # Convert mixed content list to proper Gemini API format
            gemini_content = []
            for part in final_gemini_parts:
                if isinstance(part, str):
                    gemini_content.append(part)
                elif isinstance(part, dict) and 'mime_type' in part and 'data' in part:
                    # Image part - keep as is for Gemini API
                    gemini_content.append(part)
            
            response = self.client.models.generate_content(
                model=GEMINI_PRO_VISION_MODEL_NAME,
                contents=gemini_content,
                config=generation_config_obj  # type: ignore
            )

            # Robust response parsing
            raw_text = getattr(response, "text", None)
            if not raw_text and hasattr(response, "candidates") and response.candidates:
                first_candidate = response.candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    raw_text = "".join([getattr(p, 'text', '') for p in parts if hasattr(p, 'text') and isinstance(p.text, str)])
            if not raw_text or not isinstance(raw_text, str):
                raise ValueError("No valid text response from Gemini API.")
            
            intent.provenance.add_action(f"Agent '{self.agent_name}' LLM call successful.", {"output_length": len(raw_text)})
            
            output_payload = {"generated_raw": raw_text}
            if generation_config_obj.get("response_mime_type") == "application/json":
                try:
                    output_payload["structured_payload"] = json.loads(raw_text)
                except json.JSONDecodeError as json_err:
                    intent.provenance.add_action(f"Agent '{self.agent_name}' failed to parse its JSON output.", {"error": str(json_err)})
                    output_payload["structured_payload_error"] = f"Failed to parse agent JSON output: {json_err}"
            
            intent.visual_assessment_text = raw_text

            return {
                "agent_name": self.agent_name,
                "agent_output": output_payload, 
                "status": "SUCCESS",
                "error_message": None
            }

        except Exception as e:
            intent.provenance.add_action(f"Agent '{self.agent_name}' (VisualHeritage) failed during LLM call or output processing.", 
                                         {"error_type": type(e).__name__, "error_message": str(e)})
            return {
                "agent_name": self.agent_name,
                "agent_output": None,
                "status": "FAILED",
                "error_message": f"Agent '{self.agent_name}' (VisualHeritage) failed: {type(e).__name__} - {str(e)}"
            }
    
    def _call_llm(self, prompt: str, config: dict) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config  # type: ignore
            )
            text = getattr(response, "text", None)
            if not text and hasattr(response, "candidates") and response.candidates:
                first_candidate = response.candidates[0]
                content = getattr(first_candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
            if not text or not isinstance(text, str):
                raise ValueError("No valid text response from Gemini API.")
            return text
        except Exception as e:
            print(f"ERROR in _call_llm: {e}")
            return ""
