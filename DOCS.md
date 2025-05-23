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
        *   `search_policies()`: **Crucially, this now performs a hybrid search (structured filters on `document_type` like "PolicyDocument_NPPF", `source`, policy ID tags in `document_chunks.tags` or `document_chunks.section`, combined with semantic search via `pgvector` on `chunk_embeddings`) directly against the database via `db_manager`.** It returns a list of relevant policy clauses/chunks.
        *   `get_policy_details()`: Returns the full data for a specific policy `id`.
        *   `get_policy_full_text()`: (Currently returns `text_summary`) Would ideally return the complete policy text.
        *   `_ingest_sample_policies_from_json()`: (Primarily for setup/demo) Reads policy definitions from JSON files in `POLICY_KB_DIR`, and for each policy, uses `db_manager.add_document()` to create a "policy document" record and `db_manager.add_document_chunk()` to store its text as chunks (which are then embedded). This means policy text is treated like application document text for storage and embedding.

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

    Okay, here's the documentation explaining the `schema.sql` file required for the PostgreSQL database backend of this generalized planning AI system.

---

## Database Schema Documentation (`schema.sql`)

**Purpose:** This document outlines the SQL schema required to store and manage planning application documents, their textual content, semantic embeddings, and retrieval logs for the Generalized Planning AI system. The schema is designed for PostgreSQL and leverages the `pgvector` extension for efficient similarity searches on embeddings.

**Overall Design Principles:**

*   **Normalization:** Data is organized into related tables to reduce redundancy and improve data integrity.
*   **UUIDs for Primary Keys:** Universally Unique Identifiers (`UUID`) are used for primary keys to facilitate distributed data management and prevent collisions if data from multiple sources is merged. The `uuid-ossp` PostgreSQL extension is recommended for generating these.
*   **CASCADE Deletes:** Foreign key relationships are set up with `ON DELETE CASCADE` where appropriate, meaning that if a parent record (e.g., a document) is deleted, all its associated child records (e.g., its chunks and embeddings) are also automatically deleted.
*   **Timestamping:** `created_at` timestamps are included to track when records were added. Using `timezone('utc', now())` ensures timestamps are stored in UTC for consistency.
*   **Extensibility:** Fields like `tags` (TEXT[]) and `filters` (JSONB) allow for flexible addition of metadata without schema changes.
*   **Vector Storage:** The `pgvector` extension's `vector` data type is used for storing embeddings, enabling powerful similarity search capabilities directly within the database.

---

### Table Definitions:

**1. `documents` Table**

*   **Purpose:** Stores metadata about each individual source document (typically a PDF file) that is part of a planning application or relevant policy document.
*   **SQL Definition:**
    ```sql
    CREATE TABLE IF NOT EXISTS documents (
      doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(), -- Unique identifier for the document
      filename TEXT NOT NULL,                             -- Original filename of the document
      title TEXT,                                         -- Official or descriptive title of the document
      document_type TEXT,                                 -- Categorization (e.g., DAS, ES_Chapter, PlanningStatement, PolicyDocument, UserGuide)
      source TEXT,                                        -- Origin or reference (e.g., PlanningApplicationNumber, LPA_PolicySet_Version)
      page_count INTEGER,                                 -- Total number of pages in the document
      upload_date DATE,                                   -- Date the document was ingested into the system
      tags TEXT[]                                         -- Optional array of free-text tags for further categorization or searching (e.g., ["Phase1", "Residential", "Sustainability"])
    );
    ```
*   **Column Descriptions:**
    *   `doc_id`: Primary Key. A unique UUID automatically generated for each document.
    *   `filename`: The original name of the uploaded file (e.g., `Design_and_Access_Statement_Vol1.pdf`). Not necessarily unique. `NOT NULL`.
    *   `title`: A human-readable title for the document. Can be extracted from the document or manually entered. `NULLABLE`.
    *   `document_type`: A controlled vocabulary or free-text string indicating the type of document. Essential for filtering (e.g., `UserGuide`, `DevelopmentSpecification`, `ES_Chapter_Noise`). `NULLABLE`.
    *   `source`: Indicates the origin of the document, often the planning application reference it belongs to, or the policy set it's part of. `NULLABLE`.
    *   `page_count`: The total number of pages in the PDF document. `NULLABLE`.
    *   `upload_date`: The date when this document record was created/ingested. `NULLABLE`.
    *   `tags`: An array of text strings for flexible tagging. `NULLABLE`.

**2. `document_chunks` Table**

