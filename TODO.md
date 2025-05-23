Here's a prioritized list of next steps to build upon this foundation:

**I. Core Reasoning & Knowledge Enhancement (Highest Priority):**

1.  **Deeply Populate Knowledge Bases:**
    *   **Report Templates:** Create detailed JSON templates in `report_templates/` for various common application types (e.g., `householder_extension.json`, `change_of_use.json`, `minor_commercial.json`, `listed_building_consent.json`). Each template should define its `report_type_id`, a comprehensive section/sub-section hierarchy, and for each node, relevant `node_type_tag`, `generic_material_considerations`, `specific_policy_focus_ids`, `key_evidence_document_types`, and `depends_on_nodes`.
    *   **Material Consideration Ontology (`mc_ontology_data/`):** Massively expand `main_material_considerations.json`. For each canonical material consideration (dozens of them):
        *   Provide multiple `trigger_keywords_for_llm_scan` (to help the initial app scan map to it).
        *   List specific sub-questions an officer would ask.
        *   Detail expected evidence and data points for analysis (`data_schema_hint` should become more robust).
        *   List typical positive/negative impacts and common mitigation measures.
        *   Suggest relevant agent types more precisely.
    *   **Policy Knowledge Base (`policy_kb/`):** Ingest actual Local Plan policies, London Plan policies, and key NPPF chapters into a structured format (e.g., one JSON file per policy document, with policies broken down by chapter/ID). Include full text, objectives, and keywords. Enhance `PolicyManager` to query this richer structure.

2.  **Refine `IntentDefiner.define_intent_spec_via_llm` Prompts:**
    *   This is *the critical AI prompting step*. For each `node_type_tag` or combination of `generic_material_considerations` from the `ReasoningNode`, craft highly specific meta-prompts for Gemini Pro.
    *   These prompts should guide Gemini Pro to generate an `Intent` specification that asks very targeted questions, requests specific `data_requirements_schema` elements, and suggests precise `retrieval_config` (keywords, document types) based on the ontology entry for that consideration.
    *   **Example for a "HousingDensity" MC node:** The meta-prompt would tell Gemini Pro: "You are defining an intent for Housing Density. The ontology states we need to check proposed DPH/HRH against policy, look for density plans in the DAS, and assess contextual appropriateness. Generate an intent spec to retrieve this data and then synthesize an assessment."

3.  **Implement Actionable `agent_input_data_preparation_notes`:**
    *   When `IntentDefiner`'s LLM call generates `agent_input_data_preparation_notes`, the `MRMOrchestrator` needs to:
        1.  Parse these notes (potentially using another LLM call if complex, or regex if simple instructions).
        2.  Trigger one or more *preparatory `Intent` calls* (likely simple `RETRIEVE_SPECIFIC_INFO` task type) to fetch the exact text snippets or data points the agent needs.
        3.  Populate the `agent_input_data` field of the *main* agent-invoking `Intent` with the results of these preparatory intents before calling `NodeProcessor.process_intent`. This makes agents much more effective.

**II. Robustness and Advanced Control Flow:**

1.  **Full Recursive Clarification Loop in `MRMOrchestrator`:**
    *   When `NodeProcessor.process_intent` results in `COMPLETED_WITH_CLARIFICATION_NEEDED` and `_should_attempt_auto_clarification` is true:
        1.  The orchestrator calls `IntentDefiner.define_clarification_intent_spec_via_llm`.
        2.  If a valid spec is returned, the orchestrator creates a new `Intent` object (linked to the original via `parent_intent_id`).
        3.  The `ReasoningNode`'s status is kept as `IN_PROGRESS` (or a new `AWAITING_CLARIFICATION_RESULT`), and this new clarification `Intent` is processed by `NodeProcessor`.
        4.  Manage retry limits for clarification on a given original problem.

2.  **Sophisticated Dependency Management (`_get_processing_order`):**
    *   Ensure the topological sort correctly handles dependencies not just between template-defined nodes but also between dynamically generated MC sub-nodes and their parent summary node (e.g., all MCs under `4.0...` must complete before `4.0...` itself can generate its summary intent).
    *   The `depends_on_nodes` field in `ReasoningNode` (populated from templates and for dynamic nodes) is key.

3.  **Confidence Aggregation and Propagation:**
    *   When an `Intent` completes, `NodeProcessor._estimate_confidence` provides a score.
    *   `ReasoningNode.update_status_based_on_children_and_intents` should aggregate these confidences. For a parent node, its confidence could be the average (or weighted average) of its children's confidences, potentially capped by the confidence of its own summary intent.
    *   The final report should display these confidence scores per section.

