# Agentic Retrieval Planning AI

A modular, open-source framework for agentic, LLM-driven planning application assessment and report generation. This project demonstrates a generalized architecture for orchestrating reasoning, retrieval, and assessment using LLMs (e.g., Gemini), knowledge base managers, and specialized agents.

## Features
- **Modular Orchestration:** Central `MRMOrchestrator` coordinates intent definition, retrieval, and agentic assessment.
- **Knowledge Base Management:** Pluggable managers for report templates, material consideration ontology, and policy knowledge base.
- **Agentic Reasoning:** Specialized agents (e.g., `VisualHeritageAgent`) process context and generate structured outputs.
- **Retrieval-Augmented Generation:** Hybrid and semantic retrieval from a Postgres/pgvector document store.
- **Provenance Logging:** Track actions, context, and results for every reasoning step.
- **Extensible:** Add new agents, templates, or ontologies for other planning domains.

## Directory Structure
```
agentic-retrieval/
├── main.py
├── config.py
├── core_types.py
├── db_manager.py
├── requirements.txt
├── schema.sql
├── README.md
├── DOCS.md
├── LICENSE
├── TODO.md
├── agents/
│   ├── __init__.py
│   ├── base_agent.py
│   └── visual_heritage_agent.py
├── mrm/
│   ├── __init__.py
│   ├── mrm_orchestrator.py
│   ├── intent_definer.py
│   └── node_processor.py
├── retrieval/
│   ├── __init__.py
│   └── retriever.py
├── knowledge_base/
│   ├── __init__.py
│   ├── report_template_manager.py
│   ├── material_consideration_ontology.py
│   └── policy_manager.py
├── report_templates/
│   └── default_major_hybrid.json
├── mc_ontology_data/
│   └── main_material_considerations.json
├── policy_kb/
│   └── nppf_sample.json
```

## Quickstart

### 1. Prerequisites
- Python 3.9+
- PostgreSQL with [pgvector](https://github.com/pgvector/pgvector) extension
- Google Gemini API key

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_gemini_api_key
DB_NAME=planning_ai_db
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
```

### 4. Database Setup
Ensure PostgreSQL is running and create the database. Then run the schema:
```bash
psql -U your_db_user -d planning_ai_db -f schema.sql
```

### 5. Run the System
```bash
python main.py
```
- On first run, default templates and KB files will be created if missing.
- Minimal sample data is ingested for demonstration.

## How It Works
- **main.py**: Entry point. Loads config, initializes managers, sets up DB, and runs the `MRMOrchestrator`.
- **`MRMOrchestrator`**: Builds a reasoning tree from the report template, issues intents, retrieves context, and invokes agents.
- **Agents**: Specialized LLM-driven modules (e.g., `VisualHeritageAgent`) process context and generate structured outputs.
- **Knowledge Base Managers**: Handle report templates, material consideration ontology, and policy KB. Create default files if missing.
- **Retrieval**: Hybrid and semantic search over document chunks using pgvector embeddings.

## Extending the System
- **Add new agents** in `agents/` and register them in the orchestrator.
- **Add new report templates** in `report_templates/`.
- **Expand ontology or policy KB** in their respective folders.

## License
AGPLv3 License. See the `LICENSE` file for details.

## Disclaimer
This is a conceptual, research-oriented project. LLM outputs and agent logic are for demonstration and may require further development for production use.

## Contributors
- Tim Mayoh

---
For questions or contributions, please open an issue or pull request.
