# mrm/intent_definer.py
# Enhanced IntentDefiner with Thematic Semantic Policy Search
# Performs semantic policy retrieval before generating Intent specifications

import time
import json
import signal
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

# Assuming these are correctly imported relative to this file's location
from core_types import ReasoningNode, Intent, ProvenanceLog
from knowledge_base.policy_manager import PolicyManager
from config import MRM_MODEL_NAME, INTENT_DEFINER_GEN_CONFIG, CACHE_ENABLED, create_llm_client
from cache.gemini_cache import GeminiResponseCache

def load_prompt_from_file(file_path: str) -> str:
    with open(file_path, 'r') as f:
        return f.read()

class IntentDefiner:
    def __init__(self, policy_manager: PolicyManager, api_key: str):
        self.policy_manager = policy_manager
        # Initialize LLM client with fallback support
        self.llm_client = create_llm_client()
        
        # Initialize cache if enabled
        self.cache = GeminiResponseCache() if CACHE_ENABLED else None
        
        # Load prompts from files
        self.intent_spec_prompt_template = load_prompt_from_file("/home/tim-mayoh/repos/agentic-retrieval/prompts/intent_definer_prompt.txt")
        self.clarification_prompt_template = load_prompt_from_file("/home/tim-mayoh/repos/agentic-retrieval/prompts/clarification_prompt.txt")
        
        print(f"INFO: Enhanced IntentDefiner initialized with LLM client: {self.llm_client.__class__.__name__}")
        if CACHE_ENABLED:
            print(f"INFO: IntentDefiner caching enabled")

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
        intent_spec_prompt = self.intent_spec_prompt_template.format(
            node_id=node.node_id,
            description=node.description,
            node_type_tag=node.node_type_tag,
            policy_context_json=json.dumps(policy_context_for_prompt, indent=2)[:2000] + "...",
            generic_material_considerations=node.generic_material_considerations,
            specific_policy_focus_ids=node.specific_policy_focus_ids,
            key_evidence_document_types=node.key_evidence_document_types,
            thematic_policy_descriptors=node.thematic_policy_descriptors,
            agent_to_invoke_hint=node.agent_to_invoke_hint,
            report_type=report_type,
            application_display_name=application_display_name,
            application_refs=application_refs,
            site_summary_context=str(site_summary_context)[:200] + "..." if site_summary_context else 'N/A',
            proposal_summary_context=str(proposal_summary_context)[:200] + "..." if proposal_summary_context else 'N/A',
            direct_dependency_outputs_json=json.dumps(direct_dependency_outputs, indent=1, default=str)[:400] + "..." if direct_dependency_outputs else 'None'
        )

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
            timeout_seconds = 600  # 10 minute timeout per attempt - increased for complex material consideration analysis
            
            # Try cache first if enabled
            response_text = ""
            if self.cache:
                # Convert config to dictionary format for cache compatibility
                config_dict = dict(INTENT_DEFINER_GEN_CONFIG)
                cached_response = self.cache.get(intent_spec_prompt, config_dict, MRM_MODEL_NAME)
                if cached_response:
                    print(f"DEBUG: Using cached response for node {node.node_id}")
                    # Convert cached response to text format
                    text = getattr(cached_response, "text", None)
                    if not text and hasattr(cached_response, "candidates") and cached_response.candidates:
                        first_candidate = cached_response.candidates[0]
                        content = getattr(first_candidate, "content", None)
                        parts = getattr(content, "parts", None) if content else None
                        if parts:
                            text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
                    response_text = text or ""
                else:
                    print(f"DEBUG: No cache hit, making API call for node {node.node_id}")
                    # Make API call with retries
                    for attempt in range(max_retries):
                        try:
                            print(f"DEBUG: API attempt {attempt + 1}/{max_retries} (allowing up to {timeout_seconds}s per attempt)...")
                            llm_response = self.llm_client.generate_content(
                                contents=[intent_spec_prompt],
                                config=dict(INTENT_DEFINER_GEN_CONFIG),
                                model=MRM_MODEL_NAME
                            )
                            response_text = llm_response.text
                            print(f"DEBUG: Received response from {llm_response.provider} ({llm_response.model_used}) for node {node.node_id}")
                            # Cache the response in original format if possible
                            if hasattr(llm_response, 'raw_response') and llm_response.raw_response:
                                self.cache.put(intent_spec_prompt, config_dict, MRM_MODEL_NAME, llm_response.raw_response)
                            break
                            
                        except Exception as api_error:
                            print(f"WARN: API attempt {attempt + 1} failed: {type(api_error).__name__} - {str(api_error)[:200]}")
                            if attempt == max_retries - 1:
                                print(f"ERROR: All {max_retries} API attempts failed for node {node.node_id}")
                                raise api_error
                            print(f"Retrying in 10 seconds...")
                            time.sleep(10)  # Wait longer before retry
            else:
                # No caching, make direct API call with retries
                for attempt in range(max_retries):
                    try:
                        print(f"DEBUG: API attempt {attempt + 1}/{max_retries} (allowing up to {timeout_seconds}s per attempt)...")
                        llm_response = self.llm_client.generate_content(
                            contents=[intent_spec_prompt],
                            config=dict(INTENT_DEFINER_GEN_CONFIG),
                            model=MRM_MODEL_NAME
                        )
                        response_text = llm_response.text
                        print(f"DEBUG: Received response from {llm_response.provider} ({llm_response.model_used}) for node {node.node_id}")
                        break
                        
                    except Exception as api_error:
                        print(f"WARN: API attempt {attempt + 1} failed: {type(api_error).__name__} - {str(api_error)[:200]}")
                        if attempt == max_retries - 1:
                            print(f"ERROR: All {max_retries} API attempts failed for node {node.node_id}")
                            raise api_error
                        print(f"Retrying in 10 seconds...")
                        time.sleep(10)  # Wait longer before retry
            
            if not response_text:
                raise RuntimeError("No response received from LLM API after all retries.")
            
            # Parse the JSON response directly
            if not response_text:
                raise ValueError("No valid text response from LLM API.")
            
            intent_spec_dict = json.loads(response_text)
            
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
        prompt = self.clarification_prompt_template.format(
            application_ref=original_intent.application_refs[0] if original_intent.application_refs else 'N/A',
            parent_node_id=original_intent.parent_node_id,
            task_type=original_intent.task_type,
            clarification_reason=clarification_reason or original_intent.error_message,
            previous_output=str(original_intent.synthesized_text_output)[:300] if original_intent.synthesized_text_output else 'No previous output',
            policy_context_tags_to_consider=original_intent.policy_context_tags_to_consider or 'None specified'
        )

        response = None  # Ensure response is always defined
        try:
            time.sleep(0.8)  # Rate limiting
            print(f"DEBUG: Generating clarification intent - this may take 2-3 minutes...")
            
            # Try cache first if enabled
            response_text = ""
            if self.cache:
                # Convert config to dictionary format for cache compatibility
                config_dict = dict(INTENT_DEFINER_GEN_CONFIG)
                cached_response = self.cache.get(prompt, config_dict, MRM_MODEL_NAME)
                if cached_response:
                    print(f"DEBUG: Using cached clarification response")
                    # Convert cached response to text format
                    text = getattr(cached_response, "text", None)
                    if not text and hasattr(cached_response, "candidates") and cached_response.candidates:
                        first_candidate = cached_response.candidates[0]
                        content = getattr(first_candidate, "content", None)
                        parts = getattr(content, "parts", None) if content else None
                        if parts:
                            text = "".join([getattr(p, 'text', '') for p in parts if getattr(p, 'text', None)])
                    response_text = text or ""
                else:
                    print(f"DEBUG: No cache hit for clarification, making API call")
                    llm_response = self.llm_client.generate_content(
                        contents=[prompt],
                        config=dict(INTENT_DEFINER_GEN_CONFIG),
                        model=MRM_MODEL_NAME
                    )
                    response_text = llm_response.text
                    print(f"DEBUG: Clarification intent response received from {llm_response.provider}")
                    # Cache the response in original format if possible
                    if hasattr(llm_response, 'raw_response') and llm_response.raw_response:
                        self.cache.put(prompt, config_dict, MRM_MODEL_NAME, llm_response.raw_response)
            else:
                # No caching, make direct API call
                llm_response = self.llm_client.generate_content(
                    contents=[prompt],
                    config=dict(INTENT_DEFINER_GEN_CONFIG),
                    model=MRM_MODEL_NAME
                )
                response_text = llm_response.text
                print(f"DEBUG: Clarification intent response received from {llm_response.provider}")
            
            if not response_text:
                raise ValueError("No valid text response from LLM API.")
            
            spec = json.loads(response_text)
            
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
