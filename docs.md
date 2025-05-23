**`config.py` - Configuration Settings**

*   **Purpose:** Centralizes all system-wide configuration variables. This makes it easy to adjust settings without modifying core code.
*   **Key Contents:**
    *   `GEMINI_API_KEY`: Loads the Google Generative AI API key from environment variables (via `.env` file). Raises an error if not found, as it's critical.
    *   `DB_CONFIG`: A dictionary containing connection parameters (dbname, user, password, host, port) for the PostgreSQL database, also loaded from environment variables with defaults.
    *   `MRM_MODEL_NAME`: Specifies the Gemini model to be used for the main Master Reasoning Model's (MRM) core synthesis and intent definition tasks (e.g., "gemini-1.5-pro-latest").
    *   `SUBSIDIARY_AGENT_MODEL_NAME`: Specifies the Gemini model for subsidiary agents (e.g., "gemini-1.5-flash-latest"), often a faster/cheaper model for more focused tasks.
    *   `MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION`: An integer defining the maximum number of full documents the retriever will attempt to load into an LLM's context window if deemed relevant.
    *   `MAX_CHUNKS_FOR_CONTEXT`: An integer defining the maximum number of individual text chunks to load into context if full document injection isn't feasible or chosen.
    *   `MAX_TOKENS_PER_GEMINI_CALL_APPROX`: An approximate token limit to guide context packing, helping to avoid exceeding the actual model's token limit.
    *   `EMBEDDING_DIMENSION`: An integer specifying the dimensionality of the vector embeddings used for semantic search (e.g., 768). This must match the embedding model used during data ingestion.
    *   `REPORT_TEMPLATE_DIR`: String path to the directory where report template JSON files are stored (e.g., `./report_templates/`).
    *   `POLICY_KB_DIR`: String path to the directory where policy knowledge base JSON files are stored (e.g., `./policy_kb/`).
    *   `MC_ONTOLOGY_DIR`: String path to the directory where material consideration ontology JSON files are stored (e.g., `./mc_ontology_data/`).

---

**`core_types.py` - Core Data Structures and Enumerations**

*   **Purpose:** Defines the fundamental Python classes and enums used throughout the application to represent key entities and states. This promotes type safety and code clarity.
*   **Key Contents:**
    *   `IntentStatus(Enum)`: Defines the possible states an `Intent` or `ReasoningNode` can be in (e.g., `PENDING`, `IN_PROGRESS`, `COMPLETED_SUCCESS`, `FAILED`).
    *   `RetrievalSourceType(Enum)`: Defines the origin of a retrieved piece of information (e.g., `DOCUMENT_CHUNK`, `AGENT_REPORT`).
    *   `ProvenanceLog(class)`: Records the execution history of an `Intent` or a `ReasoningNode`'s processing. It includes timestamps, actions taken, status, and a summary of results or errors. Used for explainability and debugging.
    *   `RetrievedItem(class)`: Represents a single piece of information retrieved by the `AgenticRetriever`, bundling the content with its source type and metadata (like document ID, page number).
    *   `Intent(class)`: Represents a specific task or question the MRM needs to address. This is a central data structure. It contains:
        *   `intent_id`, `parent_node_id`, `parent_intent_id` (for linking and hierarchy).
        *   `task_type`: What kind of operation this intent represents (e.g., "ASSESS\_POLICY\_COMPLIANCE").
        *   `application_refs`: Identifiers for the planning application(s) it relates to.
        *   `assessment_focus`: A detailed description of what the intent aims to achieve.
        *   `retrieval_config`: Parameters for the `AgenticRetriever` (keywords, document filters, semantic query text).
        *   `data_requirements`: (Often a JSON schema) Defines the expected structure of the output from the LLM synthesis step for this intent.
        *   `satisfaction_criteria`: Rules to check if the intent's execution was successful.
        *   `agent_to_invoke` & `agent_input_data`: If a subsidiary agent is needed.
        *   `context_data_from_prior_steps`: Outputs from previously completed intents/nodes, used as context for this one.
        *   `llm_policy_context_summary`: Summaries of relevant policies to be included in LLM prompts.
        *   `full_documents_context` & `chunk_context`: The actual textual context (either full documents or selected chunks) prepared by the retriever for LLM processing.
        *   `status`, `result` (raw retrieved items), `synthesized_text_output`, `structured_json_output`, `error_message`, `confidence_score`, `provenance`.
    *   `ReasoningNode(class)`: Represents a section or sub-section in the dynamically generated planning report structure (the "reasoning graph"). It contains:
        *   `node_id` (a unique path-like identifier, e.g., "4.0\_AssessmentOfMaterialConsiderations/HousingDelivery"), `description`.
        *   `status`: Current processing state of this node.
        *   Metadata loaded from report templates or ontology: `node_type_tag`, `generic_material_considerations`, `specific_policy_focus_ids`, `key_evidence_document_types`, `linked_ontology_entry_id`, `is_dynamic_parent_node`, `agent_to_invoke_hint`.
        *   `depends_on_nodes`: A list of other `node_id`s that must be completed before this node can be processed.
        *   `sub_nodes`: A dictionary of child `ReasoningNode`s, forming the hierarchy.
        *   `intents_issued`: A list of `Intent` objects processed for this node.
        *   `final_structured_data` & `final_synthesized_text`: The consolidated output for this node.
        *   `node_level_provenance`: A `ProvenanceLog` for the overall processing of this node.
        *   `confidence_score`: An aggregated confidence in the node's final assessment.
        *   Methods: `add_sub_node`, `get_sub_node_output_by_key`, `update_status_based_on_children_and_intents`.

