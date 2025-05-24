#!/bin/bash

# Enhanced LLM Client Enablement Script
# This script helps enable and test the enhanced LLM client

echo "🚀 Enhanced LLM Client Enablement Script"
echo "========================================"

# Check current environment
echo "📋 Current Environment Status:"
echo "GEMINI_API_KEY: ${GEMINI_API_KEY:+SET}"
echo "OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:+SET}"
echo "USE_ENHANCED_LLM_CLIENT: ${USE_ENHANCED_LLM_CLIENT:-false}"

echo ""
echo "💡 To enable the enhanced LLM client, run:"
echo "export USE_ENHANCED_LLM_CLIENT=true"

echo ""
echo "🧪 To test the enhanced client, run:"
echo "python llm/test_enhanced_llm.py"

echo ""
echo "📊 To validate configuration, run:"
echo "python llm/validate_enhanced_llm.py"

echo ""
echo "🔄 To run a quick test of basic functionality:"
python -c "
import asyncio
import os
import sys
sys.path.append('.')

async def quick_test():
    try:
        from llm.enhanced_config import create_enhanced_llm_client
        print('✅ Enhanced LLM client imports successfully')
        
        # Test creation
        client = create_enhanced_llm_client()
        print(f'✅ Created enhanced client with {len(client.providers)} providers')
        
        # Test simple generation (if API keys available)
        if os.getenv('GEMINI_API_KEY') or os.getenv('OPENROUTER_API_KEY'):
            response = await client.generate_content(
                contents='Say hello briefly',
                config={'temperature': 0.1, 'max_output_tokens': 10},
                model='gemini-2.5-flash-preview-05-20'
            )
            print(f'✅ Test generation successful: {response.text[:50]}...')
            print(f'📊 Provider: {response.provider}, Cost: \${response.estimated_cost_usd or 0:.6f}')
        else:
            print('⚠️  No API keys configured for full test')
            
    except Exception as e:
        print(f'❌ Test failed: {e}')

asyncio.run(quick_test())
"