*   **Purpose:** Stores segments of extracted text from the documents. Documents are broken down ("chunked") into smaller, manageable pieces for processing and semantic embedding.
*   **SQL Definition:**
    ```sql
    CREATE TABLE IF NOT EXISTS document_chunks (
      chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),          -- Unique identifier for the text chunk
      doc_id UUID REFERENCES documents(doc_id) ON DELETE CASCADE,    -- Foreign key linking to the parent document
      page_number INTEGER,                                          -- Page number in the original document where this chunk starts
      section TEXT,                                                 -- Optional: Logical section/heading this chunk belongs to (e.g., "3.1 Housing Mix")
      chunk_text TEXT NOT NULL,                                     -- The actual extracted text content of the chunk
      tags TEXT[],                                                  -- Optional array of tags specific to this chunk
      created_at TIMESTAMP DEFAULT timezone('utc', now())           -- Timestamp of when the chunk was created
    );

    -- Optional: Index for faster lookup by doc_id and page_number
    CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_id_page ON document_chunks (doc_id, page_number);
    ```
*   **Column Descriptions:**
    *   `chunk_id`: Primary Key. A unique UUID automatically generated for each text chunk.
    *   `doc_id`: Foreign Key referencing `documents.doc_id`. Links the chunk back to its source document. `ON DELETE CASCADE` ensures chunks are deleted if the parent document is deleted. `NULLABLE` (though practically should always be linked).
    *   `page_number`: The page number in the original document from which this chunk was extracted. `NULLABLE`.
    *   `section`: An optional textual description of the logical section or heading the chunk falls under (e.g., "4.2 Affordable Housing Provision"). Useful for contextual understanding. `NULLABLE`.
    *   `chunk_text`: The actual text content of this segment. `NOT NULL`.
    *   `tags`: An array of text strings for tagging specific aspects of this chunk (e.g., ["policy_quote", "metric_value", "objection_point"]). `NULLABLE`.
    *   `created_at`: Timestamp indicating when this chunk record was created. Defaults to the current UTC time.

**3. `chunk_embeddings` Table**

*   **Purpose:** Stores the pre-computed vector embeddings for each text chunk. These embeddings represent the semantic meaning of the chunk text and are used for similarity searches.
*   **SQL Definition:**
    ```sql
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
      chunk_id UUID PRIMARY KEY REFERENCES document_chunks(chunk_id) ON DELETE CASCADE, -- Foreign key linking to the text chunk
      embedding vector(768)                                                            -- The vector embedding. Dimension (e.g., 768) must match the embedding model used (see config.EMBEDDING_DIMENSION)
    );

    -- Crucial: Index for efficient similarity search using pgvector
    -- The type of index (e.g., HNSW, IVFFlat) and its parameters depend on dataset size and performance requirements.
    -- HNSW is generally good for recall and speed.
    CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_embedding ON chunk_embeddings USING hnsw (embedding vector_l2_ops);
    -- Or for cosine similarity if embeddings are normalized:
    -- CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_embedding ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
    -- Or for inner product:
    -- CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_embedding ON chunk_embeddings USING hnsw (embedding vector_ip_ops);
    ```
*   **Column Descriptions:**
    *   `chunk_id`: Primary Key and Foreign Key referencing `document_chunks.chunk_id`. Establishes a one-to-one relationship between a chunk and its embedding. `ON DELETE CASCADE` ensures embeddings are deleted if the parent chunk is deleted.
    *   `embedding`: The vector data type from the `pgvector` extension. The dimension (e.g., `vector(768)`) must match the output dimension of the sentence embedding model used (specified in `config.EMBEDDING_DIMENSION`).
*   **Indexing Note:** The `CREATE INDEX ... USING hnsw ...` statement is crucial for performing fast approximate nearest neighbor searches, which are the core of semantic similarity queries. The `vector_l2_ops`, `vector_cosine_ops`, or `vector_ip_ops` depends on the distance metric appropriate for your embeddings (L2 for Euclidean, cosine for cosine similarity, inner product for dot product). Ensure your embeddings are normalized if using `vector_cosine_ops`.

**4. `retrieval_logs` Table**

*   **Purpose:** Stores a log of retrieval operations performed by the system. This is valuable for debugging, performance analysis, understanding query patterns, and potentially for fine-tuning retrieval strategies.
*   **SQL Definition:**
    ```sql
    CREATE TABLE IF NOT EXISTS retrieval_logs (
      log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),          -- Unique identifier for the log entry
      timestamp TIMESTAMP DEFAULT timezone('utc', now()),           -- Timestamp of when the retrieval occurred
      query TEXT,                                                 -- The original query (could be natural language or structured terms as JSON string)
      filters JSONB,                                              -- JSONB object storing any structured filters applied (e.g., document_type, tags)
      matched_chunk_ids UUID[],                                   -- Array of chunk_ids that were returned by this retrieval operation
      agent_context TEXT                                          -- Optional: Context about the agent or process that initiated the retrieval (e.g., "IntentID_XYZ for Node_ABC")
    );
    ```
