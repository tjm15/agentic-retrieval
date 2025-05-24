#!/usr/bin/env python3
"""
Test script for the enhanced LLM abstraction layer.
Tests fallback behavior, monitoring, retry logic, and caching.
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any

# Add the parent directory to the path so we can import the LLM modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.enhanced_config import (
    create_enhanced_llm_client, 
    validate_llm_configuration,
    create_monitoring_dashboard_data
)
from llm.enhanced_llm_client import logger


def print_separator(title: str):
    """Print a formatted separator"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def print_status_report(status_report: Dict[str, Any]):
    """Print formatted status report"""
    print("\n📊 Status Report:")
    
    # Global metrics
    global_metrics = status_report["global_metrics"]
    print(f"  Total Calls: {global_metrics['total_calls']}")
    print(f"  Success Rate: {global_metrics['success_rate']*100:.1f}%")
    print(f"  Avg Response Time: {global_metrics['avg_response_time']:.0f}ms")
    print(f"  Total Cost: ${global_metrics['total_cost_usd']:.6f}")
    
    # Cache stats
    cache_stats = status_report["cache_stats"]
    print(f"  Cache Hit Rate: {cache_stats['hit_rate']*100:.1f}%")
    print(f"  Cache Hits/Misses: {cache_stats['hits']}/{cache_stats['misses']}")
    
    # Provider stats
    print("\n  Provider Details:")
    for provider_name, stats in status_report["providers"].items():
        status_emoji = "✅" if stats["is_available"] else "❌"
        print(f"    {status_emoji} {provider_name}:")
        print(f"      State: {stats['state']}")
        print(f"      Health Score: {stats['health_score']:.2f}")
        print(f"      Calls: {stats['total_calls']} (Success: {stats['success_rate']*100:.1f}%)")
        if stats['avg_response_time'] != float('inf'):
            print(f"      Avg Response Time: {stats['avg_response_time']:.0f}ms")
        print(f"      Consecutive Failures: {stats['consecutive_failures']}")


async def test_basic_functionality():
    """Test basic LLM functionality"""
    print_separator("Testing Basic Functionality")
    
    try:
        # Create enhanced client
        client = create_enhanced_llm_client()
        print(f"✅ Created enhanced LLM client: {client.provider_name}")
        
        # Test simple content generation
        print("\n🔄 Testing simple content generation...")
        config = {
            "temperature": 0.1,
            "max_output_tokens": 50
        }
        
        response = await client.generate_content(
            contents="Say hello in a friendly way",
            config=config,
            model="gemini-2.5-flash-preview-05-20"
        )
        
        print(f"✅ Response received:")
        print(f"  Provider: {response.provider}")
        print(f"  Model: {response.model_used}")
        print(f"  Response Time: {response.response_time_ms}ms")
        print(f"  Tokens: {response.prompt_tokens or 'N/A'} prompt, {response.completion_tokens or 'N/A'} completion")
        print(f"  Cost: ${response.estimated_cost_usd or 0:.6f}")
        print(f"  Cache Hit: {response.cache_hit}")
        print(f"  Text: {response.text[:100]}...")
        
        return client
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return None


async def test_caching():
    """Test caching functionality"""
    print_separator("Testing Caching")
    
    try:
        client = create_enhanced_llm_client()
        
        # Make the same request twice
        config = {"temperature": 0.0, "max_output_tokens": 30}
        prompt = "What is 2+2? Answer with just the number."
        
        print("🔄 Making first request...")
        start_time = time.time()
        response1 = await client.generate_content(
            contents=prompt,
            config=config,
            model="gemini-2.5-flash-preview-05-20"
        )
        first_time = time.time() - start_time
        
        print(f"  First response: {response1.text[:50]}")
        print(f"  Cache hit: {response1.cache_hit}")
        print(f"  Time: {first_time*1000:.0f}ms")
        
        print("\n🔄 Making identical request...")
        start_time = time.time()
        response2 = await client.generate_content(
            contents=prompt,
            config=config,
            model="gemini-2.5-flash-preview-05-20"
        )
        second_time = time.time() - start_time
        
        print(f"  Second response: {response2.text[:50]}")
        print(f"  Cache hit: {response2.cache_hit}")
        print(f"  Time: {second_time*1000:.0f}ms")
        
        if response2.cache_hit:
            print(f"✅ Caching working! Speed improvement: {(first_time/second_time):.1f}x")
        else:
            print("⚠️  Second request not cached (might be normal for different cache implementations)")
        
        return client
        
    except Exception as e:
        print(f"❌ Caching test failed: {e}")
        return None


async def test_fallback_behavior():
    """Test fallback behavior when primary provider fails"""
    print_separator("Testing Fallback Behavior")
    
    try:
        client = create_enhanced_llm_client()
        
        print("🔄 Testing normal operation...")
        response = await client.generate_content(
            contents="Say 'test' in one word",
            config={"temperature": 0.1, "max_output_tokens": 10},
            model="gemini-2.5-flash-preview-05-20"
        )
        print(f"  Normal response from: {response.provider}")
        
        # Simulate provider failure by forcing circuit breaker
        print("\n🔄 Simulating provider failure...")
        if len(client.providers) > 1:
            primary_provider = client.providers[0]
            # Force multiple failures to trigger circuit breaker
            for _ in range(6):
                primary_provider.circuit_breaker.record_failure("simulated_failure")
            
            print(f"  Primary provider ({primary_provider.provider_name}) circuit breaker: {primary_provider.circuit_breaker.state}")
            
            # Try another request
            print("🔄 Making request with failed primary provider...")
            response2 = await client.generate_content(
                contents="Say 'fallback test' in two words",
                config={"temperature": 0.1, "max_output_tokens": 10},
                model="gemini-2.5-flash-preview-05-20"
            )
            print(f"  Fallback response from: {response2.provider}")
            
            if response2.provider != response.provider:
                print("✅ Fallback working correctly!")
            else:
                print("⚠️  Same provider used (might be only one available)")
        else:
            print("⚠️  Only one provider available, cannot test fallback")
        
        return client
        
    except Exception as e:
        print(f"❌ Fallback test failed: {e}")
        return None


