# config.py
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("CRITICAL: GEMINI_API_KEY not found in environment variables. Please set it in a .env file or environment.")
    # For library use, you might not exit here, but main.py will check.

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "planning_ai_db"),
    "user": os.getenv("DB_USER", "your_user"),
    "password": os.getenv("DB_PASSWORD", "your_password"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

MRM_MODEL_NAME = "gemini-1.5-pro-latest"
SUBSIDIARY_AGENT_MODEL_NAME = "gemini-1.5-flash-latest"
GEMINI_PRO_VISION_MODEL_NAME = "gemini-pro-vision" # ADDED

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

MRM_CORE_GEN_CONFIG = { # For NodeProcessor's synthesis
    "temperature": DEFAULT_LLM_TEMPERATURE_DETERMINISTIC,
    "request_options": {'timeout': 300}
}
INTENT_DEFINER_GEN_CONFIG = { # For IntentDefiner's LLM calls
    "temperature": 0.0,
    "response_mime_type": "application/json",
    "request_options": {'timeout': 240}
}
SUBSIDIARY_AGENT_GEN_CONFIG = { # For Subsidiary Agents
    "temperature": DEFAULT_LLM_TEMPERATURE_CREATIVE,
    "request_options": {'timeout': 120}
}
VISUAL_HERITAGE_AGENT_GEN_CONFIG = { # ADDED
    "temperature": DEFAULT_LLM_TEMPERATURE_CREATIVE, 
    "request_options": {'timeout': 180} # Longer timeout for potential image processing
}
APP_SCAN_GEN_CONFIG = { # For initial application scan
    "temperature": 0.2,
    "response_mime_type": "application/json",
    "request_options": {'timeout': 180}
}
