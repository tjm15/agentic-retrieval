# mrm/report_generator.py
"""
Report Generator for MRM Orchestrator
Handles final report generation and formatting
"""

import json
from typing import Dict, List, Any, Optional
from core_types import ReasoningNode, ProvenanceLog


class ReportGenerator:
    """Generates final reports from processed reasoning trees."""
    
    def __init__(self):
        self.report_cache = {}
    
    def generate_final_report_text(self, root_node: ReasoningNode) -> str:
        """
        Generate the final report text from the processed reasoning tree.
        
        Args:
            root_node: Root node of the processed reasoning tree
            
        Returns:
            Formatted report text
        """
        def format_node_recursive(node: ReasoningNode, indent_level: int = 0) -> str:
            """Recursively format nodes into text report."""
            indent = "  " * indent_level
            result = f"{indent}# {node.node_id}\n"
            result += f"{indent}{node.description}\n"
            
            if node.status:
                result += f"{indent}Status: {node.status.value}\n"
            
            if node.confidence_score is not None:
                result += f"{indent}Confidence: {node.confidence_score:.2f}\n"
            
            if node.final_synthesized_text:
                result += f"{indent}Content:\n{node.final_synthesized_text}\n"
            
            result += "\n"
            
            # Process sub-nodes
            for sub_node in node.sub_nodes.values():
                result += format_node_recursive(sub_node, indent_level + 1)
            
            return result
        
        report_text = "# Planning Assessment Report\n\n"
        report_text += format_node_recursive(root_node)
        
        return report_text
    
    def generate_structured_report(self, root_node: ReasoningNode) -> Dict[str, Any]:
        """
        Generate a structured JSON report from the reasoning tree.
        
        Args:
            root_node: Root node of the processed reasoning tree
            
        Returns:
            Structured report as dictionary
        """
        def node_to_dict(node: ReasoningNode) -> Dict[str, Any]:
            """Convert a node to dictionary representation."""
            node_dict = {
                "node_id": node.node_id,
                "description": node.description,
                "status": node.status.value if node.status else None,
                "confidence_score": node.confidence_score,
                "final_synthesized_text": node.final_synthesized_text,
                "final_structured_data": node.final_structured_data,
                "node_type_tag": node.node_type_tag,
                "sub_nodes": {}
            }
            
            # Add sub-nodes
            for sub_node_id, sub_node in node.sub_nodes.items():
                node_dict["sub_nodes"][sub_node_id] = node_to_dict(sub_node)
            
            return node_dict
        
        return {
            "report_type": "planning_assessment",
            "root_node": node_to_dict(root_node),
            "metadata": self._extract_report_metadata(root_node)
        }
    
    def _extract_report_metadata(self, root_node: ReasoningNode) -> Dict[str, Any]:
        """Extract metadata from the reasoning tree."""
        def count_nodes(node: ReasoningNode) -> int:
            """Count total nodes in tree."""
            count = 1
            for sub_node in node.sub_nodes.values():
                count += count_nodes(sub_node)
            return count
        
        def collect_statuses(node: ReasoningNode) -> List[str]:
            """Collect all node statuses."""
            statuses = [node.status.value if node.status else "UNKNOWN"]
            for sub_node in node.sub_nodes.values():
                statuses.extend(collect_statuses(sub_node))
            return statuses
        
        all_statuses = collect_statuses(root_node)
        
        return {
            "total_nodes": count_nodes(root_node),
            "status_summary": {
                "total": len(all_statuses),
                "completed_success": all_statuses.count("COMPLETED_SUCCESS"),
                "completed_with_clarification": all_statuses.count("COMPLETED_WITH_CLARIFICATION_NEEDED"),
                "failed": all_statuses.count("FAILED"),
                "skipped": all_statuses.count("SKIPPED"),
                "in_progress": all_statuses.count("IN_PROGRESS")
            }
        }
    
    def generate_async_report_response(self, 
                                     root_node: ReasoningNode,
                                     elapsed_time: float,
                                     provenance_logs: List[ProvenanceLog],
                                     processing_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate the final async report response.
        
        Args:
            root_node: Root node of the processed reasoning tree
            elapsed_time: Total processing time in seconds
            provenance_logs: List of provenance logs
            processing_metadata: Metadata about the processing
            
        Returns:
            Complete async report response
        """
        return {
            "status": "success",
            "reasoning_tree": root_node,
            "final_report_text": self.generate_final_report_text(root_node),
            "structured_report": self.generate_structured_report(root_node),
            "report_metadata": {
                **self._extract_report_metadata(root_node),
                "provenance_logs": len(provenance_logs),
                "total_elapsed_seconds": round(elapsed_time, 2),
                **processing_metadata
            }
        }
    
    def generate_sync_report_response(self, 
                                    root_node: ReasoningNode,
                                    elapsed_time: float,
                                    provenance_logs: List[ProvenanceLog]) -> Dict[str, Any]:
        """
        Generate the final sync report response.
        
        Args:
            root_node: Root node of the processed reasoning tree
            elapsed_time: Total processing time in seconds
            provenance_logs: List of provenance logs
            
        Returns:
            Complete sync report response
        """
        return {
            "status": "success",
            "reasoning_tree": root_node,
            "final_report_text": self.generate_final_report_text(root_node),
            "structured_report": self.generate_structured_report(root_node),
            "report_metadata": {
                **self._extract_report_metadata(root_node),
                "provenance_logs": len(provenance_logs),
                "total_elapsed_seconds": round(elapsed_time, 2),
                "parallel_processing": False
            }
        }
    
    def generate_error_response(self, 
                              error: Exception,
                              processing_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate an error response.
        
        Args:
            error: The exception that occurred
            processing_metadata: Optional processing metadata
            
        Returns:
            Error response dictionary
        """
        response = {
            "status": "error",
            "error": str(error),
            "report_metadata": processing_metadata or {}
        }
        
        return response
    
    def export_report_to_file(self, 
                            report_data: Dict[str, Any], 
                            file_path: str, 
                            format_type: str = "json"):
        """
        Export report to file.
        
        Args:
            report_data: Report data to export
            file_path: Path to save the file
            format_type: Format type ('json' or 'text')
        """
        if format_type.lower() == "json":
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, default=str)
        elif format_type.lower() == "text":
            with open(file_path, 'w', encoding='utf-8') as f:
                if "final_report_text" in report_data:
                    f.write(report_data["final_report_text"])
                else:
                    f.write(str(report_data))
        else:
            raise ValueError(f"Unsupported format type: {format_type}")
    
    def clear_cache(self):
        """Clear the report cache."""
        self.report_cache.clear()
