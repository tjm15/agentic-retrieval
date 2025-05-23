# main.py
import json
import psycopg2
from dotenv import load_dotenv
import time
import os
import google.generativeai as genai # For genai.configure

# Modular imports
from db_manager import DatabaseManager
from mrm.mrm_orchestrator import MRM # Changed import
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from config import GEMINI_API_KEY, REPORT_TEMPLATE_DIR, POLICY_KB_DIR, MC_ONTOLOGY_DIR

if __name__ == "__main__":
    start_time = time.time()
    load_dotenv()
    if not GEMINI_API_KEY: print("CRITICAL: GEMINI_API_KEY is not set. Exiting."); exit(1)
    genai.configure(api_key=GEMINI_API_KEY) # Configure Gemini globally here

    # Ensure knowledge base directories exist
    for kb_dir_path in [REPORT_TEMPLATE_DIR, POLICY_KB_DIR, MC_ONTOLOGY_DIR]:
        if not os.path.exists(kb_dir_path): os.makedirs(kb_dir_path); print(f"Created KB directory: {kb_dir_path}")
    
    # Initialize managers - they will create default files if needed
    print("--- Initializing Knowledge Base Managers ---")
    report_template_man = ReportTemplateManager()
    mc_ontology_man = MaterialConsiderationOntology()
    policy_man = PolicyManager()

    db_man = None
    try:
        print("\n--- Initializing Database Manager ---")
        db_man = DatabaseManager()

        print("\n--- Ensuring Schema and Ingesting Minimal Sample Data ---")
        schema_file_path = "./schema.sql";
        # (Schema and sample data ingestion logic - same as previous)
        try:
            with open(schema_file_path, "r") as f_schema:
                cur = db_man.conn.cursor(); cur.execute("SELECT to_regclass('public.documents');"); table_exists = cur.fetchone()[0]; cur.close()
                if not table_exists:
                    print("Executing schema.sql..."); db_man.execute_query(f_schema.read()); print("Schema executed.")
                    ug_doc_id = db_man.add_document("UserGuide_EC.pdf", "Earls Court User Guide", "UserGuide", "ECDC_EarlsCourt_App", 54)
                    db_man.add_document_chunk(ug_doc_id, 1, "This major hybrid application for Earls Court proposes 4000 homes and extensive commercial space, including significant public realm and measures for sustainability and heritage conservation.", "Executive Summary")
                    es_nts_id = db_man.add_document("ES_NTS_EC.pdf", "ES Non-Technical Summary", "ES_NTS", "ECDC_EarlsCourt_App", 20)
                    db_man.add_document_chunk(es_nts_id, 2, "The Environmental Statement covers impacts on: Housing, Design, Townscape, Heritage, Transport, Air Quality, Noise, Biodiversity, Flood Risk, Socio-economics.", "ES Scope")
                    print("Minimal sample data ingested for scan.")
                else: print("Tables exist. Skipping schema/data ingestion.")
        except FileNotFoundError: print(f"ERROR: schema.sql not found at {schema_file_path}."); exit(1)
        except Exception as schema_e: print(f"ERROR during schema/data setup: {schema_e}")


        print("\n--- Initializing MRM Orchestrator ---")
        report_type_key_to_use = "Default_MajorHybrid" # This must match a "report_type_id" in a template JSON
        application_references_to_use = ["ECDC_EarlsCourt_App"] # Example

        mrm_instance = MRM(db_man, report_template_man, mc_ontology_man, policy_man) # Pass all managers

        print(f"\n--- Starting Generalized Report Orchestration for type: {report_type_key_to_use} ---")
        final_report = mrm_instance.orchestrate_full_report_generation(report_type_key_to_use, application_references_to_use)

        print("\n\n--- FINAL DRAFT REPORT (GEMINI - GENERALIZED ENGINE V7) ---")
        print(json.dumps(final_report, indent=2, default=str))
        mrm_instance.print_provenance_summary()

    except psycopg2.Error as db_conn_err: print(f"CRITICAL DB ERROR: {db_conn_err}")
    except ValueError as val_err: print(f"CONFIG/VALUE ERROR: {val_err}") # Catches template/API key issues
    except Exception as e: print(f"UNEXPECTED ERROR IN MAIN: {e}"); import traceback; traceback.print_exc()
    finally:
        if db_man: print("\n--- Closing Database Connection ---"); db_man.close()
        end_time = time.time()
        print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")
