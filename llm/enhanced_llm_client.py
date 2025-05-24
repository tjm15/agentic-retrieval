"""
Enhanced LLM client implementation with improved error handling,
monitoring, retry logic, and provider management.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Callable
import hashlib
import json

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProviderState(Enum):
    """Provider circuit breaker states"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class LLMMetrics:
    """Comprehensive LLM usage metrics"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    response_times: List[float] = field(default_factory=list)
    provider_usage: Dict[str, int] = field(default_factory=dict)
    error_counts: Dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    
    def add_call(self, provider: str, success: bool, response_time: float,
                 prompt_tokens: int = 0, completion_tokens: int = 0,
                 cost: float = 0.0, cache_hit: bool = False):
        """Record a new LLM call"""
        self.total_calls += 1
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
            
        self.response_times.append(response_time)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd += cost
        
        self.provider_usage[provider] = self.provider_usage.get(provider, 0) + 1
        
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def add_error(self, error_type: str):
        """Record an error"""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    @property
    def average_response_time(self) -> float:
        """Calculate average response time"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total_cache_attempts = self.cache_hits + self.cache_misses
        if total_cache_attempts == 0:
            return 0.0
        return self.cache_hits / total_cache_attempts


@dataclass
class LLMResponse:
    """Enhanced standardized response format for all LLM providers"""
    text: str
    model_used: str
    provider: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    response_time_ms: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    cache_hit: bool = False
    raw_response: Optional[Any] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ProviderCircuitBreaker:
    """Circuit breaker pattern for provider health management"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300,
                 degraded_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.degraded_threshold = degraded_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = ProviderState.HEALTHY
        self.consecutive_successes = 0
    
    def record_success(self):
        """Record a successful call"""
        self.consecutive_successes += 1
        
        if self.state == ProviderState.RECOVERING and self.consecutive_successes >= 3:
            self.state = ProviderState.HEALTHY
            self.failure_count = 0
            logger.info(f"Provider recovered to HEALTHY state")
        elif self.state == ProviderState.DEGRADED and self.consecutive_successes >= 2:
            self.state = ProviderState.HEALTHY
            self.failure_count = 0
            logger.info(f"Provider recovered from DEGRADED to HEALTHY state")
    
    def record_failure(self, error_type: str = "unknown"):
        """Record a failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_successes = 0
        
        if self.failure_count >= self.failure_threshold:
            self.state = ProviderState.FAILED
            logger.error(f"Provider circuit breaker OPENED - too many failures")
        elif self.failure_count >= self.degraded_threshold:
            self.state = ProviderState.DEGRADED
            logger.warning(f"Provider marked as DEGRADED - {self.failure_count} failures")
    
    def can_attempt_call(self) -> bool:
        """Check if calls should be attempted to this provider"""
        if self.state == ProviderState.HEALTHY:
            return True
        elif self.state == ProviderState.DEGRADED:
            return True  # Still allow calls but with lower priority
        elif self.state == ProviderState.FAILED:
            # Check if recovery timeout has passed
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = ProviderState.RECOVERING
                logger.info(f"Provider entering RECOVERING state")
                return True
            return False
        elif self.state == ProviderState.RECOVERING:
            return True
        
        return False
    
    @property
    def priority_score(self) -> float:
        """Get priority score for provider selection (higher = better)"""
        if self.state == ProviderState.HEALTHY:
            return 1.0
        elif self.state == ProviderState.DEGRADED:
            return 0.5
        elif self.state == ProviderState.RECOVERING:
            return 0.3
        else:  # FAILED
            return 0.0


class RetryConfig:
    """Configuration for retry logic"""
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 60.0, exponential_base: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)