---

**`db_manager.py` - Database Interaction Layer**

*   **Purpose:** Encapsulates all direct interactions with the PostgreSQL database (which includes the `pgvector` extension for vector storage and search).
*   **Key Contents:**
    *   `DatabaseManager(class)`:
        *   Constructor: Initializes a database connection using parameters from `config.DB_CONFIG`.
        *   `_connect()`: Private method to establish/re-establish the connection.
        *   `execute_query()`: A generic method to run SQL queries, handling parameters and fetching results (one or all rows) as dictionaries.
        *   `add_document()`: Inserts metadata for a new source document (e.g., PDF) into the `documents` table.
        *   `add_document_chunk()`: Inserts an extracted text chunk into `document_chunks`, generates its vector embedding (using a placeholder `get_embedding` function), and stores the embedding in `chunk_embeddings`.
        *   `get_full_document_text_by_id()`: Retrieves all text chunks for a given `doc_id` and concatenates them to reconstruct the full document text.
        *   `log_retrieval()`: Inserts a record into the `retrieval_logs` table, capturing details of a retrieval operation for auditing and analysis.
        *   `close()`: Closes the database connection.
    *   `get_embedding()`: (Placeholder function at module level) Simulates generating a vector embedding for a piece of text. In a real system, this would use a proper sentence transformer model.

---

**`retrieval/retriever.py` - Agentic Retriever Logic**

*   **Purpose:** Handles the complex task of finding and preparing relevant information (context) for the LLMs based on an `Intent`'s `retrieval_config`.
*   **Key Contents:**
    *   `AgenticRetriever(class)`:
        *   Constructor: Takes a `DatabaseManager` instance.
        *   `_get_semantic_results()`: Private method to perform a pure semantic (vector) search against the `chunk_embeddings` table using a query text and `pgvector`'s similarity operators (e.g., `<->`).
        *   `retrieve_and_prepare_context()`: This is the main method. Given an `Intent`:
            1.  **Structured Retrieval:** Executes SQL queries against `documents` and `document_chunks` based on filters in `intent.retrieval_config` (e.g., `document_type_filters`, `hybrid_search_terms` using `ILIKE`).
            2.  **Semantic Retrieval:** Calls `_get_semantic_results` if `semantic_search_query_text` is provided in the intent's config.
            3.  **Combine & Rank:** Merges results from structured and semantic searches, de-duplicates them, and applies a ranking logic (currently simple: semantic results first, then by original order).
            4.  **Populate `intent.result`:** Stores the top N ranked chunks as a list of `RetrievedItem` objects on the `intent`.
            5.  **Context Window Strategy:** Decides whether to use full document injection or chunk-based injection for the LLM context:
                *   If the number of unique source documents for the top-ranked chunks is small (<= `MAX_CONTEXT_DOCUMENTS_FOR_FULL_INJECTION`) AND their combined (approximated) token count is within limits, it fetches the full text of these documents using `db_manager.get_full_document_text_by_id()`. This is stored in `intent.full_documents_context`.
                *   Otherwise, or if full docs are too large, it selects the top N chunks (`MAX_CHUNKS_FOR_CONTEXT`) and stores them in `intent.chunk_context`.
            6.  Logs the retrieval operation using `db_manager.log_retrieval()`.
            7.  Updates the `intent.provenance` log.

---

**`knowledge_base/report_template_manager.py` - Report Structure Templates**