*   **Column Descriptions:**
    *   `log_id`: Primary Key. A unique UUID for each log entry.
    *   `timestamp`: Timestamp of the retrieval event.
    *   `query`: The raw query string or a JSON representation of the query parameters used for the retrieval. `NULLABLE`.
    *   `filters`: A JSONB field to store any structured filters applied during the retrieval (e.g., `{"document_type": ["DAS"], "tags": ["sustainability"]}`). `NULLABLE`.
    *   `matched_chunk_ids`: An array of UUIDs, storing the `chunk_id`s of all chunks returned by this retrieval. `NULLABLE`.
    *   `agent_context`: A textual description providing context about what part of the AI system triggered this retrieval (e.g., which Intent or ReasoningNode). `NULLABLE`.

---

**Required PostgreSQL Extensions:**

1.  **`uuid-ossp`**: Used for generating UUIDs via `uuid_generate_v4()`.
    *   Installation (if not already available): `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`
2.  **`vector` (`pgvector`)**: Used for storing vector embeddings and performing similarity searches.
    *   Installation (if not already available): `CREATE EXTENSION IF NOT EXISTS vector;`

These `CREATE EXTENSION` commands should typically be run once by a database superuser before creating the tables. The `IF NOT EXISTS` clause makes them safe to include in the `schema.sql` script for idempotency.

---

**1. Report Template JSON Schema (`report_templates/*.json`)**

*   **Purpose:** Defines the hierarchical structure and metadata for a specific type of planning officer's report. The `ReportTemplateManager` loads these files.
*   **File Naming Convention:** `<report_type_id_lowercase_underscored>.json` (e.g., `default_major_hybrid.json`).
*   **Root Object:** A single JSON object.
*   **Key Fields:**
    *   `report_type_id` (String, **Required**): A unique identifier for this report type (e.g., "Default\_MajorHybrid", "HouseholderExtension"). This is used by the MRM to select the correct template.
    *   `report_id_prefix` (String, Optional): A prefix to be used when generating unique IDs for instances of reports created from this template (e.g., "MajorHybridApp").
    *   `description` (String, **Required**): A human-readable description of what this report template is for.
    *   `sections` (Array of Objects, **Required**): An array defining the top-level sections of the report. Each object in this array represents a `ReasoningNode` and has the following structure:
        *   `node_id` (String, **Required**): A unique identifier for this section within its parent (e.g., "1.0\_SiteAndApplication", "1.1\_SiteLocationAndDescription"). For nested sections, the MRM will construct full paths like "1.0\_SiteAndApplication/1.1\_SiteLocationAndDescription".
        *   `description` (String, **Required**): A human-readable description of this section/node. This is used as the default `assessment_focus` for the `Intent` generated for this node.
        *   `node_type_tag` (String, Optional): A tag indicating the generic *type* or purpose of this node (e.g., "SiteDescription", "PolicyAssessment", "MaterialConsideration\_Housing"). This helps the `IntentDefiner` select appropriate logic or prompts.
        *   `generic_material_considerations` (Array of Strings, Optional): A list of broad material consideration themes relevant to this node (e.g., `["site_context", "amenity_impact"]`). Used by `IntentDefiner`.
        *   `specific_policy_focus_ids` (Array of Strings, Optional): A list of specific policy IDs or policy theme keywords (e.g., `["NPPF_Ch12", "LocalPlan_DesignPolicy_DC01"]`) that are particularly relevant to this node. Used by `IntentDefiner` and `PolicyManager`.
        *   `key_evidence_document_types` (Array of Strings, Optional): Hints for the `IntentDefiner` about typical document types that contain evidence for this node (e.g., `["DAS_Visuals", "ES_TransportChapter"]`).
        *   `is_dynamic_parent_node` (Boolean, Optional, Default: `false`): If `true`, indicates that this node (e.g., "4.0\_AssessmentOfMaterialConsiderations") will have its sub-nodes dynamically generated by the MRM based on an application scan and ontology mapping, rather than being explicitly defined in `sub_sections`.
        *   `agent_to_invoke_hint` (String, Optional): The name/ID of a `SubsidiaryAgent` that might be useful for processing this node (e.g., "VisualHeritageAssessmentAgent\_GeminiFlash\_V1").
        *   `depends_on_nodes` (Array of Strings, Optional): A list of `node_id` paths (relative to the template root, or fully qualified) that must be processed before this node can be processed. The MRM's orchestrator uses this for topological sorting.
        *   `sub_sections` (Array of Objects, Optional): If this section has predefined sub-sections, this array contains objects with the same structure as a top-level section object, defining the nested hierarchy.

