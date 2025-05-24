"""
Enhanced fallback LLM client with intelligent provider selection,
health monitoring, and comprehensive caching.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .enhanced_llm_client import (
    EnhancedLLMClient, LLMResponse, LLMMetrics, ProviderState, logger
)


@dataclass
class ProviderPerformance:
    """Track provider performance metrics"""
    total_calls: int = 0
    successful_calls: int = 0
    total_response_time: float = 0.0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    @property
    def average_response_time(self) -> float:
        if self.successful_calls == 0:
            return float('inf')
        return self.total_response_time / self.successful_calls
    
    def record_success(self, response_time: float):
        self.total_calls += 1
        self.successful_calls += 1
        self.total_response_time += response_time
        self.last_success_time = datetime.now()
        self.consecutive_successes += 1
        self.consecutive_failures = 0
    
    def record_failure(self):
        self.total_calls += 1
        self.last_failure_time = datetime.now()
        self.consecutive_failures += 1
        self.consecutive_successes = 0


class UniversalLLMCache:
    """Provider-agnostic caching system for LLM responses"""
    
    def __init__(self, cache_impl=None):
        """
        Initialize with existing cache implementation
        
        Args:
            cache_impl: Existing cache implementation (e.g., GeminiResponseCache)
        """
        self.cache_impl = cache_impl
        self._memory_cache: Dict[str, LLMResponse] = {}
        self.cache_stats = {"hits": 0, "misses": 0, "sets": 0}
    
    def _normalize_request_key(self, contents: Union[str, List[Any]], 
                              config: Dict[str, Any], model: str) -> str:
        """Generate normalized cache key across providers"""
        import hashlib
        import json
        
        # Normalize contents
        if isinstance(contents, list):
            content_str = json.dumps(contents, sort_keys=True, default=str)
        else:
            content_str = str(contents)
        
        # Normalize config (remove provider-specific keys)
        normalized_config = {}
        for key, value in config.items():
            if key not in ["thinkingConfig"]:  # Skip Gemini-specific configs
                normalized_config[key] = value
        
        # Create combined key
        combined = f"{content_str}|{json.dumps(normalized_config, sort_keys=True)}|{model}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, contents: Union[str, List[Any]], config: Dict[str, Any], 
            model: str) -> Optional[LLMResponse]:
        """Get cached response if available"""
        cache_key = self._normalize_request_key(contents, config, model)
        
        # Check memory cache first
        if cache_key in self._memory_cache:
            response = self._memory_cache[cache_key]
            response.cache_hit = True
            self.cache_stats["hits"] += 1
            logger.debug(f"Cache HIT (memory) for key {cache_key[:16]}...")
            return response
        
        # Check persistent cache if available
        if self.cache_impl and hasattr(self.cache_impl, 'get_cached_response'):
            try:
                cached_response = self.cache_impl.get_cached_response(contents, config, model)
                if cached_response:
                    # Convert to LLMResponse if needed
                    if isinstance(cached_response, str):
                        response = LLMResponse(
                            text=cached_response,
                            model_used=model,
                            provider="cache",
                            cache_hit=True
                        )
                    else:
                        response = cached_response
                        response.cache_hit = True
                    
                    # Store in memory cache for faster future access
                    self._memory_cache[cache_key] = response
                    self.cache_stats["hits"] += 1
                    logger.debug(f"Cache HIT (persistent) for key {cache_key[:16]}...")
                    return response
            except Exception as e:
                logger.warning(f"Error accessing persistent cache: {e}")
        
        self.cache_stats["misses"] += 1
        logger.debug(f"Cache MISS for key {cache_key[:16]}...")
        return None
    
    def set(self, contents: Union[str, List[Any]], config: Dict[str, Any], 
            model: str, response: LLMResponse):
        """Cache response"""
        cache_key = self._normalize_request_key(contents, config, model)
        
        # Store in memory cache
        self._memory_cache[cache_key] = response
        
        # Store in persistent cache if available
        if self.cache_impl and hasattr(self.cache_impl, 'cache_response'):
            try:
                self.cache_impl.cache_response(contents, config, model, response.text)
            except Exception as e:
                logger.warning(f"Error storing in persistent cache: {e}")
        
        self.cache_stats["sets"] += 1
        logger.debug(f"Cached response for key {cache_key[:16]}...")
    
    def clear_memory_cache(self):
        """Clear in-memory cache"""
        self._memory_cache.clear()
        logger.info("Memory cache cleared")
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_stats["hits"] + self.cache_stats["misses"]
        if total == 0:
            return 0.0
        return self.cache_stats["hits"] / total


class EnhancedFallbackLLMClient:
    """Enhanced LLM client with intelligent fallback and monitoring"""
    
    def __init__(self, providers: List[EnhancedLLMClient], cache_impl=None):
        """
        Initialize fallback client
        
        Args:
            providers: List of LLM provider clients (ordered by preference)
            cache_impl: Optional cache implementation
        """
        if not providers:
            raise ValueError("At least one provider must be specified")
        
        self.providers = providers
        self.provider_performance: Dict[str, ProviderPerformance] = {
            provider.provider_name: ProviderPerformance() 
            for provider in providers
        }
        
        self.cache = UniversalLLMCache(cache_impl)
        self.global_metrics = LLMMetrics()
        
        # Provider selection strategy
        self.selection_strategy = "health_aware"  # or "round_robin", "fastest"
        self._current_provider_index = 0
        
        logger.info(f"Enhanced fallback client initialized with {len(providers)} providers: "
                   f"{[p.provider_name for p in providers]}")
    
    def _select_best_provider(self) -> EnhancedLLMClient:
        """Select the best available provider based on current strategy"""
        available_providers = [
            p for p in self.providers 
            if p.circuit_breaker.can_attempt_call() and p.is_available()
        ]
        
        if not available_providers:
            # Try to reset circuit breakers and check again
            logger.warning("No providers available, attempting recovery...")
            for provider in self.providers:
                if provider.circuit_breaker.state == ProviderState.FAILED:
                    provider.circuit_breaker.state = ProviderState.RECOVERING
            
            available_providers = [p for p in self.providers if p.is_available()]
            
            if not available_providers:
                raise Exception("No LLM providers are currently available")
        
        if self.selection_strategy == "health_aware":
            # Select provider with highest health score
            return max(available_providers, key=lambda p: p.health_score)
        
        elif self.selection_strategy == "fastest":
            # Select provider with best average response time
            def get_avg_time(provider):
                perf = self.provider_performance[provider.provider_name]
                return perf.average_response_time
            
            return min(available_providers, key=get_avg_time)
        
        elif self.selection_strategy == "round_robin":
            # Round-robin through available providers
            while True:
                provider = self.providers[self._current_provider_index]
                self._current_provider_index = (self._current_provider_index + 1) % len(self.providers)
                
                if provider in available_providers:
                    return provider
        
        else:
            # Default: return first available provider
            return available_providers[0]
    
    async def generate_content(self, contents: Union[str, List[Any]], 
                             config: Dict[str, Any], model: str) -> LLMResponse:
        """Generate content with intelligent fallback and caching"""
        request_start_time = time.time()
        
        # Check cache first
        cached_response = self.cache.get(contents, config, model)
        if cached_response:
            logger.info(f"Returning cached response (provider: {cached_response.provider})")
            self.global_metrics.add_call(
                provider="cache",
                success=True,
                response_time=0,
                cache_hit=True
            )
            return cached_response
        
        # Try providers in order of preference
        last_error = None
        attempted_providers = []
        
        while len(attempted_providers) < len(self.providers):
            try:
                # Select best available provider
                provider = self._select_best_provider()
                
                # Skip if already attempted
                if provider.provider_name in attempted_providers:
                    # Remove from available list and try again
                    remaining_providers = [
                        p for p in self.providers 
                        if p.provider_name not in attempted_providers
                    ]
                    if not remaining_providers:
                        break
                    provider = remaining_providers[0]
                
                attempted_providers.append(provider.provider_name)
                
                logger.info(f"Attempting LLM call with {provider.provider_name}")
                
                # Make the request
                response = await provider.generate_content(contents, config, model)
                
                # Record success
                total_time = (time.time() - request_start_time) * 1000
                self.provider_performance[provider.provider_name].record_success(total_time)
                
                self.global_metrics.add_call(
                    provider=provider.provider_name,
                    success=True,
                    response_time=total_time,
                    prompt_tokens=response.prompt_tokens or 0,
                    completion_tokens=response.completion_tokens or 0,
                    cost=response.estimated_cost_usd or 0.0,
                    cache_hit=False
                )
                
                # Cache the successful response
                self.cache.set(contents, config, model, response)
                
                logger.info(f"Successfully generated content using {provider.provider_name} "
                           f"in {total_time:.0f}ms")
                
                return response
                
            except Exception as e:
                last_error = e
                total_time = (time.time() - request_start_time) * 1000
                
                # Record failure
                if attempted_providers:
                    provider_name = attempted_providers[-1]
                    self.provider_performance[provider_name].record_failure()
                    
                    self.global_metrics.add_call(
                        provider=provider_name,
                        success=False,
                        response_time=total_time
                    )
                
                logger.warning(f"Provider {attempted_providers[-1] if attempted_providers else 'unknown'} "
                              f"failed: {e}")
                
                # Continue to next provider
                continue
        
        # All providers failed
        total_time = (time.time() - request_start_time) * 1000
        logger.error(f"All {len(attempted_providers)} providers failed after {total_time:.0f}ms")
        
        raise Exception(f"All LLM providers failed. Last error: {last_error}")
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report"""
        provider_stats = {}
        
        for provider in self.providers:
            perf = self.provider_performance[provider.provider_name]
            provider_stats[provider.provider_name] = {
                "state": provider.circuit_breaker.state.value,
                "health_score": provider.health_score,
                "total_calls": perf.total_calls,
                "success_rate": perf.success_rate,
                "avg_response_time": perf.average_response_time,
                "consecutive_failures": perf.consecutive_failures,
                "consecutive_successes": perf.consecutive_successes,
                "last_success": perf.last_success_time.isoformat() if perf.last_success_time else None,
                "last_failure": perf.last_failure_time.isoformat() if perf.last_failure_time else None,
                "is_available": provider.is_available()
            }
        
        return {
            "global_metrics": {
                "total_calls": self.global_metrics.total_calls,
                "success_rate": self.global_metrics.success_rate,
                "avg_response_time": self.global_metrics.average_response_time,
                "total_cost_usd": self.global_metrics.total_cost_usd,
                "total_tokens": self.global_metrics.total_prompt_tokens + self.global_metrics.total_completion_tokens
            },
            "cache_stats": {
                "hit_rate": self.cache.hit_rate,
                **self.cache.cache_stats
            },
            "providers": provider_stats,
            "current_strategy": self.selection_strategy
        }
    
    def reset_all_providers(self):
        """Reset all provider states and metrics"""
        for provider in self.providers:
            provider.circuit_breaker.failure_count = 0
            provider.circuit_breaker.state = ProviderState.HEALTHY
            provider.circuit_breaker.consecutive_successes = 0
            provider.reset_availability_cache()
        
        self.provider_performance = {
            provider.provider_name: ProviderPerformance() 
            for provider in self.providers
        }
        
        logger.info("All providers reset")
    
    def set_selection_strategy(self, strategy: str):
        """Set provider selection strategy"""
        valid_strategies = ["health_aware", "fastest", "round_robin"]
        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy. Must be one of: {valid_strategies}")
        
        self.selection_strategy = strategy
        logger.info(f"Provider selection strategy set to: {strategy}")
    
    @property
    def provider_name(self) -> str:
        """Return description of fallback client"""
        provider_names = [p.provider_name for p in self.providers]
        return f"fallback({', '.join(provider_names)})"
