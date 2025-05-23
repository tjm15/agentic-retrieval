# config.py
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("CRITICAL: GEMINI_API_KEY not found in environment variables. Please set it in a .env file or environment.")
    # For library use, you might not exit here, but main.py will check.

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

REPORT_TEMPLATE_DIR = "./report_templates/"
POLICY_KB_DIR = "./policy_kb/" # Source for initial policy ingestion
MC_ONTOLOGY_DIR = "./mc_ontology_data/"

# LLM Generation Configuration
DEFAULT_LLM_TEMPERATURE_DETERMINISTIC = 0.05
DEFAULT_LLM_TEMPERATURE_CREATIVE = 0.4

# Centralized Gemini LLM config builder

def build_gemini_generation_config(
    temperature=None,
    max_output_tokens=None,
    top_p=None,
    top_k=None,
    response_mime_type=None,
    **kwargs
):
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
