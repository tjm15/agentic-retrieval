# Enhanced LLM Client Migration Guide

This guide provides step-by-step instructions for migrating from the standard LLM client to the enhanced implementation.

## Migration Phases

### Phase 1: Testing (Current)
- Test the enhanced client in a development environment
- Validate functionality with specific test cases
- Compare performance metrics

### Phase 2: Gradual Adoption (Recommended)
- Enable for specific components to assess impact
- Monitor performance and reliability improvements
- Gradually expand to more components

### Phase 3: Full Migration
- Enable for all components
- Remove legacy implementation
- Implement full monitoring and alerting

## Prerequisites

1. Ensure you have API keys configured:
   ```bash
   export GEMINI_API_KEY=your_key
   export OPENROUTER_API_KEY=your_key  # Optional but recommended
   ```

2. Validate the environment:
   ```bash
   python llm/validate_enhanced_llm.py
   ```

## Migration Options

### Option 1: Global Enablement (Easiest)

To enable the enhanced client for all components without code changes:

```bash
export USE_ENHANCED_LLM_CLIENT=true
```

This approach uses the compatibility layer in `config.py` which automatically returns the enhanced client when the environment variable is set.

### Option 2: Component-Specific Migration (Recommended)

For more controlled migration, update specific components:

1. **Original code**:
   ```python
   from config import create_llm_client
   client = create_llm_client()
   ```

2. **Enhanced code**:
   ```python
   from llm.enhanced_config import create_enhanced_llm_client
   client = create_enhanced_llm_client()
   
   # Make requests using async
   response = await client.generate_content(
       contents="Your prompt",
       config={"temperature": 0.1, "max_output_tokens": 100},
       model="gemini-2.5-flash-preview-05-20"
   )
   ```

3. **When using in async functions**:
   ```python
   async def your_async_function():
       response = await client.generate_content(...)
   ```

4. **When using in synchronous code**:
   ```python
   import asyncio
   
   def your_sync_function():
       response = asyncio.run(client.generate_content(...))
   ```

### Option 3: Mixed Approach (Advanced)

Conditional usage based on requirements:

```python
import os

if os.getenv("USE_ENHANCED_LLM_CLIENT", "false").lower() == "true":
    from llm.enhanced_config import create_enhanced_llm_client
    client = create_enhanced_llm_client()
    async_client = True
else:
    from config import create_llm_client
    client = create_llm_client()
    async_client = False

def generate_content(prompt, config, model):
    if async_client:
        import asyncio
        return asyncio.run(client.generate_content(
            contents=prompt, 
            config=config, 
            model=model
        ))
    else:
        return client.generate_content(
            contents=prompt, 
            config=config, 
            model=model
        )
```

## Components to Migrate

Priority order for migration:

1. **Base Agent Classes** (`agents/base_agent.py`)
   - Frequently used and benefits from improved caching

2. **Intent Definer** (`mrm/intent_definer.py`)
   - Complex LLM operations benefit from retry logic

3. **Specialized Agents** (`agents/policy_analysis_agent.py`, `agents/visual_heritage_agent.py`)
   - Can leverage improved provider health monitoring

4. **Node Processor** (`mrm/node_processor.py`)
   - Benefits from universal caching

## Monitoring

After migration, set up monitoring:

```bash
# Start the monitoring dashboard
python llm/tools/monitor_llm.py
```

This provides real-time metrics on:
- Provider health status
- Success rates and response times
- Cache performance
- Cost tracking
- Alerts for potential issues

## Rollback Plan

If issues occur, you can easily roll back:

```bash
# Disable enhanced client
unset USE_ENHANCED_LLM_CLIENT

# For component-specific migrations, revert code changes:
# From: from llm.enhanced_config import create_enhanced_llm_client
# To:   from config import create_llm_client
```

## Testing

Run the comprehensive test suite:

```bash
python llm/test_enhanced_llm.py
```

## Performance Comparison

Compare performance:

```bash
bash llm/tools/migrate_to_enhanced.sh
```

This script performs side-by-side comparison of:
- Response times
- Success rates
- Caching performance

## Support

For issues or questions:
- Check `llm/IMPLEMENTATION_SUMMARY.md` for design details
- Refer to `llm/llm_analysis_report.md` for background on the implementation
- Review test output in `llm/test_enhanced_llm.py` for common issues
