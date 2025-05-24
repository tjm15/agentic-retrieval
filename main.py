# main.py
import json
import psycopg2
from dotenv import load_dotenv
import time
import os
from datetime import datetime
from google import genai

# Modular imports
from db_manager import DatabaseManager
from mrm.mrm_orchestrator import MRMOrchestrator # MODIFIED: Renamed MRM to MRMOrchestrator
from knowledge_base.policy_manager import PolicyManager
from knowledge_base.report_template_manager import ReportTemplateManager
from knowledge_base.material_consideration_ontology import MaterialConsiderationOntology
import importlib
import config

if __name__ == "__main__":
    load_dotenv()  # Ensure .env is loaded before any config import
    importlib.reload(config)
    from config import GEMINI_API_KEY, REPORT_TEMPLATE_DIR, POLICY_KB_DIR, MC_ONTOLOGY_DIR, DB_CONFIG
    print("DEBUG DB_CONFIG:", DB_CONFIG)  # DEBUG PRINT
    start_time = time.time()
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

        # Configuration for parallel processing
        USE_PARALLEL_PROCESSING = os.getenv("USE_PARALLEL_PROCESSING", "true").lower() == "true"
        MAX_PARALLEL_NODES = int(os.getenv("MAX_PARALLEL_NODES", "12"))  # Increased from 5 to 12 for better concurrency

        print(f"\n--- Starting {'Parallel' if USE_PARALLEL_PROCESSING else 'Sequential'} Report Orchestration for type: {report_type_key_to_use} ---")
        print(f"--- Max parallel nodes: {MAX_PARALLEL_NODES if USE_PARALLEL_PROCESSING else 'N/A (sequential)'} ---")

        if USE_PARALLEL_PROCESSING:
            # Use async orchestrator with parallel processing
            import asyncio
            async def run_async_orchestration():
                return await mrm_instance.generate_async_report(
                    application_refs=application_references_to_use,
                    app_display_name="Earl's Court Development",
                    report_type=report_type_key_to_use,
                    max_parallel_nodes=MAX_PARALLEL_NODES
                )
            final_report = asyncio.run(run_async_orchestration())
        else:
            # Use synchronous orchestrator (original behavior)
            final_report = mrm_instance.orchestrate_report_generation(
                report_type_key=report_type_key_to_use, 
                application_refs=application_references_to_use, 
                application_display_name="Earl's Court Development"
            )

        processing_mode = "PARALLEL" if USE_PARALLEL_PROCESSING else "SEQUENTIAL"
        parallel_info = f" (Max Parallel: {MAX_PARALLEL_NODES})" if USE_PARALLEL_PROCESSING else ""
        print(f"\n\n--- FINAL DRAFT REPORT (GEMINI - GENERALIZED ENGINE V9 - {processing_mode} PROCESSING{parallel_info}) ---")
        
        # Generate timestamp for file outputs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = "output_reports"
        os.makedirs(output_dir, exist_ok=True)
        
        # Prepare file paths
        report_file = os.path.join(output_dir, f"final_report_{timestamp}.json")
        provenance_file = os.path.join(output_dir, f"provenance_logs_{timestamp}.txt")
        summary_file = os.path.join(output_dir, f"performance_summary_{timestamp}.txt")
        
        # Handle different report formats (sync vs async)
        if isinstance(final_report, dict) and "status" in final_report:
            # Async format includes metadata
            print(f"Processing Status: {final_report.get('status', 'unknown')}")
            if final_report.get("report_metadata"):
                metadata = final_report["report_metadata"]
                print(f"Total Nodes: {metadata.get('total_nodes', 'unknown')}")
                print(f"Parallel Processing: {metadata.get('parallel_processing', False)}")
                if metadata.get('parallel_processing'):
                    print(f"Max Parallel Nodes Used: {metadata.get('max_parallel_nodes', 'unknown')}")
                print(f"Processing Time: {metadata.get('total_elapsed_seconds', 'unknown')} seconds")
            print("\n--- REPORT CONTENT ---")
        
        # Save final report to file
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(final_report, f, indent=2, default=str, ensure_ascii=False)
            print(f"✅ Final report saved to: {report_file}")
        except Exception as e:
            print(f"❌ Error saving report to file: {e}")
        
        # Ensure default=str for UUIDs and other non-serializable types if any
        print(json.dumps(final_report, indent=2, default=str))
        
        # Save and display provenance logs
        provenance_content = []
        print("\n--- PROVENANCE SUMMARY ---")
        # MODIFIED: Access overall_provenance_logs and print each log
        if hasattr(mrm_instance, 'overall_provenance_logs') and mrm_instance.overall_provenance_logs:
            for log_entry in mrm_instance.overall_provenance_logs:
                log_str = str(log_entry)
                print(log_str) # Assuming ProvenanceLog has a __str__ method
                provenance_content.append(log_str)
        else:
            no_logs_msg = "No provenance logs recorded by the orchestrator."
            print(no_logs_msg)
            provenance_content.append(no_logs_msg)
            
        # Save provenance logs to file
        try:
            with open(provenance_file, 'w', encoding='utf-8') as f:
                f.write(f"PROVENANCE LOGS - Generated: {datetime.now().isoformat()}\n")
                f.write(f"Processing Mode: {processing_mode}{parallel_info}\n")
                f.write("=" * 80 + "\n\n")
                for log_content in provenance_content:
                    f.write(log_content + "\n\n")
            print(f"✅ Provenance logs saved to: {provenance_file}")
        except Exception as e:
            print(f"❌ Error saving provenance logs: {e}")
            
        # Generate and save performance summary
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"MRM SYSTEM PERFORMANCE SUMMARY\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                
                # Extract performance metrics
                if isinstance(final_report, dict):
                    if "report_metadata" in final_report:
                        metadata = final_report["report_metadata"]
                        f.write(f"PROCESSING CONFIGURATION:\n")
                        f.write(f"- Mode: {processing_mode}\n")
                        f.write(f"- Parallel Processing: {metadata.get('parallel_processing', False)}\n")
                        if metadata.get('parallel_processing'):
                            f.write(f"- Max Parallel Nodes: {metadata.get('max_parallel_nodes', 'N/A')}\n")
                            f.write(f"- Async LLM Mode: {metadata.get('parallel_async_llm_mode', 'N/A')}\n")
                            f.write(f"- Max Concurrent LLM Calls: {metadata.get('max_concurrent_llm_calls', 'N/A')}\n")
                        f.write(f"\nPERFORMANCE METRICS:\n")
                        f.write(f"- Total Execution Time: {metadata.get('total_elapsed_seconds', 'unknown')} seconds\n")
                        f.write(f"- Total Nodes Processed: {metadata.get('total_nodes', 'unknown')}\n")
                        f.write(f"- Total Provenance Logs: {metadata.get('total_provenance_logs', len(mrm_instance.overall_provenance_logs) if hasattr(mrm_instance, 'overall_provenance_logs') else 0)}\n")
                        
                        # Calculate nodes per second if we have the data
                        if metadata.get('total_elapsed_seconds') and metadata.get('total_nodes'):
                            try:
                                nodes_per_sec = metadata['total_nodes'] / metadata['total_elapsed_seconds']
                                f.write(f"- Processing Rate: {nodes_per_sec:.2f} nodes/second\n")
                            except (ZeroDivisionError, TypeError):
                                f.write(f"- Processing Rate: Could not calculate\n")
                    
                    # Report status and structure analysis
                    f.write(f"\nREPORT ANALYSIS:\n")
                    if "report_content" in final_report:
                        report_content = final_report["report_content"]
                        if isinstance(report_content, dict):
                            f.write(f"- Report Structure: {len(report_content)} top-level sections\n")
                            f.write(f"- Section Keys: {list(report_content.keys())}\n")
                    
                    f.write(f"- Final Report Status: {final_report.get('status', 'unknown')}\n")
                    f.write(f"- Report Size (JSON): {len(json.dumps(final_report, default=str))} characters\n")
                
                f.write(f"\nFILE OUTPUTS:\n")
                f.write(f"- Report File: {report_file}\n")
                f.write(f"- Provenance File: {provenance_file}\n")
                f.write(f"- Summary File: {summary_file}\n")
                
            print(f"✅ Performance summary saved to: {summary_file}")
            
        except Exception as e:
            print(f"❌ Error saving performance summary: {e}")
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
