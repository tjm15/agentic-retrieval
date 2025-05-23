# config.py
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    # In a real app, you might not want to raise an error immediately if it's a library
    # but for this script, it's essential.
    print("CRITICAL: GEMINI_API_KEY not found in environment variables. Please set it in a .env file or environment.")
    # exit(1) # Exiting here might be too abrupt if used as a library. Let main.py handle exit.


DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "planning_ai_db"),
    "user": os.getenv("DB_USER", "your_user"),
    "password": os.getenv("DB_PASSWORD", "your_password"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

MRM_MODEL_NAME = "gemini-2.5-pro-preview-05-06"
SUBSIDIARY_AGENT_MODEL_NAME = "gemini-2.5-flash-preview-05-20"

MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION = 2
MAX_CHUNKS_FOR_CONTEXT = 25 # Reduced for potentially more focused context
MAX_TOKENS_PER_GEMINI_CALL_APPROX = 1000000 # For Gemini 1.5 Pro. Adjust if using 1.0 Pro (30k)

EMBEDDING_DIMENSION = 768

REPORT_TEMPLATE_DIR = "./report_templates/"
POLICY_KB_DIR = "./policy_kb/"
MC_ONTOLOGY_DIR = "./mc_ontology_data/"