*   **Purpose:** Manages loading and providing standardized report structures (templates) for different types of planning applications.
*   **Key Contents:**
    *   `ReportTemplateManager(class)`:
        *   Constructor: Loads all `.json` files from the `REPORT_TEMPLATE_DIR` (defined in `config.py`). Each JSON file is expected to represent a report template.
        *   `_load_templates()`: Handles the loading logic. Each template JSON should have a `report_type_id` field (e.g., "Default\_MajorHybrid") which is used as the key to store the template. It also creates a default template if the directory is empty or the specific default is missing.
        *   `get_template()`: Takes a `report_type` string and returns the corresponding loaded template structure (a dictionary). Includes fallback logic to find generic templates (e.g., "Default\_MajorApplication") if a highly specific one isn't found.

---

**`knowledge_base/material_consideration_ontology.py` - Planning Knowledge Ontology**

*   **Purpose:** Stores structured information about canonical material planning considerations. This acts as a knowledge base for the MRM.
*   **Key Contents:**
    *   `MaterialConsiderationOntology(class)`:
        *   Constructor: Loads all `.json` files from `MC_ONTOLOGY_DIR`. Each file is expected to contain a list of material consideration entries.
        *   `_load_ontology()`: Handles loading. Each entry in the JSON should have an `id` (e.g., "HousingDelivery") and other metadata. Creates a default ontology file if needed.
        *   `ontology` (dict): Stores the loaded data, keyed by the MC `id`. Each entry contains:
            *   `id`, `display_name_template` (a template for the node description).
            *   `primary_tags` (keywords associated with this MC).
            *   `relevant_policy_themes` (tags/IDs for related policies).
            *   `key_evidence_docs` (typical document types needed for this MC).
            *   `data_schema_hint` (a hint for the expected structured output when assessing this MC).
            *   `agent_to_invoke_hint` (if a specific agent is usually helpful).
        *   `get_consideration_details()`: Returns the full data for a given MC `id`.
        *   `find_matching_consideration_id()`: Takes a free-text theme (e.g., from an LLM's application scan) and tries to match it to a canonical MC `id` in the ontology using keyword and tag matching.

---

**`knowledge_base/policy_manager.py` - Planning Policy Access**

*   **Purpose:** Manages access to a knowledge base of planning policies.
*   **Key Contents:**
    *   `PolicyManager(class)`:
        *   Constructor: Loads policy data from `.json` files in `POLICY_KB_DIR`. Creates a default sample policy file if needed.
        *   `policies_kb` (dict): Stores loaded policies, keyed by policy `id`. Each entry contains `id`, `title`, `text_summary`, `keywords`, `source`.
        *   `get_policies_by_tags_and_keywords()`: Retrieves a list of policy data dictionaries that match any of the provided tags (against policy IDs) or keywords (against policy title, keywords, summary).
        *   `get_policy_details()`: Returns the full data for a specific policy `id`.
        *   `get_policy_full_text()`: (Currently returns `text_summary`) Would ideally return the complete policy text.

---

**`agents/base_agent.py` - Base Class for Subsidiary Agents**

*   **Purpose:** Provides a common structure and helper methods for all subsidiary agents.
*   **Key Contents:**
    *   `BaseSubsidiaryAgent(class)`:
        *   Constructor: Takes an `agent_name` and a `genai.GenerativeModel` instance (typically a Gemini Flash model).
        *   `_prepare_gemini_content()`: A helper method that constructs the list of "parts" (text, and potentially images in future) to send to the Gemini API. It prioritizes `intent.full_documents_context`, then `intent.chunk_context`, and includes `intent.llm_policy_context_summary` and the `agent_specific_prompt_prefix`. It also logs which context type is being used via `intent.provenance`.
        *   `process()`: The main method called by the `NodeProcessor`. It:
            1.  Calls `_prepare_gemini_content`.
            2.  Makes the `self.model.generate_content()` call to the agent's Gemini model.
            3.  Handles basic response validation (checking for blocks or empty content).
            4.  Extracts the generated text (or JSON string if `response_mime_type` was set).
            5.  Returns a dictionary containing the agent's name, model used, the raw generated output, and an echo of its input data for auditing.
            6.  Updates `intent.provenance`.

---

**`agents/visual_heritage_agent.py` - Example Specific Agent**

*   **Purpose:** A concrete implementation of a subsidiary agent focused on visual and heritage assessment (currently text-based, using Gemini Flash).
*   **Key Contents:**
    *   `VisualHeritageAssessmentAgentGemini(class)`: Inherits from `BaseSubsidiaryAgent`.
        *   Constructor: Initializes with a specific agent name and the passed Gemini model instance.
        *   `process()`:
            1.  Extracts relevant pieces of information from `agent_input_data` (which was prepared by `IntentDefiner` based on its LLM-generated spec). This includes visual descriptions (textual), design principles, and specific heritage concerns.
            2.  Constructs a detailed `prompt_prefix` tailored for visual/heritage assessment, incorporating this extracted information and instructing the LLM on the desired output structure.
            3.  Calls `super().process()` to handle the actual Gemini API call and context preparation.
            4.  Optionally, performs basic post-processing on the `generated_analysis` from the LLM to create a simple `structured_findings_summary`.
            5.  Returns the enriched output dictionary.

---

**`mrm/intent_definer.py` - LLM-Powered Intent Specification Generator**

*   **Purpose:** This crucial module uses the main MRM's Gemini Pro model to *dynamically generate the JSON specification for the next `Intent`* that a `ReasoningNode` needs to process. This replaces most of the hardcoded `if/elif` logic for different node types.
*   **Key Contents:**
    *   `IntentDefiner(class)`:
        *   Constructor: Takes a `PolicyManager` instance and initializes its own Gemini Pro model instance.
        *   `define_intent_spec_via_llm()`:
            1.  Gathers extensive context about the current `ReasoningNode` (its metadata from the template/ontology), summaries of the site and proposal, outputs from prerequisite nodes, and relevant policy summaries from `PolicyManager`.
            2.  Crafts a detailed meta-prompt for Gemini Pro. This prompt instructs Gemini Pro to act as a "Planning Assessment Orchestrator" and generate a JSON object specifying the `task_type`, `assessment_focus`, `policy_context_tags_to_consider`, `retrieval_config`, `data_requirements_schema`, optional `agent_to_invoke` and `agent_input_data_preparation_notes`, and `output_format_request_for_llm` for the *current* `ReasoningNode`. The prompt includes examples and guidance based on node type.
            3.  Makes a Gemini Pro API call with `response_mime_type="application/json"`.
            4.  Parses the returned JSON string into a dictionary (the intent specification).
            5.  Performs basic validation on the generated specification.
            6.  Returns the specification dictionary or `None` if generation fails.
        *   `define_clarification_intent_spec_via_llm()`: A similar method, but the prompt is tailored to generate a *follow-up, more focused Intent specification* if a previous intent for a node resulted in `COMPLETED_WITH_CLARIFICATION_NEEDED`. It takes the original intent and the reason for clarification as input.

---

**`mrm/node_processor.py` - Executor of Individual Intents**

*   **Purpose:** Encapsulates the logic for taking a fully defined `Intent` object and executing its lifecycle: retrieval, optional agent invocation, and final MRM synthesis using Gemini Pro.
*   **Key Contents:**
    *   `NodeProcessor(class)`:
        *   Constructor: Takes the MRM's main Gemini Pro model instance, an `AgenticRetriever` instance, and the dictionary of `SubsidiaryAgent`s.
        *   `_prepare_mrm_synthesis_content()`: Helper to assemble all context (from `intent.context_data_from_prior_steps`, `intent.llm_policy_context_summary`, `intent.full_documents_context` or `intent.chunk_context`) for the final synthesis LLM call.
        *   `_check_satisfaction()`: Evaluates if an intent's outcome meets its `satisfaction_criteria`.
        *   `_estimate_confidence()`: Conceptually estimates a confidence score for an intent's output.
        *   `process_intent()`: The main execution method for an `Intent`:
            1.  Sets intent status to `IN_PROGRESS`.
            2.  If the `intent.task_type` requires data retrieval, calls `self.retriever.retrieve_and_prepare_context(intent)` to populate `intent.full_documents_context` or `intent.chunk_context` and `intent.result`.
            3.  If `intent.agent_to_invoke` is set, it gets the agent from `self.subsidiary_agents` and calls its `process()` method, passing the `intent` (for context access) and `intent.agent_input_data`. Stores the agent's report.
            4.  If the `intent.task_type` involves MRM synthesis/assessment (e.g., "SYNTHESIZE\_...", "ASSESS\_..."), it:
                *   Constructs a detailed prompt for `self.mrm_model` (Gemini Pro).
                *   Calls `_prepare_mrm_synthesis_content` to gather all context.
                *   Makes the Gemini Pro API call.
                *   Parses the response (JSON or text) and stores it in `intent.structured_json_output` and `intent.synthesized_text_output`.
            5.  If it was a simple retrieval or agent-only task without MRM synthesis, populates output fields accordingly.
            6.  Calls `_check_satisfaction`. If not met, status becomes `COMPLETED_WITH_CLARIFICATION_NEEDED`.
            7.  Calls `_estimate_confidence` and stores it on the `intent`.
            8.  Completes the `intent.provenance` log.

---

**`mrm/mrm_orchestrator.py` - Main Orchestration Logic**

*   **Purpose:** Manages the overall process of generating a planning report. It initializes the reasoning graph from a template, dynamically expands it (especially for material considerations), determines the processing order of nodes based on dependencies, and coordinates the definition and execution of intents for each node.
*   **Key Contents:**
    *   `MRM(class)`: (Now `MRMOrchestrator` effectively)
        *   Constructor: Initializes with `DatabaseManager`, `ReportTemplateManager`, `MaterialConsiderationOntology`, and `PolicyManager`. It also creates instances of `IntentDefiner` and `NodeProcessor`.
        *   `_initialize_reasoning_graph_for_application()`: Loads a report template using `ReportTemplateManager` based on `report_type` and builds the initial `ReasoningNode` tree, populating nodes with metadata from the template.
        *   `_run_initial_application_scan_intent()`: **NEW.** Creates and processes a special intent using `NodeProcessor` to scan initial application documents with Gemini Pro and identify key themes for material considerations.
        *   `_dynamically_expand_mc_node()`: **ENHANCED.** Takes the themes from the application scan, matches them to entries in the `MaterialConsiderationOntology`, and dynamically creates/adds detailed sub-nodes under the main "Material Considerations" parent node in the reasoning graph.
        *   `_get_all_nodes_in_graph()` & `_get_processing_order()`: Helpers to flatten the reasoning graph and perform a topological sort to determine the correct order for processing nodes based on their `depends_on_nodes` metadata.
        *   `_process_single_node()`: Core logic for processing one `ReasoningNode`:
            1.  Checks if dependencies are met.
            2.  Calls `self.intent_definer.define_intent_spec_via_llm()` to get the JSON specification for the *primary intent* for this node. This is the key LLM-driven intent definition step.
            3.  If a clarification is needed (node status is `COMPLETED_WITH_CLARIFICATION_NEEDED`), it calls `self.intent_definer.define_clarification_intent_spec_via_llm()` instead.
            4.  Constructs an `Intent` object from the returned specification.
            5.  Calls `self.node_processor.process_intent()` to execute this intent.
            6.  Updates the `ReasoningNode`'s status, final outputs, and confidence based on the intent's outcome. Stores output in `self.completed_node_outputs`.
        *   `orchestrate_full_report_generation()`: The main public method.
            1.  Initializes the graph for the given `report_type` and `application_refs`.
            2.  Calls `_run_initial_application_scan_intent()` to get application-specific MC themes.
            3.  Calls `_dynamically_expand_mc_node()` for any dynamic parent nodes (like "4.0\_AssessmentOfMaterialConsiderations") using the scanned themes.
            4.  Gets the `processing_order` for all nodes.
            5.  Iterates through the nodes in order, calling `_process_single_node()` for each. Includes a loop to allow for reprocessing nodes that require clarification.
            6.  Updates the root node's overall status.
            7.  Returns the final report structure.
        *   `get_final_report()` & `_build_final_report_object()`: Recursively constructs the final JSON report output from the processed `ReasoningNode` tree.
        *   `print_provenance_summary()`: Prints a summary of all `ProvenanceLog` entries.
        *   Helper methods like `_should_attempt_auto_clarification_for_node` to manage the clarification loop.

---

**`main.py` - Main Execution Script**

*   **Purpose:** Initializes all components and kicks off the report generation process.
*   **Key Contents:**
    *   Loads environment variables (for `GEMINI_API_KEY`, DB config).
    *   Initializes `DatabaseManager`, `ReportTemplateManager`, `MaterialConsiderationOntology`, and `PolicyManager`.
    *   Ensures `schema.sql` is executed and minimal sample data is ingested if the database is new.
    *   Creates an instance of the main `MRM` orchestrator class, passing the necessary manager instances.
    *   Specifies the `report_type_key` (e.g., "Default\_MajorHybrid") and `application_references`.
    *   Calls `mrm_instance.orchestrate_full_report_generation()`.
    *   Prints the final JSON report and the provenance summary.
    *   Includes basic error handling and total execution time.