*   **Example Snippet (`report_templates/default_major_hybrid.json`):**
    ```json
    {
      "report_type_id": "Default_MajorHybrid",
      "report_id_prefix": "MajorHybridApp",
      "description": "Default Standard Report for Major Hybrid Planning Applications",
      "sections": [
        {
          "node_id": "1.0_SiteAndApplication",
          "description": "Site Description, Proposal Details & Planning History",
          "node_type_tag": "IntroductionBlock",
          // ... other metadata ...
          "depends_on_nodes": [],
          "sub_sections": [
            {
              "node_id": "1.1_SiteLocationAndDescription",
              "description": "Site Location, Existing Conditions, and Surrounding Area Character",
              "node_type_tag": "SiteDescription",
              // ... other metadata ...
            }
            // ... more sub-sections ...
          ]
        },
        {
          "node_id": "4.0_AssessmentOfMaterialConsiderations",
          "description": "Officer's Assessment of Material Planning Considerations",
          "node_type_tag": "MaterialConsiderationsBlock_Parent",
          "is_dynamic_parent_node": true,
          "depends_on_nodes": ["1.0_SiteAndApplication", "2.0_ConsultationResponses", "3.0_PlanningPolicyFramework"]
        }
        // ... other top-level sections ...
      ]
    }
    ```

---

**2. Material Consideration Ontology JSON Schema (`mc_ontology_data/*.json`)**

*   **Purpose:** Stores structured, canonical knowledge about various material planning considerations. This is used by the MRM to dynamically generate assessment nodes and define highly relevant intents for them.
*   **File Naming Convention:** Can be one large file (e.g., `main_material_considerations.json`) or multiple thematic files.
*   **Root Object:** A JSON array, where each element is an object representing a single material consideration.
*   **Key Fields for each Material Consideration Object:**
    *   `id` (String, **Required**): A unique canonical identifier for this material consideration (e.g., "HousingDelivery", "HeritageImpact", "FloodRiskAndDrainage"). This is used for linking and lookup.
    *   `display_name_template` (String, **Required**): A template string for generating a human-readable description of the assessment node for this MC, often including a placeholder for the application name (e.g., "Housing Delivery (Quantum, Mix, Affordability, Density, Standards) for {app_name}").
    *   `description_long` (String, Optional): A more detailed explanation of what this material consideration typically covers.
    *   `primary_tags` (Array of Strings, **Required**): Core keywords and tags associated with this MC (e.g., `["housing_impact", "residential_development", "NPPF_Ch5"]`). Used for matching themes from application scans and for retrieval.
    *   `relevant_policy_themes` (Array of Strings, Optional): A list of policy theme keywords or specific policy ID prefixes that are usually relevant to this MC (e.g., `["LondonPlan_H_Series", "LocalPlan_AffordableHousing"]`).
    *   `key_evidence_docs` (Array of Strings, Optional): A list of typical document types where evidence for assessing this MC is usually found (e.g., `["HousingStatement", "ViabilityAssessment"]`).
    *   `data_schema_hint` (Object, Optional): A JSON schema-like dictionary hinting at the structured data points that an `Intent` assessing this MC should aim to extract or synthesize (e.g., `{"total_homes_net": "int", "affordable_percentage": "float"}`). This guides the `IntentDefiner`'s LLM prompt.
    *   `potential_agent_hint` (String, Optional): The name/ID of a `SubsidiaryAgent` that might be particularly useful for analyzing this MC (e.g., "HousingMetricsAgent", "FloodRiskModellingAgent").
    *   `sub_considerations` (Array of Strings, Optional): If this MC has common sub-topics, they can be listed here (e.g., for "Sustainability", sub-considerations might be "Energy", "BNG", "Waste"). This can guide further dynamic node expansion.
    *   `typical_questions_to_address` (Array of Strings, Optional): A list of standard questions an officer would ask when assessing this MC. Useful for crafting the `assessment_focus` of an `Intent`.

