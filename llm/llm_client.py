# llm/llm_client.py
import json
import time
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from google import genai
from google.genai.types import GenerateContentConfigDict
import requests


@dataclass
class LLMResponse:
    """Standardized response format for all LLM providers"""
    text: str
    model_used: str
    provider: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    raw_response: Optional[Any] = None


class LLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    def generate_content(self, 
                        contents: Union[str, List[Any]], 
                        config: Dict[str, Any],
                        model: str) -> LLMResponse:
        """Generate content using the LLM"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is available"""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the LLM provider"""
        pass


class GeminiClient(LLMClient):
    """Gemini LLM client implementation"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self._available = None
    
    def generate_content(self, 
                        contents: Union[str, List[Any]], 
                        config: Dict[str, Any],
                        model: str) -> LLMResponse:
        """Generate content using Gemini"""
        try:
            # Convert contents to proper format
            if isinstance(contents, str):
                contents = [contents]
            
            # Cast config for type safety
            from typing import cast
            gemini_config = cast(GenerateContentConfigDict, config)
            
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=gemini_config
            )
            
            # Extract text from response
            text = self._extract_text_from_response(response)
            
            return LLMResponse(
                text=text,
                model_used=model,
                provider="gemini",
                raw_response=response
            )
            
        except Exception as e:
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                # Mark as unavailable if quota exceeded
                self._available = False
            raise e
    
    def _extract_text_from_response(self, response) -> str:
        """Extract text from Gemini response with fallback methods"""
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
        
        raise ValueError("No valid text response from Gemini API")
    
    def is_available(self) -> bool:
        """Check if Gemini is available"""
        if self._available is not None:
            return self._available
        
        try:
            # Test with a simple request
            test_response = self.client.models.generate_content(
                model="gemini-2.5-flash-preview-05-20",
                contents=["Test"],
                config={"temperature": 0.1, "max_output_tokens": 10}
            )
            self._available = True
            return True
        except Exception as e:
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                self._available = False
                print(f"WARN: Gemini API quota/limit reached: {e}")
                return False
            # Other errors might be temporary
            print(f"WARN: Gemini availability check failed: {e}")
            return False
    
    @property
    def provider_name(self) -> str:
        return "gemini"


