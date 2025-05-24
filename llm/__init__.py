"""
Enhanced LLM abstraction layer module.

This module provides an improved LLM client abstraction with:
- Intelligent provider fallback
- Circuit breaker pattern for provider health management
- Comprehensive monitoring and metrics
- Universal caching across providers
- Structured logging and error handling
- Retry logic with exponential backoff

Usage:
    from llm.enhanced_config import create_enhanced_llm_client
    
    client = create_enhanced_llm_client()
    response = await client.generate_content(
        contents="Your prompt here",
        config={"temperature": 0.1, "max_output_tokens": 100},
        model="gemini-2.5-flash-preview-05-20"
    )
"""

from .enhanced_llm_client import (
    LLMResponse,
    LLMMetrics,
    ProviderState,
    EnhancedLLMClient
)

from .enhanced_providers import (
    EnhancedGeminiClient,
    EnhancedOpenRouterClient
)

from .enhanced_fallback_client import (
    EnhancedFallbackLLMClient,
    UniversalLLMCache
)

from .enhanced_config import (
    create_enhanced_llm_client,
    validate_llm_configuration,
    create_monitoring_dashboard_data,
    create_llm_client  # Compatibility function
)

__all__ = [
    'LLMResponse',
    'LLMMetrics', 
    'ProviderState',
    'EnhancedLLMClient',
    'EnhancedGeminiClient',
    'EnhancedOpenRouterClient',
    'EnhancedFallbackLLMClient',
    'UniversalLLMCache',
    'create_enhanced_llm_client',
    'validate_llm_configuration',
    'create_monitoring_dashboard_data',
    'create_llm_client'
]
