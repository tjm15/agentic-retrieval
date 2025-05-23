# core_types.py
# (This is the complete version from the previous "Reproduce the full updated code" V8)
import uuid
import json
import time
from enum import Enum
from typing import List, Dict, Any, Optional, Union # ADDED Union


class IntentStatus(Enum):
    PENDING = "PENDING"; IN_PROGRESS = "IN_PROGRESS"; COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    COMPLETED_WITH_CLARIFICATION_NEEDED = "COMPLETED_WITH_CLARIFICATION_NEEDED"; FAILED = "FAILED"; SKIPPED = "SKIPPED"

class RetrievalSourceType(Enum):
    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"; AGENT_REPORT = "AGENT_REPORT"; EXTERNAL_DATA = "EXTERNAL_DATA"

class ProvenanceLog:
    def __init__(self, intent_id: Optional[uuid.UUID], task_description: str):
        self.log_id = uuid.uuid4(); self.intent_id = intent_id; self.task_description = task_description
        self.timestamp_start = time.time(); self.timestamp_end = None
        self.actions: List[Dict[str, Any]] = []; self.status = "STARTED"; self.result_summary: Optional[Any] = None
    def add_action(self, action_description: str, details: Optional[Dict] = None): self.actions.append({"time": time.time(), "action": action_description, "details": details or {}})
    def complete(self, status: str, result_summary: Optional[Any] = None):
        self.timestamp_end = time.time(); self.status = status; self.result_summary = result_summary
    def duration(self) -> Optional[float]: return self.timestamp_end - self.timestamp_start if self.timestamp_end and self.timestamp_start else None
    def __str__(self): return json.dumps(self.__dict__, default=lambda o: str(o) if isinstance(o, uuid.UUID) else o.__dict__ if hasattr(o, '__dict__') else str(o), indent=2)

class RetrievedItem:
    def __init__(self, source_type: RetrievalSourceType, content: Any, metadata: Dict):
        self.item_id = uuid.uuid4(); self.source_type = source_type; self.content = content; self.metadata = metadata
    def __str__(self): content_str = str(self.content); return f"RetrievedItem(type={self.source_type.value}, content_preview='{content_str[:100]}...', metadata={self.metadata})"

class SecurityAssessment: # ADDED CLASS
    def __init__(self, assessment_id: uuid.UUID, focus_area: str, findings: List[str], risk_level: str, recommendations: List[str]):
        self.assessment_id = assessment_id
        self.focus_area = focus_area
        self.findings = findings
        self.risk_level = risk_level # e.g., "Low", "Medium", "High"
        self.recommendations = recommendations
        self.timestamp = time.time()

    def __str__(self):
        return json.dumps(self.__dict__, default=str, indent=2)

class Intent:
    def __init__(self, parent_node_id: str, task_type: str, application_refs: List[str],
                 data_requirements: Optional[Dict] = None, satisfaction_criteria: Optional[List[Dict]] = None,
                 parent_intent_id: Optional[uuid.UUID] = None, retrieval_config: Optional[Dict] = None,
                 agent_to_invoke: Optional[str] = None, agent_input_data: Optional[Dict] = None,
                 assessment_focus: Optional[str] = None, output_format_request: str = "JSON_DetailedAssessment_And_DraftReportText",
                 context_data_from_prior_steps: Optional[Dict] = None, full_documents_context: Optional[List[Dict[str, str]]] = None,
                 chunk_context: Optional[List[Dict[str, Any]]] = None, llm_policy_context_summary: Optional[List[Dict]] = None,
                 image_context: Optional[List[Dict[str, Any]]] = None, 
                 visual_assessment_text: Optional[str] = None,
                 security_assessments: Optional[List[SecurityAssessment]] = None): # ADDED
        self.intent_id = uuid.uuid4(); self.parent_node_id = parent_node_id; self.parent_intent_id = parent_intent_id
        self.task_type = task_type; self.application_refs = application_refs
        self.data_requirements = data_requirements or {"schema": {}}; self.satisfaction_criteria = satisfaction_criteria or [{"type": "GENERIC_COMPLETION"}]
        self.retrieval_config = retrieval_config or {}; self.agent_to_invoke = agent_to_invoke; self.agent_input_data = agent_input_data or {}
        self.assessment_focus = assessment_focus or "General assessment"; self.output_format_request = output_format_request
        self.context_data_from_prior_steps = context_data_from_prior_steps or {}; self.llm_policy_context_summary = llm_policy_context_summary or []
        self.full_documents_context = full_documents_context or []; self.chunk_context = chunk_context or []
        self.image_context = image_context or [] 
        self.visual_assessment_text = visual_assessment_text
        self.security_assessments = security_assessments or [] # ADDED
        self.status = IntentStatus.PENDING; self.result: Optional[List[RetrievedItem]] = None
        self.synthesized_text_output: Optional[str] = None; self.structured_json_output: Optional[Dict] = None
        self.error_message: Optional[str] = None; self.confidence_score: Optional[float] = None
        self.provenance = ProvenanceLog(self.intent_id, f"Intent: {self.task_type} for node {self.parent_node_id}")
    def __str__(self): return f"Intent({self.intent_id}, Task: {self.task_type}, Node: {self.parent_node_id}, Status: {self.status.value})"