**III. Enhancing Subsidiary Agent Capabilities & Integration:**

1.  **Develop New, More Specific Agents:**
    *   **TransportImpactAgent:** Parse TA tables (headcounts, trip rates), compare parking against standards.
    *   **SustainabilityMetricsAgent:** Extract BNG values, energy performance figures, UGF scores.
    *   **HousingMetricsAgent:** Detailed parsing of housing schedules for unit mix, affordable % by tenure, space standard compliance.
    *   **(Future) GISAgent:** To perform spatial queries (e.g., "count listed buildings within 100m of site boundary X").

2.  **Standardized Agent Output Schemas:**
    *   Each agent should ideally return a well-defined JSON structure (its "report"). This makes it easier for the MRM (`NodeProcessor`'s synthesis step) to integrate agent findings. The `agent_input_data_preparation_notes` generated by `IntentDefiner` could even hint at the expected output schema from the agent.

3.  **Multimodal Input for Agents (Gemini 1.5 Pro/Flash or Vision models):**
    *   For agents like `VisualHeritageAssessmentAgent`, modify `_prepare_gemini_content` in `BaseSubsidiaryAgent` to handle image inputs (e.g., URLs, base64 data) if the underlying Gemini model supports it. The `IntentDefiner` would need to specify which images (e.g., from submitted plans, CGIs, site photos) are relevant for the agent's task.

**IV. System & Operational Improvements:**

1.  **Asynchronous Operations (`asyncio`):**
    *   Convert I/O-bound operations (database queries, ALL Gemini API calls) to use `async/await`. This is critical for performance, allowing the system to work on multiple intents or nodes concurrently where dependencies allow. This is a major architectural change.

2.  **Caching Strategy:**
    *   Cache LLM responses: If an identical prompt (including full context) is generated for an intent, consider returning a cached response to save API calls and time (use with caution if context freshness is paramount).
    *   Cache retrieved document sets for common queries.

3.  **Enhanced Logging and Monitoring:**
    *   More detailed structured logging (e.g., using Python's `logging` module) for easier debugging and performance analysis.
    *   Track token usage per API call.
    *   Monitor API error rates and implement exponential backoff for retries.

4.  **Configuration Management:**
    *   Move more settings from `config.py` into structured configuration files (e.g., YAML) for different environments (dev, staging, prod).
    *   Agent registry and model names could be part of this external config.

5.  **Testing Framework:**
    *   **Unit Tests:** For individual components (retriever, managers, agent base class logic).
    *   **Integration Tests:** For flows like "define intent -> process intent -> check output".
    *   **End-to-End Tests:** With mock application data and "golden" report outputs to check overall quality and regression.

**Iterative Focus for Immediate Next Steps (if I were to continue coding *now*):**

Given the current codebase, I would prioritize:

1.  **Full `_dynamically_expand_mc_node` using the `MATERIAL_CONSIDERATION_ONTOLOGY`:**
    *   Load the ontology from `mc_ontology_data/main_material_considerations.json`.
    *   Make the `_run_initial_application_scan_intent` more robust in its prompting to get themes.
    *   Implement the logic in `_dynamically_expand_mc_node` to match scanned themes to ontology entries and create well-parameterized child `ReasoningNode`s.

2.  **Refine `IntentDefiner.define_intent_spec_via_llm` for Dynamic MC Nodes:**
    *   When the `node.linked_ontology_entry_id` is present (meaning it's a dynamically created MC node), use the rich metadata from `self.mc_ontology.get_consideration_details(node.linked_ontology_entry_id)` to heavily guide the prompt to Gemini Pro for defining its intent spec. This makes the intent for each material consideration highly tailored.

3.  **Basic End-to-End Clarification Loop:**
    *   In `MRMOrchestrator.orchestrate_full_report_generation`, if a node finishes as `COMPLETED_WITH_CLARIFICATION_NEEDED` and `_should_attempt_auto_clarification` (for its last intent) returns true:
        1.  Call `IntentDefiner.define_clarification_intent_spec_via_llm`.
        2.  If a spec is returned, *reset the node's status to `PENDING`* and add the new clarification intent to a conceptual "next intent to run for this node" queue (or simply let the main loop pick it up because it's `PENDING` again).
        3.  This makes the main orchestration loop naturally handle reprocessing.

These three steps would make the core reasoning loop much more powerful and adaptive to the specific application being assessed.