class EnhancedLLMClient(ABC):
    """Enhanced abstract base class for LLM clients with monitoring"""
    
    def __init__(self, provider_name: str):
        self._provider_name = provider_name
        self.circuit_breaker = ProviderCircuitBreaker()
        self.retry_config = RetryConfig()
        self.metrics = LLMMetrics()
        self._request_counter = 0
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        self._request_counter += 1
        timestamp = int(time.time() * 1000)
        return f"{self._provider_name}_{timestamp}_{self._request_counter}"
    
    @abstractmethod
    async def _execute_request(self, contents: Union[str, List[Any]], 
                             config: Dict[str, Any], model: str,
                             request_id: str) -> LLMResponse:
        """Execute the actual LLM request (to be implemented by providers)"""
        pass
    
    async def generate_content(self, contents: Union[str, List[Any]], 
                             config: Dict[str, Any], model: str) -> LLMResponse:
        """Generate content with retry logic and monitoring"""
        request_id = self._generate_request_id()
        start_time = time.time()
        
        logger.info(f"Starting LLM request {request_id} to {self._provider_name}")
        
        if not self.circuit_breaker.can_attempt_call():
            raise Exception(f"Provider {self._provider_name} is not available (circuit breaker)")
        
        last_error = None
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                response = await self._execute_request(contents, config, model, request_id)
                
                # Record success
                response_time = (time.time() - start_time) * 1000
                response.response_time_ms = int(response_time)
                response.request_id = request_id
                
                self.circuit_breaker.record_success()
                self.metrics.add_call(
                    provider=self._provider_name,
                    success=True,
                    response_time=response_time,
                    prompt_tokens=response.prompt_tokens or 0,
                    completion_tokens=response.completion_tokens or 0,
                    cost=response.estimated_cost_usd or 0.0,
                    cache_hit=response.cache_hit
                )
                
                logger.info(f"LLM request {request_id} completed successfully in {response_time:.0f}ms")
                return response
                
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                
                # Check if this is a retryable error
                if self._is_retryable_error(e) and attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(f"LLM request {request_id} failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Final failure
                    response_time = (time.time() - start_time) * 1000
                    self.circuit_breaker.record_failure(error_type)
                    self.metrics.add_call(
                        provider=self._provider_name,
                        success=False,
                        response_time=response_time
                    )
                    self.metrics.add_error(error_type)
                    
                    logger.error(f"LLM request {request_id} failed permanently: {e}")
                    raise e
        
        # This part should ideally not be reached if the loop logic is correct
        if last_error is None:
            # This case implies the loop completed without any error being caught and without returning a response,
            # which should be impossible.
            logger.error(f"LLM request {request_id} to {self._provider_name} ended in an unexpected state without a specific error.")
            raise RuntimeError(f"LLM request {request_id} to {self._provider_name} failed without a specific exception after all retries.")
        raise last_error
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable"""
        error_str = str(error).lower()
        retryable_patterns = [
            "timeout", "connection", "network", "temporary", "503", "502", "500"
        ]
        non_retryable_patterns = [
            "quota", "limit", "unauthorized", "invalid", "400", "401", "403"
        ]
        
        # Check non-retryable first
        for pattern in non_retryable_patterns:
            if pattern in error_str:
                return False
        
        # Check retryable
        for pattern in retryable_patterns:
            if pattern in error_str:
                return True
        
        # Default to retryable for unknown errors
        return True
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is available"""
        pass
    
    @property
    def provider_name(self) -> str:
        """Name of the LLM provider"""
        return self._provider_name
    
    @property
    def health_score(self) -> float:
        """Get overall health score (0.0 to 1.0)"""
        circuit_score = self.circuit_breaker.priority_score
        success_rate = self.metrics.success_rate
        
        # Weight recent performance more heavily
        return (circuit_score * 0.6) + (success_rate * 0.4)

    def reset_availability_cache(self):
        """
        Resets the provider's circuit breaker to a healthy state.
        Providers can override for more specific cache resetting if needed.
        """
        logger.info(f"Resetting availability for provider {self._provider_name} (circuit breaker state to HEALTHY)")
        self.circuit_breaker.failure_count = 0
        self.circuit_breaker.state = ProviderState.HEALTHY
        self.circuit_breaker.consecutive_successes = 0


# Cost estimation utilities
PROVIDER_COSTS = {
    "gemini": {
        "gemini-2.5-flash-preview-05-20": {"prompt": 0.075e-6, "completion": 0.30e-6},
        "gemini-1.5-pro-latest": {"prompt": 1.25e-6, "completion": 5.0e-6},
    },
    "openrouter": {
        "google/gemini-2.0-flash-exp:free": {"prompt": 0.0, "completion": 0.0},
        "google/gemini-pro-1.5": {"prompt": 1.25e-6, "completion": 5.0e-6},
    }
}

def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost for API call"""
    if provider not in PROVIDER_COSTS or model not in PROVIDER_COSTS[provider]:
        return 0.0
    
    costs = PROVIDER_COSTS[provider][model]
    return (prompt_tokens * costs["prompt"]) + (completion_tokens * costs["completion"])