*   **Example Snippet (`mc_ontology_data/main_material_considerations.json`):**
    ```json
    [
      {
        "id": "HeritageImpact",
        "display_name_template": "Impact on Heritage Assets (Designated and Non-Designated, including Archaeology and Setting) for {app_name}",
        "description_long": "Assessment of potential direct/indirect impacts on heritage assets (listed buildings, conservation areas, scheduled monuments, etc.), their significance, and setting, including archaeological implications.",
        "primary_tags": ["heritage_conservation", "archaeology", "setting_of_heritage_assets", "NPPF_Ch16", "historic_environment"],
        "relevant_policy_themes": ["LondonPlan_HC_Series", "LocalPlan_HeritagePolicies", "LocalPlan_ArchaeologyPolicy", "ConservationAreaAppraisalsAndManagementPlans"],
        "key_evidence_docs": ["HeritageImpactAssessment", "ArchaeologicalDBA_Or_Evaluation", "ES_BuiltHeritageChapter", "ES_ArchaeologyChapter", "DAS_HeritageResponse", "HistoricEnvironmentRecordData"],
        "data_schema_hint": {
            "identified_heritage_assets_list": [{"asset_name": "string", "designation_grade": "string", "proximity_to_site_m": "integer"}],
            "impact_on_significance_summary": "text_block",
            "archaeology_potential_and_impact": "text_block",
            "mitigation_measures_proposed": "list_of_strings",
            "nppf_harm_test_analysis": "text_block_evaluating_substantial_vs_less_than_substantial_harm_and_public_benefits"
        },
        "potential_agent_hint": "VisualHeritageAssessment_GeminiFlash_V1",
        "typical_questions_to_address": [
            "What designated heritage assets are affected by the proposal or its setting?",
            "What is the significance of these assets?",
            "What is the level of harm (substantial, less than substantial, no harm) to their significance?",
            "Are there any public benefits that outweigh identified harm, as per NPPF tests?",
            "What is the archaeological potential of the site and how is it addressed?"
        ]
      }
      // ... other material consideration entries ...
    ]
    ```

---

**3. Policy Knowledge Base JSON Schema (`policy_kb/*.json`)**

*   **Purpose:** Stores structured information about individual planning policies from various documents (NPPF, London Plan, Local Plans).
*   **File Naming Convention:** Can be organized by policy document (e.g., `nppf_2023.json`, `london_plan_2021.json`, `rbkc_local_plan_core_strategy.json`).
*   **Root Object:** A JSON array, where each element is an object representing a single policy or a significant paragraph within a policy.
*   **Key Fields for each Policy Object:**
    *   `id` (String, **Required**): A unique identifier for the policy (e.g., "NPPF_Ch12_Para130", "LondonPlan_Policy_D3", "RBKC_LP_Policy_CL5"). This should be stable and referenceable.
    *   `title` (String, Optional): The official title or heading of the policy/paragraph.
    *   `text_summary` (String, **Required**): A concise summary of the policy's main thrust or requirements. This is what might be fed into LLM prompts as initial context.
    *   `full_text` (String, Optional but Highly Recommended): The complete verbatim text of the policy. This is crucial for detailed assessment.
    *   `keywords` (Array of Strings, Optional): Keywords and themes associated with this policy, aiding in retrieval (e.g., `["design quality", "local distinctiveness", "streetscape"]`).
    *   `source_document` (String, **Required**): The name of the parent policy document (e.g., "NPPF 2023", "London Plan 2021", "RBKC Core Strategy 2015").
    *   `version_date` (String, Optional, Format: "YYYY-MM-DD"): The adoption or publication date of this version of the policy.
    *   `chapter_or_section_ref` (String, Optional): Reference to the chapter or section within the source document (e.g., "Chapter 12", "Section 3.A").
    *   `related_policy_ids` (Array of Strings, Optional): A list of IDs of other policies that are closely related (e.g., higher-tier policies it implements, or detailed policies that expand on it).
    *   `policy_type` (String, Optional): E.g., "Strategic", "Development Management", "Guidance".
    *   `tests_or_requirements` (Array of Strings, Optional): If the policy contains specific tests or explicit requirements, these can be listed for easier checking (e.g., "Must demonstrate X% affordable housing", "Sequential test for retail required").

*   **Example Snippet (`policy_kb/nppf_sample.json`):**
    ```json
    [
      {
        "id": "NPPF_Para11c_PresumptionTest",
        "title": "NPPF Paragraph 11c - Presumption in Favour (Decision Taking)",
        "text_summary": "For decision-taking, this means approving development proposals that accord with an up-to-date development plan without delay; or where there are no relevant development plan policies, or the policies which are most important for determining the application are out-of-date, granting permission unless: i. the application of policies in this Framework that protect areas or assets of particular importance provides a clear reason for refusing the development proposed; or ii. any adverse impacts of doing so would significantly and demonstrably outweigh the benefits, when assessed against the policies in this Framework taken as a whole.",
        "full_text": "(Full text of NPPF paragraph 11c and d)...",
        "keywords": ["presumption in favour", "sustainable development", "decision making", "NPPF test", "planning balance"],
        "source_document": "NPPF 2023",
        "version_date": "2023-12-20",
        "chapter_or_section_ref": "Chapter 2, Paragraph 11"
      },
      {
        "id": "NPPF_Para134_DesignQuality",
        "title": "NPPF Paragraph 134 - High Quality Design",
        "text_summary": "Development that is not well designed should be refused, especially where it fails to reflect local design policies and government guidance on design, taking into account any local design guidance and supplementary planning documents which use visual tools such as design codes.",
        "full_text": "(Full text of NPPF paragraph 134)...",
        "keywords": ["design quality", "refusal grounds", "local design policies", "design codes", "National Design Guide"],
        "source_document": "NPPF 2023",
        "version_date": "2023-12-20",
        "chapter_or_section_ref": "Chapter 12, Paragraph 134"
      }
      // ... other policy entries ...
    ]
    ```

