"""
Enhanced LLM configuration module with improved client factory
and monitoring capabilities.
"""

import os
from typing import Optional

from .enhanced_providers import EnhancedGeminiClient, EnhancedOpenRouterClient
from .enhanced_fallback_client import EnhancedFallbackLLMClient
from .enhanced_llm_client import logger


def create_enhanced_llm_client(cache_impl=None, selection_strategy: str = "health_aware") -> EnhancedFallbackLLMClient:
    """
    Create and return the enhanced LLM client with fallback support
    
    Args:
        cache_impl: Optional cache implementation (e.g., GeminiResponseCache)
        selection_strategy: Provider selection strategy ("health_aware", "fastest", "round_robin")
    
    Returns:
        EnhancedFallbackLLMClient instance
    """
    # Get API keys from environment
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    
    # Create providers in order of preference
    providers = []
    
    if gemini_api_key:
        try:
            gemini_client = EnhancedGeminiClient(gemini_api_key)
            providers.append(gemini_client)
            logger.info("Gemini client configured as primary provider")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
    
    if openrouter_api_key:
        try:
            openrouter_client = EnhancedOpenRouterClient(openrouter_api_key)
            providers.append(openrouter_client)
            logger.info("OpenRouter client configured as fallback provider")
        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter client: {e}")
    
    if not providers:
        raise ValueError(
            "No LLM API keys configured. Please set GEMINI_API_KEY and/or OPENROUTER_API_KEY"
        )
    
    # Create enhanced fallback client
    fallback_client = EnhancedFallbackLLMClient(
        providers=providers,
        cache_impl=cache_impl
    )
    
    # Set selection strategy
    fallback_client.set_selection_strategy(selection_strategy)
    
    logger.info(f"Enhanced LLM client created with {len(providers)} providers, "
               f"strategy: {selection_strategy}")
    
    return fallback_client


def validate_llm_configuration() -> dict:
    """
    Validate LLM configuration and return status report
    
    Returns:
        Dictionary with validation results
    """
    validation_results = {
        "api_keys": {},
        "providers": {},
        "overall_status": "unknown"
    }
    
    # Check API keys
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    validation_results["api_keys"]["gemini"] = bool(gemini_key)
    validation_results["api_keys"]["openrouter"] = bool(openrouter_key)
    
    # Test provider availability
    providers_available = 0
    
    if gemini_key:
        try:
            client = EnhancedGeminiClient(gemini_key)
            is_available = client.is_available()
            validation_results["providers"]["gemini"] = {
                "available": is_available,
                "error": None
            }
            if is_available:
                providers_available += 1
        except Exception as e:
            validation_results["providers"]["gemini"] = {
                "available": False,
                "error": str(e)
            }
    
    if openrouter_key:
        try:
            client = EnhancedOpenRouterClient(openrouter_key)
            is_available = client.is_available()
            validation_results["providers"]["openrouter"] = {
                "available": is_available,
                "error": None
            }
            if is_available:
                providers_available += 1
        except Exception as e:
            validation_results["providers"]["openrouter"] = {
                "available": False,
                "error": str(e)
            }
    
    # Determine overall status
    if providers_available == 0:
        validation_results["overall_status"] = "failed"
    elif providers_available == 1:
        validation_results["overall_status"] = "degraded"
    else:
        validation_results["overall_status"] = "healthy"
    
    return validation_results


def get_llm_cost_estimate(provider: str, model: str, prompt_length: int, 
                         completion_length: int) -> float:
    """
    Estimate cost for LLM API call
    
    Args:
        provider: Provider name ("gemini" or "openrouter")
        model: Model name
        prompt_length: Estimated prompt length in characters
        completion_length: Estimated completion length in characters
    
    Returns:
        Estimated cost in USD
    """
    # Rough estimation: ~4 characters per token
    prompt_tokens = prompt_length // 4
    completion_tokens = completion_length // 4
    
    from .enhanced_llm_client import estimate_cost
    return estimate_cost(provider, model, prompt_tokens, completion_tokens)


def create_monitoring_dashboard_data(fallback_client: EnhancedFallbackLLMClient) -> dict:
    """
    Create data for monitoring dashboard
    
    Args:
        fallback_client: Enhanced fallback client instance
    
    Returns:
        Dictionary with monitoring data
    """
    status_report = fallback_client.get_status_report()
    
    # Calculate additional metrics
    dashboard_data = {
        "summary": {
            "total_providers": len(fallback_client.providers),
            "healthy_providers": sum(1 for p in status_report["providers"].values() 
                                   if p["is_available"]),
            "total_calls": status_report["global_metrics"]["total_calls"],
            "success_rate_pct": status_report["global_metrics"]["success_rate"] * 100,
            "avg_response_time_ms": status_report["global_metrics"]["avg_response_time"],
            "total_cost_usd": status_report["global_metrics"]["total_cost_usd"],
            "cache_hit_rate_pct": status_report["cache_stats"]["hit_rate"] * 100
        },
        "providers": [],
        "alerts": []
    }
    
    # Process provider data
    for provider_name, stats in status_report["providers"].items():
        provider_data = {
            "name": provider_name,
            "status": stats["state"],
            "health_score": stats["health_score"],
            "success_rate_pct": stats["success_rate"] * 100,
            "avg_response_time_ms": stats["avg_response_time"] if stats["avg_response_time"] != float('inf') else None,
            "total_calls": stats["total_calls"],
            "consecutive_failures": stats["consecutive_failures"]
        }
        dashboard_data["providers"].append(provider_data)
        
        # Generate alerts
        if not stats["is_available"]:
            dashboard_data["alerts"].append({
                "level": "error",
                "message": f"Provider {provider_name} is not available",
                "provider": provider_name
            })
        elif stats["success_rate"] < 0.9 and stats["total_calls"] > 5:
            dashboard_data["alerts"].append({
                "level": "warning", 
                "message": f"Provider {provider_name} has low success rate: {stats['success_rate']*100:.1f}%",
                "provider": provider_name
            })
        elif stats["consecutive_failures"] > 2:
            dashboard_data["alerts"].append({
                "level": "warning",
                "message": f"Provider {provider_name} has {stats['consecutive_failures']} consecutive failures",
                "provider": provider_name
            })
    
    return dashboard_data


# Compatibility function for existing code
def create_llm_client():
    """
    Compatibility function that creates the enhanced LLM client
    using the original interface
    """
    try:
        # Try to import existing cache if available
        from cache.gemini_cache import GeminiResponseCache
        from config import CACHE_ENABLED
        
        cache_impl = GeminiResponseCache() if CACHE_ENABLED else None
    except ImportError:
        cache_impl = None
    
    return create_enhanced_llm_client(cache_impl=cache_impl)
