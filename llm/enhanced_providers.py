"""
Enhanced implementations of Gemini and OpenRouter clients with 
improved error handling, monitoring, and retry logic.
"""

import requests
import time
from typing import Dict, Any, List, Optional, Union
from google import genai
from google.genai.types import GenerateContentConfigDict

from .enhanced_llm_client import (
    EnhancedLLMClient, LLMResponse, estimate_cost, logger
)


class EnhancedGeminiClient(EnhancedLLMClient):
    """Enhanced Gemini LLM client implementation with monitoring"""
    
    def __init__(self, api_key: str):
        super().__init__("gemini")
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self._availability_checked = False
        self._is_available = None
    
    async def _execute_request(self, contents: Union[str, List[Any]], 
                             config: Dict[str, Any], model: str,
                             request_id: str) -> LLMResponse:
        """Execute Gemini API request"""
        try:
            # Convert contents to proper format
            if isinstance(contents, str):
                contents = [contents]
            
            # Cast config for type safety
            from typing import cast
            gemini_config = cast(GenerateContentConfigDict, config)
            
            logger.debug(f"Gemini request {request_id}: model={model}, config={config}")
            
            start_time = time.time()
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=gemini_config
            )
            response_time = (time.time() - start_time) * 1000
            
            # Extract text from response
            text = self._extract_text_from_response(response)
            
            # Extract token usage (Gemini doesn't provide this directly)
            prompt_tokens = self._estimate_prompt_tokens(contents)
            completion_tokens = self._estimate_completion_tokens(text)
            
            # Estimate cost
            cost = estimate_cost("gemini", model, prompt_tokens, completion_tokens)
            
            return LLMResponse(
                text=text,
                model_used=model,
                provider="gemini",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                response_time_ms=int(response_time),
                estimated_cost_usd=cost,
                raw_response=response,
                request_id=request_id
            )
            
        except Exception as e:
            error_str = str(e).lower()
            
            # Categorize errors for better handling
            if any(term in error_str for term in ["quota", "limit", "exceeded"]):
                logger.error(f"Gemini quota/limit exceeded: {e}")
                self._is_available = False
                raise Exception(f"Gemini API quota exceeded: {e}")
            elif any(term in error_str for term in ["unauthorized", "invalid key", "403"]):
                logger.error(f"Gemini authentication error: {e}")
                raise Exception(f"Gemini API authentication failed: {e}")
            elif any(term in error_str for term in ["timeout", "network", "connection"]):
                logger.warning(f"Gemini network error: {e}")
                raise Exception(f"Gemini network error: {e}")
            else:
                logger.error(f"Gemini unexpected error: {e}")
                raise Exception(f"Gemini API error: {e}")
    
    def _extract_text_from_response(self, response) -> str:
        """Extract text from Gemini response with comprehensive fallback methods"""
        try:
            # Try direct text access
            if hasattr(response, 'text') and response.text:
                return response.text
            
            # Try candidates approach
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    content = candidate.content
                    if hasattr(content, 'parts') and content.parts:
                        text_parts = []
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_parts.append(part.text)
                        if text_parts:
                            return "".join(text_parts)
            
            # Try alternative response structure
            if hasattr(response, 'result') and hasattr(response.result, 'text'):
                return response.result.text
            
            # Log response structure for debugging
            logger.error(f"Unable to extract text from Gemini response. Response structure: {dir(response)}")
            raise ValueError("No valid text response from Gemini API")
            
        except Exception as e:
            logger.error(f"Error extracting text from Gemini response: {e}")
            raise ValueError(f"Failed to extract text from Gemini response: {e}")
    
    def _estimate_prompt_tokens(self, contents: Union[str, List[Any]]) -> int:
        """Estimate prompt tokens (rough approximation)"""
        if isinstance(contents, str):
            text = contents
        else:
            text = " ".join(str(item) for item in contents)
        
        # Rough estimation: ~4 characters per token
        return len(text) // 4
    
    def _estimate_completion_tokens(self, text: str) -> int:
        """Estimate completion tokens (rough approximation)"""
        return len(text) // 4
    
    def is_available(self) -> bool:
        """Check if Gemini is available with caching"""
        if self._availability_checked and self._is_available is not None:
            return self._is_available
        
        try:
            logger.info("Checking Gemini API availability...")
            
            # Test with a minimal request
            test_response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-05-20",
                contents=["Hi"],
                config={"temperature": 0.1, "max_output_tokens": 5}
            )
            
            # Try to extract text to ensure response is valid
            self._extract_text_from_response(test_response)
            
            self._is_available = True
            self._availability_checked = True
            logger.info("Gemini API is available")
            return True
            
        except Exception as e:
            error_str = str(e).lower()
            self._availability_checked = True
            
            if any(term in error_str for term in ["quota", "limit", "exceeded"]):
                self._is_available = False
                logger.error(f"Gemini API quota/limit reached: {e}")
            else:
                # For other errors, don't cache the result (might be temporary)
                self._availability_checked = False
                logger.warning(f"Gemini availability check failed (temporary): {e}")
                
            return False
    
    def reset_availability_cache(self):
        """Reset availability cache to force re-check"""
        self._availability_checked = False
        self._is_available = None


