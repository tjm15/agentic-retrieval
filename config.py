# config.py
import os
from dotenv import load_dotenv
from typing import cast, Dict, Any

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not GEMINI_API_KEY:
    print("CRITICAL: GEMINI_API_KEY not found in environment variables. Please set it in a .env file or environment.")
    # For library use, you might not exit here, but main.py will check.

if not OPENROUTER_API_KEY:
    print("WARNING: OPENROUTER_API_KEY not found. Fallback LLM provider will not be available.")

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "tpa"),
    "user": os.getenv("DB_USER", "tpa"),
    "password": os.getenv("DB_PASSWORD", "tpa"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

MRM_MODEL_NAME = "gemini-2.5-flash-preview-05-20"
SUBSIDIARY_AGENT_MODEL_NAME = "gemini-2.5-flash-preview-05-20"
GEMINI_PRO_VISION_MODEL_NAME = "gemini-2.5-flash-preview-05-20" # ADDED

MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION = 2
MAX_CHUNKS_FOR_CONTEXT = 25
MAX_TOKENS_PER_GEMINI_CALL_APPROX = 1000000 # For Gemini 1.5 Pro. Adjust if using 1.0 Pro (30k)

EMBEDDING_DIMENSION = 768

# Cache Configuration
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_MAX_AGE_HOURS = int(os.getenv("CACHE_MAX_AGE_HOURS", "24"))
CACHE_DIR = os.getenv("CACHE_DIR", "./cache/gemini_responses")

REPORT_TEMPLATE_DIR = "./report_templates/"
POLICY_KB_DIR = "./policy_kb/" # Source for initial policy ingestion
MC_ONTOLOGY_DIR = "./mc_ontology_data/"

# LLM Generation Configuration
DEFAULT_LLM_TEMPERATURE_DETERMINISTIC = 0.05
DEFAULT_LLM_TEMPERATURE_CREATIVE = 0.4

# Parallel Async LLM Configuration
PARALLEL_ASYNC_LLM_MODE = os.getenv("PARALLEL_ASYNC_LLM_MODE", "true").lower() == "true"
MAX_CONCURRENT_LLM_CALLS = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "15"))  # Increased from 3 to 15 for better throughput
LLM_CALL_TIMEOUT_SECONDS = int(os.getenv("LLM_CALL_TIMEOUT_SECONDS", "600"))  # Increased to 10 minutes per LLM call

# Centralized Gemini LLM config builder

def build_gemini_generation_config(
    temperature=None,
    max_output_tokens=None,
    top_p=None,
    top_k=None,
    response_mime_type=None,
    **kwargs
) -> Dict[str, Any]:
    config = {}
    if temperature is not None:
        config["temperature"] = temperature
    if max_output_tokens is not None:
        config["max_output_tokens"] = max_output_tokens
    if top_p is not None:
        config["top_p"] = top_p
    if top_k is not None:
        config["top_k"] = top_k
    if response_mime_type is not None:
        config["response_mime_type"] = response_mime_type
    config.update(kwargs)
    return config

# Standard configs for each use case
MRM_CORE_GEN_CONFIG = build_gemini_generation_config(
    temperature=DEFAULT_LLM_TEMPERATURE_DETERMINISTIC,
    thinkingConfig={"includeThoughts": True, "thinkingBudget": 256}
)
INTENT_DEFINER_GEN_CONFIG = build_gemini_generation_config(
    temperature=0.0,
    response_mime_type="application/json"
)
SUBSIDIARY_AGENT_GEN_CONFIG = build_gemini_generation_config(
    temperature=DEFAULT_LLM_TEMPERATURE_CREATIVE
)
VISUAL_HERITAGE_AGENT_GEN_CONFIG = build_gemini_generation_config(
    temperature=DEFAULT_LLM_TEMPERATURE_CREATIVE
)
APP_SCAN_GEN_CONFIG = build_gemini_generation_config(
    temperature=0.2,
    response_mime_type="application/json"
)

# LLM Client Factory
def create_llm_client():
    """Create and return the configured LLM client with fallback support"""
    from llm.llm_client import FallbackLLMClient, GeminiClient, OpenRouterClient
    
    # Create primary and fallback clients
    primary_client = None
    fallback_clients = []
    
    if GEMINI_API_KEY:
        primary_client = GeminiClient(GEMINI_API_KEY)
    
    if OPENROUTER_API_KEY:
        fallback_clients.append(OpenRouterClient(OPENROUTER_API_KEY))
    
    if not primary_client and not fallback_clients:
        raise ValueError("No LLM API keys configured. Please set GEMINI_API_KEY and/or OPENROUTER_API_KEY")
    
    if not primary_client and fallback_clients:
        # If no primary client, use the first fallback as primary
        primary_client = fallback_clients.pop(0)

    assert primary_client is not None, "Primary client should not be None at this point"
    return FallbackLLMClient(primary_client, fallback_clients)

def create_enhanced_llm_client():
    """Create and return the enhanced LLM client with improved monitoring and fallback"""
    try:
        from llm.enhanced_config import create_enhanced_llm_client as create_enhanced
        from cache.gemini_cache import GeminiResponseCache
        
        cache_impl = GeminiResponseCache() if CACHE_ENABLED else None
        return create_enhanced(cache_impl=cache_impl)
    except ImportError as e:
        print(f"WARN: Enhanced LLM client not available ({e}), falling back to standard client")
        return create_llm_client()

# Environment variable to choose LLM client implementation
USE_ENHANCED_LLM_CLIENT = os.getenv("USE_ENHANCED_LLM_CLIENT", "false").lower() == "true"
