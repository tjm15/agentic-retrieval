# mrm/parallel_processor.py
"""
Parallel Processor for MRM Orchestrator
Handles async/parallel processing logic
"""

import asyncio
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Callable
from core_types import ReasoningNode, IntentStatus


class ParallelProcessor:
    """Handles parallel and async processing of reasoning nodes."""
    
    def __init__(self, parallel_async_llm_mode: bool = False, max_concurrent_llm_calls: int = 5):
        self.parallel_async_llm_mode = parallel_async_llm_mode
        self.max_concurrent_llm_calls = max_concurrent_llm_calls
        self._llm_semaphore = asyncio.Semaphore(max_concurrent_llm_calls) if parallel_async_llm_mode else None
        
        print(f"INFO: Parallel Async LLM Mode: {'ENABLED' if self.parallel_async_llm_mode else 'DISABLED'}")
        if self.parallel_async_llm_mode:
            print(f"INFO: Max Concurrent LLM Calls: {self.max_concurrent_llm_calls}")
    
    async def async_llm_call_with_semaphore(self, llm_callable: Callable, *args, **kwargs):
        """
        Execute an LLM call with semaphore control for parallel async mode.
        
        Args:
            llm_callable: The callable that makes the LLM call
            *args, **kwargs: Arguments to pass to the callable
            
        Returns:
            The result of the LLM call
        """
        if not self.parallel_async_llm_mode or not self._llm_semaphore:
            # Run synchronously if parallel async mode is disabled
            return llm_callable(*args, **kwargs)
        
        # Use semaphore to limit concurrent LLM calls
        async with self._llm_semaphore:
            # Run the LLM call in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                # Create a wrapper function that captures kwargs
                def wrapper():
                    return llm_callable(*args, **kwargs)
                
                return await loop.run_in_executor(executor, wrapper)
    
    async def process_node_async(self, 
                                node: ReasoningNode,
                                process_func: Callable,
                                *args, **kwargs):
        """
        Async version of node processing with LLM calls wrapped in asyncio.
        
        Args:
            node: The reasoning node to process
            process_func: The function to call for processing
            *args, **kwargs: Arguments to pass to the processing function
        """
        if self.parallel_async_llm_mode:
            # Use async LLM processing with semaphore control
            await self.async_llm_call_with_semaphore(process_func, node, *args, **kwargs)
        else:
            # Run synchronously in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, process_func, node, *args, **kwargs)
    
    async def process_nodes_parallel(self, 
                                   nodes: List[ReasoningNode],
                                   process_func: Callable,
                                   max_parallel_nodes: int,
                                   *args, **kwargs):
        """
        Process multiple nodes concurrently with optional parallel async LLM mode.
        
        Args:
            nodes: List of nodes to process
            process_func: Function to call for processing each node
            max_parallel_nodes: Maximum number of nodes to process concurrently
            *args, **kwargs: Arguments to pass to the processing function
        """
        # Process nodes in batches to respect max_parallel_nodes limit
        for i in range(0, len(nodes), max_parallel_nodes):
            batch = nodes[i:i + max_parallel_nodes]
            tasks = []
            
            for node in batch:
                task = self.process_node_async(node, process_func, *args, **kwargs)
                tasks.append(task)
            
            # Wait for all tasks in this batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for exceptions and log them
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    node_id = batch[i].node_id if i < len(batch) else "unknown"
                    print(f"ERROR: Exception processing node {node_id}: {result}")
                    traceback.print_exception(type(result), result, result.__traceback__)
    
    def get_ready_nodes(self, all_nodes: List[ReasoningNode], processed_outputs: Dict[str, Any]) -> List[ReasoningNode]:
        """
        Get nodes that are ready for processing (dependencies met).
        
        Args:
            all_nodes: All nodes in the reasoning graph
            processed_outputs: Dictionary of already processed node outputs
            
        Returns:
            List of nodes ready for processing
        """
        ready_nodes = []
        
        for node in all_nodes:
            # Skip if already processed
            if node.node_id in processed_outputs:
                continue
                
            # Skip if currently in progress or failed
            if node.status in [IntentStatus.IN_PROGRESS, IntentStatus.FAILED]:
                continue
                
            # Check if dependencies are met
            dependencies_met = True
            if node.depends_on_nodes:
                for dep_id in node.depends_on_nodes:
                    if dep_id not in processed_outputs:
                        dependencies_met = False
                        break
                    dep_status = processed_outputs[dep_id].get("status")
                    if dep_status not in [IntentStatus.COMPLETED_SUCCESS.value, 
                                        IntentStatus.COMPLETED_WITH_CLARIFICATION_NEEDED.value]:
                        dependencies_met = False
                        break
            
            if dependencies_met:
                ready_nodes.append(node)
        
        return ready_nodes
    
    async def run_orchestration_loop(self, 
                                   all_nodes_func: Callable,
                                   process_func: Callable,
                                   max_parallel_nodes: int,
                                   max_iterations: int = 20,  # Increased from 10 to 20
                                   **process_kwargs) -> Dict[str, Any]:
        """
        Run the main orchestration loop with parallel processing.
        
        Args:
            all_nodes_func: Function to get all nodes in the graph
            process_func: Function to process individual nodes
            max_parallel_nodes: Maximum number of nodes to process concurrently
            max_iterations: Maximum number of orchestration iterations
            **process_kwargs: Additional keyword arguments for processing
            
        Returns:
            Dictionary containing processed node outputs
        """
        processed_node_outputs = {}
        
        for iteration in range(max_iterations):
            all_nodes = all_nodes_func()
            ready_nodes = self.get_ready_nodes(all_nodes, processed_node_outputs)
            
            if not ready_nodes:
                print(f"INFO: No more ready nodes. Orchestration complete after {iteration + 1} iterations.")
                break
            
            # Limit the number of nodes processed in parallel
            batch_size = min(len(ready_nodes), max_parallel_nodes)
            current_batch = ready_nodes[:batch_size]
            
            print(f"INFO: Processing batch {iteration + 1}: {len(current_batch)} nodes")
            
            # Process the batch
            await self.process_nodes_parallel(
                current_batch,
                process_func,
                max_parallel_nodes,
                processed_node_outputs,
                **process_kwargs
            )
            
            # Update processed outputs for nodes that completed
            for node in current_batch:
                if node.node_id not in processed_node_outputs:
                    processed_node_outputs[node.node_id] = {
                        "status": node.status.value,
                        "node_id": node.node_id,
                        "final_synthesized_text_preview": (
                            node.final_synthesized_text[:200] + "..." 
                            if node.final_synthesized_text and len(node.final_synthesized_text) > 200 
                            else node.final_synthesized_text
                        ),
                        "final_structured_data": node.final_structured_data,
                        "confidence_score": node.confidence_score
                    }
        
        return processed_node_outputs
    
    def update_semaphore_limit(self, new_limit: int):
        """Update the semaphore limit for concurrent LLM calls."""
        if self.parallel_async_llm_mode and new_limit > 0:
            self.max_concurrent_llm_calls = new_limit
            self._llm_semaphore = asyncio.Semaphore(new_limit)
            print(f"INFO: Updated LLM semaphore limit to {new_limit}")
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics."""
        return {
            "parallel_async_llm_mode": self.parallel_async_llm_mode,
            "max_concurrent_llm_calls": self.max_concurrent_llm_calls,
            "semaphore_available": self._llm_semaphore._value if self._llm_semaphore else None
        }