---

These JSON schemas provide the necessary structure for the knowledge bases. Populating them with comprehensive, accurate, and well-curated data is a substantial but essential task for the AI's effectiveness and ability to generalize. The Python managers (`ReportTemplateManager`, `MaterialConsiderationOntology`, `PolicyManager`) will be responsible for loading and providing access to this data.

---

## UPDATED: High-Level Dataflow Explanation

The system operates in a cyclical, iterative manner, driven by the MRM Orchestrator to construct a planning assessment report. Policy documents are now treated similarly to application documents, being ingested, chunked, and embedded in the main database.

1.  **Initialization & Application Input:**
    *   `main.py` starts with `application_refs` and a `report_type`.
    *   Core managers are initialized: `DatabaseManager`, `ReportTemplateManager`, `MaterialConsiderationOntology`, and `PolicyManager` (which now takes `DatabaseManager` as a dependency).
    *   The `MRMOrchestrator` is initialized, creating instances of `IntentDefiner` and `NodeProcessor`.

2.  **Reasoning Graph Construction (MRM Orchestrator):**
    *   The `MRMOrchestrator` loads the base hierarchical report structure for the `report_type` using `ReportTemplateManager`, forming the initial `ReasoningNode` tree. Nodes are populated with metadata.

3.  **Initial Application Scan (MRM Orchestrator & NodeProcessor):**
    *   A special `Intent` (task type: `SCAN_APPLICATION_FOR_KEY_THEMES_AND_MATERIAL_CONSIDERATIONS`) is processed by `NodeProcessor`.
    *   `AgenticRetriever` fetches key initial application document chunks from the `Database`.
    *   `NodeProcessor`'s main LLM (Gemini Pro) analyzes this context to identify relevant material consideration themes for the *specific application*.

4.  **Dynamic Node Expansion (MRM Orchestrator):**
    *   The `MRMOrchestrator` uses the LLM-identified themes from the scan.
    *   For each theme, it consults `MaterialConsiderationOntology` to map it to a canonical MC entry.
    *   New `ReasoningNode`s for these application-specific MCs are dynamically added to the reasoning graph, populated with metadata from the ontology.

5.  **Processing Order Determination (MRM Orchestrator):**
    *   A topological sort (`_get_processing_order()`) on the fully expanded reasoning graph determines the processing sequence based on `depends_on_nodes`.