class OpenRouterClient(LLMClient):
    """OpenRouter LLM client implementation"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self._available = None
    
    def generate_content(self, 
                        contents: Union[str, List[Any]], 
                        config: Dict[str, Any],
                        model: str) -> LLMResponse:
        """Generate content using OpenRouter"""
        try:
            # Convert contents to OpenAI chat format
            messages = self._convert_contents_to_messages(contents)
            
            # Map Gemini config to OpenAI config
            openai_config = self._map_config_to_openai(config)
            
            # Map Gemini model to OpenRouter model
            openrouter_model = self._map_gemini_model_to_openrouter(model)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/tim-mayoh/agentic-retrieval",
                "X-Title": "Agentic Retrieval Planning AI"
            }
            
            payload = {
                "model": openrouter_model,
                "messages": messages,
                **openai_config
            }
            
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=300  # 5 minute timeout
            )
            
            if response.status_code == 429:
                # Rate limit or quota exceeded
                self._available = False
                raise Exception(f"OpenRouter rate limit/quota exceeded: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # Extract text from response
            text = data["choices"][0]["message"]["content"]
            
            # Extract token usage if available
            usage = data.get("usage", {})
            
            return LLMResponse(
                text=text,
                model_used=openrouter_model,
                provider="openrouter",
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                raw_response=data
            )
            
        except requests.RequestException as e:
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                self._available = False
            raise e
    
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
                # Handle potential structured content (images, etc.)
                # For now, just convert to string representation
                combined_content += str(content) + "\n"
            else:
                combined_content += str(content) + "\n"
        
        return [{"role": "user", "content": combined_content.strip()}]
    
    def _map_config_to_openai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Map Gemini config to OpenAI/OpenRouter config"""
        openai_config = {}
        
        if "temperature" in config:
            openai_config["temperature"] = config["temperature"]
        
        if "max_output_tokens" in config:
            openai_config["max_tokens"] = config["max_output_tokens"]
        
        if "top_p" in config:
            openai_config["top_p"] = config["top_p"]
        
        # Handle JSON mode
        if config.get("response_mime_type") == "application/json":
            openai_config["response_format"] = {"type": "json_object"}
        
        return openai_config
    
    def _map_gemini_model_to_openrouter(self, gemini_model: str) -> str:
        """Map Gemini model names to OpenRouter model names"""
        # Map common Gemini models to high-quality OpenRouter alternatives
        model_mapping = {
            "gemini-2.5-flash-preview-05-20": "google/gemini-2.0-flash-exp:free",
            "gemini-1.5-pro-latest": "google/gemini-pro-1.5",
            "gemini-1.5-flash-latest": "google/gemini-flash-1.5",
            "gemini-pro": "google/gemini-pro",
            "gemini-pro-vision": "google/gemini-pro-vision"
        }
        
        return model_mapping.get(gemini_model, "google/gemini-2.0-flash-exp:free")
    
    def is_available(self) -> bool:
        """Check if OpenRouter is available"""
        if self._available is not None:
            return self._available
        
        try:
            # Test with a simple request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/tim-mayoh/agentic-retrieval",
                "X-Title": "Agentic Retrieval Planning AI"
            }
            
            payload = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [{"role": "user", "content": "Test"}],
                "max_tokens": 10,
                "temperature": 0.1
            }
            
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                self._available = True
                return True
            else:
                self._available = False
                print(f"WARN: OpenRouter availability check failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"WARN: OpenRouter availability check failed: {e}")
            self._available = False
            return False
    
    @property
    def provider_name(self) -> str:
        return "openrouter"


class FallbackLLMClient:
    """LLM client with automatic fallback between providers"""
    
    def __init__(self, primary_client: LLMClient, fallback_clients: List[LLMClient]):
        self.primary_client = primary_client
        self.fallback_clients = fallback_clients
        self.current_client = primary_client
        self.failed_clients = set()
    
    def generate_content(self, 
                        contents: Union[str, List[Any]], 
                        config: Dict[str, Any],
                        model: str) -> LLMResponse:
        """Generate content with automatic fallback"""
        
        # Try current client first
        if self.current_client not in self.failed_clients:
            try:
                if self.current_client.is_available():
                    response = self.current_client.generate_content(contents, config, model)
                    print(f"INFO: Using {self.current_client.provider_name} for LLM call")
                    return response
                else:
                    print(f"WARN: {self.current_client.provider_name} not available, trying fallback")
                    self.failed_clients.add(self.current_client)
            except Exception as e:
                print(f"WARN: {self.current_client.provider_name} failed: {e}")
                self.failed_clients.add(self.current_client)
        
        # Try fallback clients
        for fallback_client in self.fallback_clients:
            if fallback_client in self.failed_clients:
                continue
                
            try:
                if fallback_client.is_available():
                    response = fallback_client.generate_content(contents, config, model)
                    print(f"INFO: Using fallback {fallback_client.provider_name} for LLM call")
                    self.current_client = fallback_client  # Switch to working fallback
                    return response
                else:
                    print(f"WARN: Fallback {fallback_client.provider_name} not available")
                    self.failed_clients.add(fallback_client)
            except Exception as e:
                print(f"WARN: Fallback {fallback_client.provider_name} failed: {e}")
                self.failed_clients.add(fallback_client)
        
        # All clients failed
        raise Exception("All LLM providers failed or are unavailable")
    
    def reset_failed_clients(self):
        """Reset failed clients list to retry them"""
        self.failed_clients.clear()
        self.current_client = self.primary_client
    
    @property
    def provider_name(self) -> str:
        return f"{self.current_client.provider_name} (with fallback)"