class ReasoningNode:
    def __init__(self, node_id: str, description: str):
        self.node_id = node_id; self.description = description; self.status = IntentStatus.PENDING; self.application_refs: List[str] = []
        self.node_type_tag: Optional[str] = None; self.generic_material_considerations: List[str] = []
        self.specific_policy_focus_ids: List[str] = []; self.key_evidence_document_types: List[str] = []
        self.linked_ontology_entry_id: Optional[str] = None; self.is_dynamic_parent_node: bool = False
        self.agent_to_invoke_hint: Optional[str] = None; self.depends_on_nodes: List[str] = []
        self.sub_nodes: Dict[str, ReasoningNode] = {}; self.intents_issued: List[Intent] = []
        self.final_structured_data: Optional[Dict] = None; self.final_synthesized_text: Optional[str] = None
        self.node_level_provenance: Optional[ProvenanceLog] = None; self.confidence_score: Optional[float] = None
        self.data_requirements_schema_hint: Optional[Dict] = None # Added from MCOntology

    def add_sub_node(self, sub_node: 'ReasoningNode'):
        sub_node.application_refs = self.application_refs; sub_node_key = sub_node.node_id.split('/')[-1]; self.sub_nodes[sub_node_key] = sub_node
    def get_sub_node_output_by_key(self, sub_node_key: str) -> Optional[Dict]:
        target_node = self.sub_nodes.get(sub_node_key)
        if target_node and (target_node.status == IntentStatus.COMPLETED_SUCCESS or target_node.status == IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED):
            return {"node_id": target_node.node_id, "text_summary": target_node.final_synthesized_text, "structured_data": target_node.final_structured_data, "confidence": getattr(target_node, 'confidence_score', None)}
        return None
    def update_status_based_on_children_and_intents(self):
        if self.sub_nodes:
            all_children_ok=True; any_fail=False; any_clarify=False; any_prog_pend=False; child_confs=[]
            for child in self.sub_nodes.values():
                if child.status == IntentStatus.FAILED: any_fail=True; break
                if child.status == IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED: any_clarify=True
                if child.status in [IntentStatus.IN_PROGRESS, IntentStatus.PENDING]: any_prog_pend=True
                if child.status != IntentStatus.COMPLETED_SUCCESS: all_children_ok=False
                if child.confidence_score is not None: child_confs.append(child.confidence_score)
            if any_fail: self.status=IntentStatus.FAILED
            elif any_prog_pend: self.status=IntentStatus.IN_PROGRESS
            elif any_clarify: self.status=IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED
            elif all_children_ok: self.status=IntentStatus.COMPLETED_SUCCESS
            else: self.status=IntentStatus.PENDING
            if child_confs: self.confidence_score=sum(child_confs)/len(child_confs) if child_confs else None
            elif self.intents_issued and self.intents_issued[-1].confidence_score is not None : self.confidence_score=self.intents_issued[-1].confidence_score # For summary nodes of dynamic children
        elif self.intents_issued:
            last_intent=self.intents_issued[-1]; self.status=last_intent.status
            if self.status in [IntentStatus.COMPLETED_SUCCESS,IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED]:
                self.final_structured_data=last_intent.structured_json_output; self.final_synthesized_text=last_intent.synthesized_text_output
                self.confidence_score=last_intent.confidence_score
        else: self.status=IntentStatus.PENDING; self.confidence_score=None
    def __str__(self): conf_str = f", Conf: {self.confidence_score:.2f}" if self.confidence_score is not None else ""; return f"Node({self.node_id}, Status: {self.status.value}{conf_str}, Sub: {len(self.sub_nodes)}, Intents: {len(self.intents_issued)})"