6.  **Iterative Node Processing Loop (MRM Orchestrator, IntentDefiner, NodeProcessor):**
    *   For each `ReasoningNode` in order:
        *   **a. Intent Specification (IntentDefiner):**
            *   `IntentDefiner.define_intent_spec_via_llm()` is called.
            *   It gathers context (node metadata, application summaries, completed dependency outputs, relevant policy *summaries/tags* from `PolicyManager`'s initial lookup).
            *   It prompts its Gemini Pro model to generate a detailed JSON *specification* for the `Intent` needed to process the current node (including `task_type`, `assessment_focus`, `retrieval_config` for *application documents*, `data_requirements_schema`, hints for `agent_policy_context_requirements` if an agent is involved, etc.).
        *   **b. Intent Creation & Execution (NodeProcessor):**
            *   The orchestrator creates an `Intent` object from the LLM-generated spec.
            *   This `Intent` is passed to `NodeProcessor.process_intent()`.
            *   `NodeProcessor`:
                1.  **Application Document Retrieval:** Calls `AgenticRetriever.retrieve_and_prepare_context(intent)` to get relevant *application document* chunks/full docs from the `Database` and populates the `intent`'s context fields.
                2.  **Agent-Specific Policy Retrieval (NEW):** If the `intent` (from `IntentDefiner`'s spec) indicates an agent needs specific policy context (e.g., via `agent_policy_context_requirements` field in `agent_input_data`):
                    *   `NodeProcessor` calls `self.policy_manager.search_policies()` with these requirements.
                    *   `PolicyManager` performs a hybrid search (SQL + `pgvector`) on policy documents/chunks *stored in the main database*.
                    *   The retrieved policy *clauses* are added to `intent.agent_input_data["retrieved_policy_clauses_for_agent"]`.
                3.  **Subsidiary Agent Invocation (Optional):** If `intent.agent_to_invoke` is set, the agent's `process()` method is called. The `BaseSubsidiaryAgent._prepare_gemini_content()` now incorporates `intent.llm_policy_context_summary` (general policy context for the node) AND `intent.agent_input_data.get("retrieved_policy_clauses_for_agent")` (targeted policy clauses for the agent).
                4.  **MRM Synthesis/Assessment:** `NodeProcessor` constructs a final prompt for its Gemini Pro model, including application doc context, prior step outputs, *general policy summaries for the node* (`intent.llm_policy_context_summary`), and any agent report.
                5.  Gemini Pro generates the output for the `Intent`.
                6.  Satisfaction, confidence, and provenance are updated.
        *   **c. Node Update & Clarification Check (MRM Orchestrator):**
            *   The `ReasoningNode` is updated. Outputs are stored in `completed_node_outputs`.
            *   If clarification is needed and viable, `IntentDefiner.define_clarification_intent_spec_via_llm()` is called, and the node might be re-queued by the orchestrator's main loop.

7.  **Loop Continuation & Final Report:**
    *   The orchestrator continues until all nodes are processed or max iterations are hit.
    *   The final report is assembled from all `ReasoningNode` outputs.

**Key Dataflow Change for Policy:** Policy documents are now treated like application documents – ingested, chunked, embedded, and stored in the main database. `PolicyManager` becomes a specialized query interface to this policy data within the database, performing its own hybrid searches. `NodeProcessor` explicitly retrieves targeted policy context for agents via `PolicyManager`.

---

## UPDATED: ASCII Architecture Diagram

The main change is that `PolicyManager` now interacts with the `PostgreSQL DB` for its searches.

```mermaid
graph TD
    A[main.py Client/User] ==> B(MRM Orchestrator);

    subgraph KnowledgeBase_Configuration
        C[ReportTemplateManager] --> B;
        D[MCOntology] --> B;
        E(PolicyManager) --> B; subgraph Policy_DB_Interaction
            E -- Hybrid Search for Policies --> L((PostgreSQL DB));
        end
    end

    subgraph MRM_Core
        B ==> F(IntentDefiner);
        F -- Gemini Pro Call (Define Intent Spec) --> G((Gemini API));
        F ==> B; subgraph In_MRM_Orchestrator
            direction LR
            B ==> H{Reasoning Graph};
            B ==> I(NodeProcessor);
        end
        I -- Uses --> J(AgenticRetriever);
        I -- Uses --> E; # NodeProcessor uses PolicyManager for agent-specific policy context
        I -- Invokes --> K[Subsidiary Agents];
        K -- Gemini Flash Call --> G;
        I -- Gemini Pro Call (Synthesize Node Output) --> G;
        I ==> H;
    end

    subgraph DataAndStorage
        J -- App Doc Retrieval --> L;
        M[Source Docs (App & Policy)] --> N(Ingestion Pipeline);
        N -- Chunks & Embeddings --> L;
        L -- pgvector --> J; % For app docs
        L -- pgvector --> E; % For policy docs
    end

    B ==> O[Final Report JSON];
    B ==> P[Provenance Logs];

    classDef kb fill:#e6ffe6,stroke:#333,stroke-width:2px;
    classDef mrmcore fill:#ffe6e6,stroke:#333,stroke-width:2px;
    classDef data fill:#e6f3ff,stroke:#333,stroke-width:2px;

    class C,D,E kb;
    class F,H,I,K mrmcore;
    class L,M,N data;
    class B,G,O,P default;
```

**Diagram Change Explanation:**

*   `PolicyManager` (E) now has an arrow pointing to `PostgreSQL DB` (L) indicating it performs its own hybrid searches for policy documents/clauses.
*   `NodeProcessor` (I) now also has an arrow pointing to `PolicyManager` (E) to signify that it requests specific policy context from the `PolicyManager` for subsidiary agents.
*   `Source Docs` (M) now explicitly includes "Policy" documents, which go through the same `Ingestion Pipeline` (N) into the database.

---

## UPDATED: Key File Descriptions (Changes Highlighted)

*   **`knowledge_base/policy_manager.py` (Major Update):**
    *   **Purpose:** Manages access to and retrieval of planning policy information, which is now assumed to be stored and embedded within the main `PostgreSQL DB`.
    *   **Key Functionality:**
        *   Constructor: Takes a `DatabaseManager` instance. Conceptually includes `_ensure_default_policies_ingested_if_needed` which calls `_ingest_sample_policies_from_json` to populate the DB with sample policies if they aren't found (in a real system, ingestion is a separate, robust process).
        *   `_ingest_sample_policies_from_json()`: (Primarily for setup/demo) Reads policy definitions from JSON files in `POLICY_KB_DIR`, and for each policy, uses `db_manager.add_document()` to create a "policy document" record and `db_manager.add_document_chunk()` to store its text as chunks (which are then embedded). This means policy text is treated like application document text for storage and embedding.
        *   `search_policies()`: **Crucially, this now performs a hybrid search (structured filters on `document_type` like "PolicyDocument_NPPF", `source`, policy ID tags in `document_chunks.tags` or `document_chunks.section`, combined with semantic search via `pgvector` on `chunk_embeddings`) directly against the database via `db_manager`.** It returns a list of relevant policy clauses/chunks.
        *   `get_policy_details()`: Returns the full data for a specific policy `id`.
        *   `get_policy_full_text()`: (Currently returns `text_summary`) Would ideally return the complete policy text.

*   **`mrm/mrm_orchestrator.py` (MRMOrchestrator Class):**
    *   **Purpose:** Central controller. Initializes the reasoning graph from a `ReportTemplateManager` template, drives the `_run_initial_application_scan_intent` to identify application-specific material considerations, dynamically expands the reasoning graph using `MaterialConsiderationOntology` and the scan results, determines processing order, and iterates through nodes.
    *   **Interaction with `IntentDefiner`:** For each node, it provides context (node metadata, application summaries, prior outputs, policy hints from `PolicyManager`) to `IntentDefiner` to get an LLM-generated `Intent` specification.
    *   **Interaction with `NodeProcessor`:** Passes the fully constructed `Intent` object (from `IntentDefiner`'s spec) to `NodeProcessor` for execution. It stores the results from `NodeProcessor` in `self.completed_node_outputs`.
    *   **Clarification Loop Management (Conceptual):** Manages the iterative processing if a node requires clarification.

*   **`mrm/intent_definer.py` (IntentDefiner Class):**
    *   **Purpose:** Uses its own Gemini Pro instance to dynamically generate the detailed JSON *specification* for an `Intent` needed for a given `ReasoningNode`.
    *   **Key Functionality (`define_intent_spec_via_llm`, `define_clarification_intent_spec_via_llm`):**
        *   Constructs a rich meta-prompt for Gemini Pro, including current node details, application context, outputs of prerequisite nodes, and crucially, **relevant policy summaries/tags fetched via `PolicyManager`'s initial lookup**.
        *   The prompt guides Gemini Pro to output a JSON object defining the `task_type`, `assessment_focus`, `retrieval_config` (for application documents), `data_requirements_schema`, `agent_to_invoke` (if any), and significantly, **`agent_input_data_preparation_notes` which might include hints for `agent_policy_context_requirements`**.
        *   Returns this JSON specification to the `MRMOrchestrator`.

*   **`mrm/node_processor.py` (NodeProcessor Class):**
    *   **Purpose:** Executes a single, fully defined `Intent` object.
    *   **Key Functionality (`process_intent`):**
        1.  **Application Document Retrieval:** Uses its `AgenticRetriever` instance to fetch context from *application documents* based on `intent.retrieval_config`.
        2.  **Agent-Specific Policy Retrieval (NEW & CRITICAL):** If the `intent.agent_to_invoke` is set and the `intent.agent_input_data` (from `IntentDefiner`'s spec) contains `agent_policy_context_requirements` (e.g., themes like "BiodiversityNetGain"):
            *   It calls `self.policy_manager.search_policies()` with these requirements.
            *   The retrieved policy *clauses* are added to the `agent_input_data` that will be passed to the specific agent.
        3.  **Subsidiary Agent Invocation:** Calls the specified agent, passing the `intent` (which has general context) and the enriched `agent_input_data` (which now includes specifically retrieved policy clauses for the agent).
        4.  **MRM Synthesis:** Uses its Gemini Pro instance to synthesize the final output for the `Intent`, using all available context: application document context, prior step outputs, general policy summaries for the node (`intent.llm_policy_context_summary`), and the agent's report.
        5.  Updates the `Intent` with results, status, confidence.

*   **`knowledge_base/*.json` files:**
    *   **`report_templates/default_major_hybrid.json`:** Provides the *generic structural backbone* of a report for major hybrid applications. Its nodes contain tags and hints that `IntentDefiner` uses to generate specific questions.
    *   **`mc_ontology_data/main_material_considerations.json`:** A structured dictionary of canonical planning issues. `MRMOrchestrator` uses this to flesh out dynamically added nodes (e.g., under "4.0_AssessmentOfMaterialConsiderations") with appropriate tags, policy hints, evidence keywords, and agent suggestions, which then feed into `IntentDefiner`.
    *   **`policy_kb/*.json` (e.g., `nppf_sample.json`):** These are now primarily *source files for an initial, one-time ingestion process* handled by `PolicyManager._ingest_sample_policies_from_json()`. Once ingested, the live policy data resides in the main PostgreSQL database and is queried via `PolicyManager.search_policies()`.

This updated dataflow and architecture make the system more robust in handling policy context for all components, especially subsidiary agents, by treating policy documents as first-class citizens in the database, searchable via hybrid methods.