# mrm/intent_definer.py
# Enhanced IntentDefiner with Thematic Semantic Policy Search
# Performs semantic policy retrieval before generating Intent specifications

import time
import json
import signal
from contextlib import contextmanager
from google import genai
from typing import cast
from google.genai.types import GenerateContentConfigOrDict, GenerateContentConfigDict  # <-- Add GenerateContentConfigDict
from typing import Dict, List, Optional, Any

# Assuming these are correctly imported relative to this file's location
from core_types import ReasoningNode, Intent, ProvenanceLog
from knowledge_base.policy_manager import PolicyManager
from config import MRM_MODEL_NAME, INTENT_DEFINER_GEN_CONFIG

class IntentDefiner:
    def __init__(self, policy_manager: PolicyManager, api_key: str):
        self.policy_manager = policy_manager
        # Initialize Gemini client with timeout configuration
        self.client = genai.Client(api_key=api_key)
        print(f"INFO: Enhanced IntentDefiner initialized with semantic policy search capability.")

    def _perform_thematic_policy_search(self, node: ReasoningNode, application_display_name: str, 
                                      node_provenance: ProvenanceLog) -> List[Dict[str, Any]]:
        """
        Perform semantic policy search using thematic descriptors before generating Intent specs.
        This replaces rigid keyword matching with intelligent semantic policy discovery.
        """
        node_provenance.add_action("Starting thematic semantic policy search")
        
        # Build comprehensive search terms from node metadata
        search_themes = []
        semantic_queries = []
        
        # Use thematic policy descriptors as primary search themes
        if node.thematic_policy_descriptors:
            search_themes.extend(node.thematic_policy_descriptors)
            # Create semantic queries from thematic descriptors
            for descriptor in node.thematic_policy_descriptors[:3]:  # Top 3 for focused search
                semantic_queries.append(f"planning policy for {descriptor}")
        
        # Supplement with material considerations and policy focus
        search_themes.extend(node.generic_material_considerations or [])
        search_themes.extend(node.specific_policy_focus_ids or [])
        
        # Add node context for more targeted search
        context_query = f"planning policy guidance for {node.description} assessment in {application_display_name}"
        semantic_queries.append(context_query)
        
        node_provenance.add_action("Compiled thematic search parameters", {
            "themes_count": len(search_themes),
            "semantic_queries_count": len(semantic_queries),
            "primary_descriptors": node.thematic_policy_descriptors[:3]
        })
        
        # Perform multiple semantic searches to capture diverse relevant policies
        all_relevant_policies = []
        
        for i, semantic_query in enumerate(semantic_queries[:3]):  # Limit to avoid over-querying
            try:
                policies = self.policy_manager.search_policies(
                    themes=search_themes[:5],  # Top themes
                    semantic_query=semantic_query,
                    limit=8  # More policies per search
                )
                
                # Add search context to policies
                for policy in policies:
                    policy['search_context'] = f"semantic_query_{i+1}"
                    policy['search_query'] = semantic_query
                
                all_relevant_policies.extend(policies)
                node_provenance.add_action(f"Semantic search {i+1} completed", {
                    "query": semantic_query[:100],
                    "results_count": len(policies)
                })
                
            except Exception as e:
                node_provenance.add_action(f"Semantic search {i+1} failed", {"error": str(e)})
                print(f"WARN: Semantic policy search failed: {e}")
        
        # Deduplicate policies by policy_clause_id
        unique_policies = {}
        for policy in all_relevant_policies:
            policy_id = policy.get('policy_clause_id') or policy.get('id')
            if policy_id not in unique_policies:
                unique_policies[policy_id] = policy
        
        final_policies = list(unique_policies.values())
        
        # Sort by semantic relevance (distance) if available
        final_policies.sort(key=lambda p: p.get('semantic_distance', 1.0))
        
        node_provenance.add_action("Thematic policy search completed", {
            "total_policies_found": len(final_policies),
            "unique_sources": list(set(p.get('policy_document_source', 'unknown') for p in final_policies))
        })
        
        return final_policies[:12]  # Return top 12 most relevant policies

    def define_intent_spec_via_llm(self, node: ReasoningNode, application_refs: List[str], application_display_name: str,
                                   report_type: str, site_summary_context: Optional[str], proposal_summary_context: Optional[str],
                                   direct_dependency_outputs: Optional[Dict], node_provenance: ProvenanceLog) -> Optional[Dict[str, Any]]:
        
        node_provenance.add_action("Enhanced LLM-driven Intent definition started")
        
        # Perform thematic semantic policy search BEFORE generating intent spec
        relevant_policies = self._perform_thematic_policy_search(node, application_display_name, node_provenance)
        
        # Build rich policy context for LLM prompt
        policy_context_for_prompt = []
        for policy in relevant_policies:
            policy_summary = {
                "id": policy.get('policy_id_tag') or policy.get('id', 'unknown'),
                "title": policy.get('policy_document_title', 'Unknown Policy'),
                "source": policy.get('policy_document_source', 'Unknown Source'),
                "text": policy.get('text_snippet', '')[:300],  # Truncate for prompt
                "relevance": f"Found via: {policy.get('search_context', 'general')}"
            }
            if policy.get('semantic_distance') is not None:
                policy_summary['semantic_similarity'] = round(1.0 - float(policy.get('semantic_distance', 0.5)), 3)
            policy_context_for_prompt.append(policy_summary)
        
        # Enhanced prompt with thematic policy context
        intent_spec_prompt = f"""You are an expert Planning Assessment Orchestrator AI. You have access to comprehensive policy context discovered through semantic analysis.

REPORT SECTION TO PROCESS:
Node ID: {node.node_id}
Description: "{node.description}"
Node Type: {node.node_type_tag}

THEMATIC POLICY CONTEXT (discovered via semantic search):
{json.dumps(policy_context_for_prompt, indent=2)[:2000]}...

NODE METADATA:
- Generic Material Considerations: {node.generic_material_considerations}
- Specific Policy Focus Areas: {node.specific_policy_focus_ids}
- Key Evidence Document Types: {node.key_evidence_document_types}
- Thematic Policy Descriptors: {node.thematic_policy_descriptors}
- Suggested Agent: {node.agent_to_invoke_hint}

APPLICATION CONTEXT:
- Report Type: {report_type}
- Application: "{application_display_name}"
- References: {application_refs}
- Site Context: {str(site_summary_context)[:200] if site_summary_context else 'N/A'}...
- Proposal Context: {str(proposal_summary_context)[:200] if proposal_summary_context else 'N/A'}...

DEPENDENCY OUTPUTS:
{json.dumps(direct_dependency_outputs, indent=1, default=str)[:400] if direct_dependency_outputs else 'None'}...

TASK: Generate a comprehensive Intent specification that leverages the discovered policy context. Create a JSON object with these exact keys:

1. "task_type": The specific assessment task (e.g., "PolicyFrameworkSummary", "MaterialConsiderationAssessment", "SiteDescription")
2. "assessment_focus": Detailed description of what specifically to assess, informed by the policy context
3. "policy_context_tags_to_consider": Array of policy IDs/themes to prioritize (extracted from the discovered policies)
4. "retrieval_config": {{
     "hybrid_search_terms": [array of specific search terms for document retrieval],
     "semantic_search_query_text": "focused semantic query for retrieving relevant application documents",
     "document_type_filters": [array of document types to focus on]
   }}
5. "data_requirements_schema": JSON schema defining the structured data to extract
6. "agent_to_invoke": Name of subsidiary agent to use (if any) - use "PolicyAnalysisAgent" for policy-heavy nodes, "VisualHeritageAssessment_GeminiFlash_V1" for heritage/design, or null
7. "agent_input_data_preparation_notes": Instructions for preparing agent input
8. "output_format_request_for_llm": Specific format requirements for the LLM output

IMPORTANT: 
- Base your assessment_focus on the discovered policy requirements
- Extract specific policy IDs from the policy context for policy_context_tags_to_consider
- Make retrieval_config highly targeted based on the node type and evidence requirements
- For material consideration nodes, create detailed data schemas reflecting policy requirements
- Use appropriate agents: "PolicyAnalysisAgent" for policy analysis, "VisualHeritageAssessment_GeminiFlash_V1" for heritage/visual assessment

Output ONLY the JSON specification:"""

        node_provenance.add_action("Prompting LLM with enhanced policy context", {
            "prompt_length": len(intent_spec_prompt),
            "policies_included": len(policy_context_for_prompt)
        })
        
        response = None  # Ensure response is always defined
        try:
            time.sleep(1.0)  # Rate limiting
            print(f"DEBUG: Sending request to Gemini API for node {node.node_id}...")
            print(f"DEBUG: Prompt length: {len(intent_spec_prompt)} chars, Policy context: {len(policy_context_for_prompt)} policies")
            print(f"DEBUG: This may take up to 5 minutes - Gemini is processing complex policy analysis...")
            # Add timeout and better error handling with retry mechanism
            max_retries = 2
            timeout_seconds = 300  # 5 minute timeout per attempt - Gemini can be slow
            
            for attempt in range(max_retries):
                try:
                    print(f"DEBUG: API attempt {attempt + 1}/{max_retries} (allowing up to {timeout_seconds}s per attempt)...")
                    # Use typing.cast to satisfy type checker
                    api_config = cast(GenerateContentConfigDict, dict(INTENT_DEFINER_GEN_CONFIG))
                    response = self.client.models.generate_content(
                        model=MRM_MODEL_NAME,
                        contents=[intent_spec_prompt],
                        config=api_config
                    )
                    print(f"DEBUG: Received response from Gemini API for node {node.node_id}")
                    break
                    
                except Exception as api_error:
                    print(f"WARN: API attempt {attempt + 1} failed: {type(api_error).__name__} - {str(api_error)[:200]}")
                    if attempt == max_retries - 1:
                        print(f"ERROR: All {max_retries} API attempts failed for node {node.node_id}")
                        raise api_error
                    print(f"Retrying in 10 seconds...")
                    time.sleep(10)  # Wait longer before retry
            
            if response is None:
                raise RuntimeError("No response received from Gemini API after all retries.")
            
            # Robust response parsing
            raw_json_spec_text = self._extract_response_text(response)
            if not raw_json_spec_text:
                raise ValueError("No valid text response from Gemini API.")
            
            intent_spec_dict = json.loads(raw_json_spec_text)
            
            # Validate required keys
            required_keys = ["task_type", "assessment_focus", "retrieval_config"]
            if not all(k in intent_spec_dict for k in required_keys):
                missing_keys = [k for k in required_keys if k not in intent_spec_dict]
                raise ValueError(f"LLM-generated Intent Spec missing required keys: {missing_keys}")
            
            node_provenance.add_action("Enhanced Intent Spec generated successfully", {
                "keys_generated": list(intent_spec_dict.keys()),
                "policies_considered": len(relevant_policies),
                "agent_specified": intent_spec_dict.get('agent_to_invoke')
            })
            
            return intent_spec_dict
            
        except Exception as e:
            error_msg = f"Enhanced Intent Spec generation failed for {node.node_id}: {type(e).__name__} - {e}"
            print(f"ERROR: {error_msg}")
            print(f"Prompt preview: {intent_spec_prompt[:500]}...")
            node_provenance.complete("FAILED", {"error": error_msg})
            return None

    def _extract_response_text(self, response) -> Optional[str]:
        """Extract text from Gemini API response with multiple fallback methods."""
        # Try direct text access
        if hasattr(response, 'text') and response.text:
            return response.text
        
        # Try candidates approach
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                content = candidate.content
                if hasattr(content, 'parts') and content.parts:
                    text_parts = []
                    for part in content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    if text_parts:
                        return "".join(text_parts)
        
        return None

    def define_clarification_intent_spec_via_llm(self, original_intent: Intent, clarification_reason: Optional[str], 
                                               node_provenance: ProvenanceLog) -> Optional[Dict[str, Any]]:
        """Enhanced clarification intent generation with policy context awareness."""
        
        node_provenance.add_action("Generating clarification intent with policy awareness", {
            "original_reason": clarification_reason
        })
        
        # Build clarification prompt with policy context
        prompt = f"""The original Intent for application "{original_intent.application_refs[0] if original_intent.application_refs else 'N/A'}" needs clarification.

ORIGINAL INTENT CONTEXT:
- Node: {original_intent.parent_node_id}
- Task Type: {original_intent.task_type}
- Clarification Reason: {clarification_reason or original_intent.error_message}
- Previous Output: {str(original_intent.synthesized_text_output)[:300] if original_intent.synthesized_text_output else 'No previous output'}

POLICY CONTEXT AVAILABLE:
- Policy tags considered: {original_intent.policy_context_tags_to_consider or 'None specified'}

TASK: Generate a refined JSON Intent specification that addresses the clarification need while maintaining focus on policy compliance. The new Intent should:
1. Target the specific gap or issue identified
2. Use more focused retrieval parameters  
3. Request more specific output format
4. Consider additional policy context if needed

Output ONLY a JSON specification with the same structure as the original Intent but refined for clarity and focus.

Required JSON keys: "task_type", "assessment_focus", "policy_context_tags_to_consider", "retrieval_config", "data_requirements_schema", "agent_to_invoke", "agent_input_data_preparation_notes", "output_format_request_for_llm"

Parent node ID will be: "{original_intent.parent_node_id}"
"""

        response = None  # Ensure response is always defined
        try:
            time.sleep(0.8)  # Rate limiting
            print(f"DEBUG: Generating clarification intent - this may take 2-3 minutes...")
            
            # Add timeout and retry for clarification calls
            api_config = cast(GenerateContentConfigDict, dict(INTENT_DEFINER_GEN_CONFIG))
            response = self.client.models.generate_content(
                model=MRM_MODEL_NAME,
                contents=[prompt],
                config=api_config
            )
            print(f"DEBUG: Clarification intent response received")
            
            raw_json_spec_text = self._extract_response_text(response)
            if not raw_json_spec_text:
                raise ValueError("No valid text response from Gemini API.")
            
            spec = json.loads(raw_json_spec_text)
            
            # Inject required fields for clarification intent
            spec["application_refs"] = original_intent.application_refs
            spec["parent_node_id"] = original_intent.parent_node_id
            spec["parent_intent_id"] = original_intent.intent_id
            
            node_provenance.add_action("Enhanced clarification spec generated", {
                "original_intent_id": str(original_intent.intent_id),
                "refined_task_type": spec.get("task_type")
            })
            
            return spec
            
        except Exception as e:
            error_msg = f"Enhanced clarification spec generation failed: {type(e).__name__} - {e}"
            node_provenance.add_action("Clarification spec generation failed", {"error": error_msg})
            print(f"ERROR: {error_msg}")
            return None
