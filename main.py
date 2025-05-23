# main.py
import json
import psycopg2
from dotenv import load_dotenv
import time
import os

# Modular imports
from db_manager import DatabaseManager
from mrm.mrm_orchestrator import MRMOrchestrator # MODIFIED: Renamed MRM to MRMOrchestrator
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
from config import GEMINI_API_KEY, REPORT_TEMPLATE_DIR, POLICY_KB_DIR, MC_ONTOLOGY_DIR, DB_CONFIG # ADDED DB_CONFIG

if __name__ == "__main__":
    start_time = time.time()
    load_dotenv()
    if not GEMINI_API_KEY: print("CRITICAL: GEMINI_API_KEY is not set. Exiting."); exit(1)
    # ADDED: Check for DB_CONFIG components
    if not all(DB_CONFIG.get(k) for k in ['dbname', 'user', 'password', 'host', 'port']):
        print("CRITICAL: Database configuration is incomplete. Check .env file for DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT. Exiting.")
        exit(1)

    # Use correct config variable names for KB dirs
    for kb_dir_path in [REPORT_TEMPLATE_DIR, POLICY_KB_DIR, MC_ONTOLOGY_DIR]:
        if not os.path.exists(kb_dir_path): os.makedirs(kb_dir_path); print(f"Created KB directory: {kb_dir_path}")
    
    db_man = None # Initialize db_man outside try block for finally clause
    try:
        print("\n--- Initializing Database Manager ---")
        db_man = DatabaseManager()
        
        print("\n--- Initializing Knowledge Base Managers ---")
        report_template_man = ReportTemplateManager()
        mc_ontology_man = MaterialConsiderationOntology()
        policy_man = PolicyManager(db_man) # PolicyManager now requires db_man

        print("\n--- Ensuring Schema and Ingesting Minimal Sample Data (if first run) ---")
        schema_file_path = "./schema.sql";
        try:
            with open(schema_file_path, "r") as f_schema:
                if db_man.conn is not None:
                    cur = db_man.conn.cursor()
                    # Check if 'documents' table exists to infer if schema was run
                    cur.execute("SELECT to_regclass('public.documents');")
                    table_exists = cur.fetchone()[0]
                    cur.close()
                else:
                    # This case should ideally not be reached if DatabaseManager() succeeded
                    raise RuntimeError("Database connection is not established after DatabaseManager initialization.")

                if not table_exists:
                    print("Executing schema.sql...")
                    # Read the entire schema file
                    sql_commands = f_schema.read()
                    # Split commands if necessary, though execute_query might handle multi-statement SQL
                    # For simplicity, assuming execute_query can handle it or schema.sql is single/batchable
                    db_man.execute_query(sql_commands) # Pass the whole content
                    print("Schema executed.")
                    
                    # Ingest sample data only if schema was just created
                    print("Ingesting minimal sample data for initial scan...")
                    ug_doc_id = db_man.add_document(filename="UserGuide_EC.pdf", title="Earls Court User Guide", document_type="UserGuide", source="ECDC_EarlsCourt_App", page_count=54)
                    if ug_doc_id:
                        db_man.add_document_chunk(doc_id=ug_doc_id, page_number=1, chunk_text="This major hybrid application for Earls Court proposes 4000 homes and extensive commercial space, including significant public realm and measures for sustainability and heritage conservation.", section="Executive Summary")
                    
                    es_nts_id = db_man.add_document(filename="ES_NTS_EC.pdf", title="ES Non-Technical Summary", document_type="ES_NTS", source="ECDC_EarlsCourt_App", page_count=20)
                    if es_nts_id:
                        db_man.add_document_chunk(doc_id=es_nts_id, page_number=2, chunk_text="The Environmental Statement covers impacts on: Housing, Design, Townscape, Heritage, Transport, Air Quality, Noise, Biodiversity, Flood Risk, Socio-economics.", section="ES Scope")
                    
                    # ADDED: Ingest sample policy data via PolicyManager
                    print("Ingesting sample policy data...")
                    policy_man._ingest_sample_policies_from_json() # Call the method to ingest policies
                    print("Minimal sample data (application & policy) ingested.")
                else: 
                    print("Tables exist. Skipping schema/data ingestion.")
        except FileNotFoundError: 
            print(f"ERROR: schema.sql not found at {schema_file_path}. Ensure it's in the same directory as main.py."); exit(1)
        except psycopg2.Error as db_err: # More specific error handling for DB operations
            print(f"ERROR during schema/data setup (DB operation): {db_err}")
            # db_man.conn might be None or closed, or in an unusable state
            if db_man and db_man.conn: 
                try: db_man.conn.rollback() # Attempt to rollback if transaction was open
                except: pass # Ignore rollback errors
            exit(1) # Exit on schema/data setup errors
        except Exception as schema_e: 
            print(f"ERROR during schema/data setup (General): {schema_e}"); 
            import traceback; traceback.print_exc()
            exit(1) # Exit on schema/data setup errors

        print("\n--- Initializing MRM Orchestrator ---")
        report_type_key_to_use = "Default_MajorHybrid" # Example report type
        application_references_to_use = ["ECDC_EarlsCourt_App"] # Example application reference

        # Use the renamed MRMOrchestrator class
        mrm_instance = MRMOrchestrator(db_man, report_template_man, mc_ontology_man, policy_man)

        print(f"\n--- Starting Generalized Report Orchestration for type: {report_type_key_to_use} ---")
        # MODIFIED: Corrected method signature call
        final_report = mrm_instance.orchestrate_report_generation(report_type_key=report_type_key_to_use, application_refs=application_references_to_use, application_display_name="Earl\'s Court Development")

        print("\n\n--- FINAL DRAFT REPORT (GEMINI - GENERALIZED ENGINE V9 - Policy DB & Agents) ---") # MODIFIED Version
        # Ensure default=str for UUIDs and other non-serializable types if any
        print(json.dumps(final_report, indent=2, default=str))
        
        print("\n--- PROVENANCE SUMMARY ---")
        # MODIFIED: Access overall_provenance_logs and print each log
        if hasattr(mrm_instance, 'overall_provenance_logs') and mrm_instance.overall_provenance_logs:
            for log_entry in mrm_instance.overall_provenance_logs:
                print(str(log_entry)) # Assuming ProvenanceLog has a __str__ method
        else:
            print("No provenance logs recorded by the orchestrator.")

    except psycopg2.Error as db_conn_err: 
        print(f"CRITICAL DB CONNECTION/OPERATION ERROR: {db_conn_err}")
        import traceback; traceback.print_exc()
    except ValueError as val_err: 
        print(f"CRITICAL CONFIGURATION/VALUE ERROR: {val_err}")
        import traceback; traceback.print_exc()
    except RuntimeError as rt_err: # Catch runtime errors, e.g., from DB connection issues
        print(f"CRITICAL RUNTIME ERROR: {rt_err}")
        import traceback; traceback.print_exc()
    except Exception as e: 
        print(f"UNEXPECTED CRITICAL ERROR IN MAIN EXECUTION: {e}")
        import traceback; traceback.print_exc()
    finally:
        if db_man: 
            print("\n--- Closing Database Connection ---")
            db_man.close()
        end_time = time.time()
        print(f"\nTotal execution time: {end_time - start_time:.2f} seconds")
