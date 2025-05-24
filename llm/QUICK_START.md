# Enhanced LLM Client Quick-Start Guide

This guide provides quick steps to get started with the enhanced LLM client in the agentic-retrieval project.

## 1. Prerequisites

Ensure you have the necessary API keys:

```bash
# Set your API keys
export GEMINI_API_KEY=your_key_here
export OPENROUTER_API_KEY=your_key_here  # Optional but recommended for fallback
```

## 2. Validation

Verify that the enhanced client is properly configured:

```bash
# Run validation script
python llm/validate_enhanced_llm.py
```

You should see a success message confirming that imports and configuration are valid.

## 3. Enable Enhanced Client

Choose one of these options:

### Option A: Global Enablement (Simplest)

```bash
# Enable for all components
export USE_ENHANCED_LLM_CLIENT=true

# Run your application as usual
python main.py
```

### Option B: Component-Specific (Recommended for Testing)

Modify only the components you want to test with the enhanced client:

```python
# Change this in specific components:
from config import create_llm_client
client = create_llm_client()

# To this:
from llm.enhanced_config import create_enhanced_llm_client
client = create_enhanced_llm_client()

# Then use async/await for calls:
response = await client.generate_content(...)
```

## 4. Monitoring

Start the monitoring dashboard to see real-time performance:

```bash
# Run the monitoring dashboard
python llm/tools/monitor_llm.py
```

This shows:
- Provider health status
- Success rates
- Response times
- Cache performance
- Cost tracking

For visualization of trends:

```bash
# Generate visualization from collected data
python llm/tools/dashboard_visualization.py
```

This creates graphs and reports in the `llm/monitoring/` directory.

## 5. Testing

Run the test suite to verify functionality:

```bash
# Run the comprehensive test suite
python llm/test_enhanced_llm.py
```

For performance comparison with the standard client:

```bash
# Run migration script with performance comparison
bash llm/tools/migrate_to_enhanced.sh
```

## 6. Key Benefits

The enhanced client provides:

- **Better Reliability**: Automatic fallback between providers
- **Faster Responses**: Smart provider selection and caching
- **Lower Costs**: Better tracking and optimization
- **More Insights**: Comprehensive monitoring and alerts

## 7. Common Usage Patterns

### Basic Usage (Async)

```python
from llm.enhanced_config import create_enhanced_llm_client

async def my_function():
    client = create_enhanced_llm_client()
    
    response = await client.generate_content(
        contents="Your prompt here",
        config={"temperature": 0.1, "max_output_tokens": 100},
        model="gemini-2.5-flash-preview-05-20"
    )
    
    print(response.text)
    print(f"Provider: {response.provider}")
    print(f"Response time: {response.response_time_ms}ms")
    print(f"Cost: ${response.estimated_cost_usd:.6f}")
```

### Basic Usage (Sync)

```python
import asyncio
from llm.enhanced_config import create_enhanced_llm_client

def my_function():
    client = create_enhanced_llm_client()
    
    response = asyncio.run(client.generate_content(
        contents="Your prompt here",
        config={"temperature": 0.1, "max_output_tokens": 100},
        model="gemini-2.5-flash-preview-05-20"
    ))
    
    print(response.text)
```

### Status Reporting

```python
client = create_enhanced_llm_client()
status_report = client.get_status_report()

print(f"Success rate: {status_report['global_metrics']['success_rate'] * 100:.1f}%")
print(f"Average response time: {status_report['global_metrics']['avg_response_time']:.0f}ms")
print(f"Total cost: ${status_report['global_metrics']['total_cost_usd']:.6f}")
```

## 8. Next Steps

For complete information:

- See `llm/MIGRATION_GUIDE.md` for detailed migration instructions
- Read `llm/IMPLEMENTATION_SUMMARY.md` for architectural details
- Check `llm/COMPLETION_REPORT.md` for overall project status

## 9. Troubleshooting

### Client not working after enabling?

Check that async/await is being used correctly:

```python
# Wrong
response = client.generate_content(...)

# Right
response = await client.generate_content(...)  # In async function
# OR
response = asyncio.run(client.generate_content(...))  # In sync function
```

### Missing dependencies?

Ensure you have all required packages:

```bash
pip install google-genai requests matplotlib numpy
```

### Need help?

Run the migration script for guidance:

```bash
bash llm/tools/migrate_to_enhanced.sh
```
