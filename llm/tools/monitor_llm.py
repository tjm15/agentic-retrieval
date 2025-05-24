#!/usr/bin/env python3
# filepath: /home/tim-mayoh/repos/agentic-retrieval/llm/tools/monitor_llm.py
"""
Simple monitoring dashboard for the enhanced LLM client.
"""

import os
import sys
import time
import json
from datetime import datetime
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm.enhanced_config import create_enhanced_llm_client, create_monitoring_dashboard_data


def print_header():
    """Print dashboard header"""
    print("\033c", end="")  # Clear screen
    print(f"📊 Enhanced LLM Client Monitoring Dashboard | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


def print_summary(dashboard_data):
    """Print summary statistics"""
    summary = dashboard_data["summary"]
    
    # Calculate provider health
    healthy = summary["healthy_providers"]
    total = summary["total_providers"]
    health_pct = (healthy / total * 100) if total > 0 else 0
    
    # Health status indicator
    if health_pct == 100:
        health_status = "\033[92m● HEALTHY\033[0m"  # Green
    elif health_pct >= 50:
        health_status = "\033[93m● DEGRADED\033[0m"  # Yellow
    else:
        health_status = "\033[91m● CRITICAL\033[0m"  # Red
    
    print(f"System Status: {health_status} | {healthy}/{total} providers available")
    print(f"Total Calls: {summary['total_calls']} | Success Rate: {summary['success_rate_pct']:.1f}%")
    print(f"Avg Response: {summary['avg_response_time_ms']:.0f}ms | Cache Hit Rate: {summary['cache_hit_rate_pct']:.1f}%")
    print(f"Total Cost: ${summary['total_cost_usd']:.6f}")
    print("-" * 80)


def print_providers(dashboard_data):
    """Print provider details"""
    print("Provider Status:")
    
    for provider in dashboard_data["providers"]:
        # Status indicators
        if provider["status"] == "healthy":
            status_icon = "\033[92m●\033[0m"  # Green
        elif provider["status"] == "degraded":
            status_icon = "\033[93m●\033[0m"  # Yellow
        elif provider["status"] == "recovering":
            status_icon = "\033[94m●\033[0m"  # Blue
        else:
            status_icon = "\033[91m●\033[0m"  # Red
        
        # Format provider data
        name = provider["name"].ljust(12)
        health = f"{provider['health_score']*100:.0f}%".rjust(4)
        success = f"{provider['success_rate_pct']:.1f}%".rjust(6)
        
        if provider["avg_response_time_ms"] is not None:
            response = f"{provider['avg_response_time_ms']:.0f}ms".rjust(7)
        else:
            response = "   N/A".rjust(7)
            
        calls = str(provider["total_calls"]).rjust(4)
        
        print(f"  {status_icon} {name} | Health: {health} | Success: {success} | Response: {response} | Calls: {calls}")
    
    print("-" * 80)


def print_alerts(dashboard_data):
    """Print active alerts"""
    alerts = dashboard_data.get("alerts", [])
    
    if not alerts:
        print("🟢 No active alerts")
        return
    
    print(f"🚨 Active Alerts ({len(alerts)}):")
    
    for alert in alerts:
        if alert["level"] == "error":
            level_icon = "\033[91m!\033[0m"  # Red
        else:
            level_icon = "\033[93m!\033[0m"  # Yellow
            
        print(f"  {level_icon} {alert['message']}")


async def run_dashboard(refresh_seconds=5):
    """Run the monitoring dashboard"""
    # Create the enhanced client
    client = create_enhanced_llm_client()
    
    try:
        while True:
            # Generate dashboard data
            dashboard_data = create_monitoring_dashboard_data(client)
            
            # Print dashboard
            print_header()
            print_summary(dashboard_data)
            print_providers(dashboard_data)
            print_alerts(dashboard_data)
            
            # Save snapshot to file
            save_snapshot(dashboard_data)
            
            # Wait for refresh
            print(f"\nRefreshing in {refresh_seconds} seconds... (Press Ctrl+C to exit)")
            await asyncio.sleep(refresh_seconds)
            
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


def save_snapshot(dashboard_data):
    """Save dashboard snapshot to file"""
    try:
        os.makedirs("llm/monitoring", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save latest snapshot
        with open("llm/monitoring/latest_snapshot.json", "w") as f:
            json.dump(dashboard_data, f, indent=2)
        
        # Every 10 minutes, save a timestamped snapshot
        current_minute = datetime.now().minute
        if current_minute % 10 == 0:
            with open(f"llm/monitoring/snapshot_{timestamp}.json", "w") as f:
                json.dump(dashboard_data, f, indent=2)
                
    except Exception as e:
        print(f"Error saving snapshot: {e}")


if __name__ == "__main__":
    # Check if environment variable is set
    if os.getenv("USE_ENHANCED_LLM_CLIENT", "false").lower() != "true":
        print("⚠️  Enhanced LLM client is not enabled.")
        print("Please run: export USE_ENHANCED_LLM_CLIENT=true")
        sys.exit(1)
    
    # Run dashboard
    asyncio.run(run_dashboard())