class EnhancedOpenRouterClient(EnhancedLLMClient):
    """Enhanced OpenRouter LLM client implementation with monitoring"""
    
    def __init__(self, api_key: str):
        super().__init__("openrouter")
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self._availability_checked = False
        self._is_available = None
        
        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/tim-mayoh/agentic-retrieval",
            "X-Title": "Agentic Retrieval Planning AI"
        })
    
    async def _execute_request(self, contents: Union[str, List[Any]], 
                             config: Dict[str, Any], model: str,
                             request_id: str) -> LLMResponse:
        """Execute OpenRouter API request"""
        try:
            # Convert contents to OpenAI chat format
            messages = self._convert_contents_to_messages(contents)
            
            # Map Gemini config to OpenAI config
            openai_config = self._map_config_to_openai(config)
            
            # Map Gemini model to OpenRouter model
            openrouter_model = self._map_gemini_model_to_openrouter(model)
            
            payload = {
                "model": openrouter_model,
                "messages": messages,
                **openai_config
            }
            
            logger.debug(f"OpenRouter request {request_id}: model={openrouter_model}, payload_size={len(str(payload))}")
            
            start_time = time.time()
            response = self.session.post(
                self.base_url,
                json=payload,
                timeout=300  # 5 minute timeout
            )
            response_time = (time.time() - start_time) * 1000
            
            # Handle HTTP errors
            if response.status_code == 429:
                self._is_available = False
                raise Exception(f"OpenRouter rate limit exceeded: {response.text}")
            elif response.status_code == 401:
                raise Exception(f"OpenRouter authentication failed: {response.text}")
            elif response.status_code == 403:
                raise Exception(f"OpenRouter access forbidden: {response.text}")
            elif response.status_code >= 500:
                raise Exception(f"OpenRouter server error ({response.status_code}): {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # Extract text from response
            if not data.get("choices") or not data["choices"][0].get("message"):
                raise Exception("Invalid response format from OpenRouter")
            
            text = data["choices"][0]["message"]["content"]
            if not text:
                raise Exception("Empty response from OpenRouter")
            
            # Extract token usage
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
            
            # Estimate cost
            cost = estimate_cost("openrouter", openrouter_model, prompt_tokens, completion_tokens)
            
            return LLMResponse(
                text=text,
                model_used=openrouter_model,
                provider="openrouter",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                response_time_ms=int(response_time),
                estimated_cost_usd=cost,
                raw_response=data,
                request_id=request_id
            )
            
        except requests.RequestException as e:
            error_str = str(e).lower()
            
            if any(term in error_str for term in ["quota", "limit", "429"]):
                self._is_available = False
                logger.error(f"OpenRouter quota/limit exceeded: {e}")
                raise Exception(f"OpenRouter API quota exceeded: {e}")
            elif any(term in error_str for term in ["timeout", "connection"]):
                logger.warning(f"OpenRouter network error: {e}")
                raise Exception(f"OpenRouter network error: {e}")
            else:
                logger.error(f"OpenRouter request error: {e}")
                raise Exception(f"OpenRouter API error: {e}")
        
        except Exception as e:
            logger.error(f"OpenRouter unexpected error: {e}")
            raise Exception(f"OpenRouter error: {e}")
    
    def _convert_contents_to_messages(self, contents: Union[str, List[Any]]) -> List[Dict[str, str]]:
        """Convert Gemini contents format to OpenAI messages format"""
        if isinstance(contents, str):
            return [{"role": "user", "content": contents}]
        
        # Handle list of contents
        messages = []
        combined_content = ""
        
        for content in contents:
            if isinstance(content, str):
                combined_content += content + "\n"
            elif isinstance(content, dict):
                # Handle potential structured content
                if "text" in content:
                    combined_content += content["text"] + "\n"
                else:
                    combined_content += str(content) + "\n"
            else:
                combined_content += str(content) + "\n"
        
        return [{"role": "user", "content": combined_content.strip()}]
    
    def _map_config_to_openai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Map Gemini config to OpenAI/OpenRouter config"""
        openai_config = {}
        
        # Direct mappings
        if "temperature" in config:
            openai_config["temperature"] = config["temperature"]
        
        if "max_output_tokens" in config:
            openai_config["max_tokens"] = config["max_output_tokens"]
        
        if "top_p" in config:
            openai_config["top_p"] = config["top_p"]
        
        # Handle JSON mode
        if config.get("response_mime_type") == "application/json":
            openai_config["response_format"] = {"type": "json_object"}
        
        # Handle thinking config (Gemini-specific, ignore for OpenRouter)
        if "thinkingConfig" in config:
            logger.debug("Ignoring Gemini-specific thinkingConfig for OpenRouter")
        
        return openai_config
    
    def _map_gemini_model_to_openrouter(self, gemini_model: str) -> str:
        """Map Gemini model names to OpenRouter model names"""
        model_mapping = {
            "gemini-2.5-flash-preview-05-20": "google/gemini-2.0-flash-exp:free",
            "gemini-1.5-pro-latest": "google/gemini-pro-1.5", 
            "gemini-1.5-flash-latest": "google/gemini-flash-1.5",
            "gemini-pro": "google/gemini-pro",
            "gemini-pro-vision": "google/gemini-pro-vision"
        }
        
        mapped_model = model_mapping.get(gemini_model, "google/gemini-2.0-flash-exp:free")
        if mapped_model != gemini_model:
            logger.info(f"Mapped Gemini model '{gemini_model}' to OpenRouter model '{mapped_model}'")
        
        return mapped_model
    
    def is_available(self) -> bool:
        """Check if OpenRouter is available with caching"""
        if self._availability_checked and self._is_available is not None:
            return self._is_available
        
        try:
            logger.info("Checking OpenRouter API availability...")
            
            payload = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
                "temperature": 0.1
            }
            
            response = self.session.post(
                self.base_url,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                # Validate response format
                data = response.json()
                if data.get("choices") and data["choices"][0].get("message"):
                    self._is_available = True
                    self._availability_checked = True
                    logger.info("OpenRouter API is available")
                    return True
                else:
                    raise Exception("Invalid response format")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            error_str = str(e).lower()
            self._availability_checked = True
            
            if any(term in error_str for term in ["quota", "limit", "429"]):
                self._is_available = False
                logger.error(f"OpenRouter API quota/limit reached: {e}")
            else:
                # For other errors, don't cache the result
                self._availability_checked = False
                logger.warning(f"OpenRouter availability check failed (temporary): {e}")
                
            return False
    
    def reset_availability_cache(self):
        """Reset availability cache to force re-check"""
        self._availability_checked = False
        self._is_available = None
    
    def __del__(self):
        """Cleanup session on destruction"""
        if hasattr(self, 'session'):
            self.session.close()
