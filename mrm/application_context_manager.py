# mrm/application_context_manager.py
"""
Application Context Manager for MRM Orchestrator
Handles application context caching and summarization
"""

from typing import Dict, List, Any
from db_manager import DatabaseManager


class ApplicationContextManager:
    """Manages application context caching and retrieval for MRM processing."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.application_context_cache: Dict[str, Dict[str, Any]] = {}
    
    def get_or_create_application_context_summary(self, application_refs: List[str], app_display_name: str) -> Dict[str, Any]:
        """
        Get or create application context summary with caching.
        
        Args:
            application_refs: List of application reference IDs
            app_display_name: Display name for the application
            
        Returns:
            Dictionary containing application context summary
        """
        cache_key = f"app_summary_{'_'.join(sorted(application_refs))}"
        if cache_key in self.application_context_cache:
            return self.application_context_cache[cache_key]
        
        # Query for site description
        site_desc_query = """
            SELECT chunk_text 
            FROM document_chunks dc 
            JOIN documents d ON dc.doc_id = d.doc_id 
            WHERE d.source = ANY(%s) 
            AND (d.document_type ILIKE %s OR dc.tags @> ARRAY[%s]) 
            ORDER BY d.upload_date DESC, dc.page_number ASC 
            LIMIT 1
        """
        
        site_text_row = self.db_manager.execute_query(
            site_desc_query, 
            (application_refs, "%SiteDescription%", "site_description"), 
            fetch_one=True
        )
        site_summary = (
            site_text_row['chunk_text'][:500] + "..." 
            if site_text_row and site_text_row['chunk_text'] 
            else f"No detailed site description found for {app_display_name} via placeholder query."
        )

        # Query for proposal description
        proposal_text_row = self.db_manager.execute_query(
            site_desc_query, 
            (application_refs, "%ProposalDescription%", "proposal_summary"), 
            fetch_one=True
        )
        proposal_summary = (
            proposal_text_row['chunk_text'][:500] + "..." 
            if proposal_text_row and proposal_text_row['chunk_text'] 
            else f"No detailed proposal description found for {app_display_name} via placeholder query."
        )

        summary = {
            "application_name": app_display_name,
            "application_identifiers": application_refs,
            "site_summary_placeholder": site_summary,
            "proposal_summary_placeholder": proposal_summary,
            "key_documents_hint": ["ApplicationForm.pdf", "PlanningStatement.pdf", "DesignAccessStatement.pdf"]
        }
        
        self.application_context_cache[cache_key] = summary
        return summary
    
    def clear_cache(self):
        """Clear the application context cache."""
        self.application_context_cache.clear()
    
    def get_cache_size(self) -> int:
        """Get the current cache size."""
        return len(self.application_context_cache)
