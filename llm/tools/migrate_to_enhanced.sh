#!/bin/bash
# filepath: /home/tim-mayoh/repos/agentic-retrieval/llm/tools/migrate_to_enhanced.sh

# Enhanced LLM Client Migration Script
# This script helps migrate components to use the enhanced LLM client

echo "🚀 Enhanced LLM Client Migration Script"
echo "======================================"

# Check if the enhanced client is enabled
if [ "${USE_ENHANCED_LLM_CLIENT}" != "true" ]; then
    echo "⚠️  Enhanced LLM client is not enabled."
    echo "Please run: export USE_ENHANCED_LLM_CLIENT=true"
    exit 1
fi

# Validate the environment
echo "📋 Validating environment..."
python -c "
import sys
sys.path.append('.')
from llm.validate_enhanced_llm import validate_imports, validate_configuration
imports_ok = validate_imports()
config_ok = validate_configuration()
if not (imports_ok and config_ok):
    print('❌ Validation failed')
    exit(1)
print('✅ Validation passed')
"

if [ $? -ne 0 ]; then
    echo "❌ Environment validation failed. Please check your configuration."
    exit 1
fi

# Run a quick performance test
echo ""
echo "📊 Running performance comparison..."
python -c "
import asyncio
import time
import sys
sys.path.append('.')

async def compare_performance():
    # Standard client
    from llm.llm_client import FallbackLLMClient, GeminiClient, OpenRouterClient
    from config import GEMINI_API_KEY, OPENROUTER_API_KEY
    
    primary = GeminiClient(GEMINI_API_KEY) if GEMINI_API_KEY else None
    fallbacks = [OpenRouterClient(OPENROUTER_API_KEY)] if OPENROUTER_API_KEY else []
    
    if not primary and fallbacks:
        primary = fallbacks.pop(0)
    elif not primary and not fallbacks:
        print('❌ No API keys configured')
        return
        
    standard_client = FallbackLLMClient(primary, fallbacks)
    
    # Enhanced client
    from llm.enhanced_config import create_enhanced_llm_client
    enhanced_client = create_enhanced_llm_client()
    
    # Test prompt
    prompt = 'What is the capital of France? Answer in one word.'
    config = {'temperature': 0.1, 'max_output_tokens': 10}
    model = 'gemini-2.5-flash-preview-05-20'
    
    # Test standard client
    print('Testing standard client...')
    start_time = time.time()
    try:
        std_response = standard_client.generate_content(
            contents=prompt,
            config=config,
            model=model
        )
        std_time = time.time() - start_time
        print(f'✅ Standard client: {std_time:.2f}s - {std_response.provider}')
    except Exception as e:
        std_time = float('inf')
        print(f'❌ Standard client failed: {e}')
    
    # Test enhanced client
    print('Testing enhanced client...')
    start_time = time.time()
    try:
        enh_response = await enhanced_client.generate_content(
            contents=prompt,
            config=config,
            model=model
        )
        enh_time = time.time() - start_time
        print(f'✅ Enhanced client: {enh_time:.2f}s - {enh_response.provider}')
    except Exception as e:
        enh_time = float('inf')
        print(f'❌ Enhanced client failed: {e}')
    
    # Compare
    if std_time != float('inf') and enh_time != float('inf'):
        if enh_time < std_time:
            print(f'🏆 Enhanced client is {std_time/enh_time:.1f}x faster')
        else:
            print(f'⚠️ Standard client is {enh_time/std_time:.1f}x faster')
    
    # Test caching
    print('\\nTesting caching performance...')
    start_time = time.time()
    try:
        cached_response = await enhanced_client.generate_content(
            contents=prompt,
            config=config,
            model=model
        )
        cache_time = time.time() - start_time
        print(f'✅ Cached response: {cache_time:.2f}s - Cache hit: {cached_response.cache_hit}')
        
        if cached_response.cache_hit:
            print(f'🏆 Caching provides {enh_time/cache_time:.1f}x speed improvement')
    except Exception as e:
        print(f'❌ Cache test failed: {e}')

asyncio.run(compare_performance())
"

# Summary
echo ""
echo "📝 Migration Next Steps:"
echo "1. Modify agents to use the enhanced client"
echo "2. Update the MRM components"
echo "3. Set up monitoring dashboards"
echo ""
echo "To enable enhanced client for all components:"
echo "export USE_ENHANCED_LLM_CLIENT=true"
echo ""
echo "To test in production with a specific component, modify that component to use:"
echo "from llm.enhanced_config import create_enhanced_llm_client"
echo "client = create_enhanced_llm_client()"
echo ""
echo "For additional tools and documentation, see:"
echo "- llm/IMPLEMENTATION_SUMMARY.md"
echo "- llm/test_enhanced_llm.py"