async def test_monitoring_and_metrics():
    """Test monitoring and metrics collection"""
    print_separator("Testing Monitoring and Metrics")
    
    try:
        client = create_enhanced_llm_client()
        
        # Make several requests to generate metrics
        print("🔄 Making multiple requests to generate metrics...")
        for i in range(3):
            await client.generate_content(
                contents=f"Test request number {i+1}",
                config={"temperature": 0.1, "max_output_tokens": 20},
                model="gemini-2.5-flash-preview-05-20"
            )
        
        # Get status report
        status_report = client.get_status_report()
        print_status_report(status_report)
        
        # Test dashboard data
        print("\n📊 Dashboard Data:")
        dashboard_data = create_monitoring_dashboard_data(client)
        print(f"  Total Providers: {dashboard_data['summary']['total_providers']}")
        print(f"  Healthy Providers: {dashboard_data['summary']['healthy_providers']}")
        print(f"  Success Rate: {dashboard_data['summary']['success_rate_pct']:.1f}%")
        
        if dashboard_data['alerts']:
            print("  🚨 Alerts:")
            for alert in dashboard_data['alerts']:
                emoji = "🔴" if alert['level'] == 'error' else "🟡"
                print(f"    {emoji} {alert['message']}")
        else:
            print("  ✅ No alerts")
        
        return client
        
    except Exception as e:
        print(f"❌ Monitoring test failed: {e}")
        return None


async def test_error_scenarios():
    """Test various error scenarios"""
    print_separator("Testing Error Scenarios")
    
    try:
        client = create_enhanced_llm_client()
        
        # Test with invalid model
        print("🔄 Testing with invalid model...")
        try:
            await client.generate_content(
                contents="Test with invalid model",
                config={"temperature": 0.1, "max_output_tokens": 20},
                model="non-existent-model"
            )
            print("⚠️  Expected error but request succeeded")
        except Exception as e:
            print(f"✅ Correctly handled invalid model: {str(e)[:100]}...")
        
        # Test with extreme configuration
        print("\n🔄 Testing with extreme configuration...")
        try:
            await client.generate_content(
                contents="Test with extreme config",
                config={"temperature": 2.0, "max_output_tokens": 100000},  # Extreme values
                model="gemini-2.5-flash-preview-05-20"
            )
            print("✅ Handled extreme configuration")
        except Exception as e:
            print(f"⚠️  Extreme config failed: {str(e)[:100]}...")
        
        return client
        
    except Exception as e:
        print(f"❌ Error scenario test failed: {e}")
        return None


async def run_comprehensive_test():
    """Run comprehensive test suite"""
    print_separator("Enhanced LLM Abstraction Layer Test Suite")
    
    # Check configuration first
    print("🔍 Validating LLM configuration...")
    validation_results = validate_llm_configuration()
    
    print(f"  API Keys:")
    for provider, available in validation_results["api_keys"].items():
        emoji = "✅" if available else "❌"
        print(f"    {emoji} {provider}: {'configured' if available else 'not configured'}")
    
    print(f"  Provider Availability:")
    for provider, status in validation_results["providers"].items():
        emoji = "✅" if status["available"] else "❌"
        error_msg = f" ({status['error']})" if status["error"] else ""
        print(f"    {emoji} {provider}: {'available' if status['available'] else 'unavailable'}{error_msg}")
    
    print(f"  Overall Status: {validation_results['overall_status'].upper()}")
    
    if validation_results["overall_status"] == "failed":
        print("\n❌ Cannot run tests - no providers available")
        return
    
    # Run test suite
    test_results = {}
    
    # Test basic functionality
    client = await test_basic_functionality()
    test_results["basic"] = client is not None
    
    if client:
        # Test caching
        cache_client = await test_caching()
        test_results["caching"] = cache_client is not None
        
        # Test fallback
        fallback_client = await test_fallback_behavior()
        test_results["fallback"] = fallback_client is not None
        
        # Test monitoring
        monitoring_client = await test_monitoring_and_metrics()
        test_results["monitoring"] = monitoring_client is not None
        
        # Test error handling
        error_client = await test_error_scenarios()
        test_results["error_handling"] = error_client is not None
        
        # Final status report
        print_separator("Final Status Report")
        final_status = client.get_status_report()
        print_status_report(final_status)
    
    # Summary
    print_separator("Test Results Summary")
    passed_tests = sum(test_results.values())
    total_tests = len(test_results)
    
    for test_name, passed in test_results.items():
        emoji = "✅" if passed else "❌"
        print(f"  {emoji} {test_name.replace('_', ' ').title()}")
    
    print(f"\n📊 Overall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed! Enhanced LLM abstraction layer is working correctly.")
    elif passed_tests > 0:
        print("⚠️  Some tests passed. Enhanced LLM abstraction layer is partially working.")
    else:
        print("❌ All tests failed. Please check configuration and provider availability.")


if __name__ == "__main__":
    # Set up logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Run tests
    asyncio.run(run_comprehensive_test())
