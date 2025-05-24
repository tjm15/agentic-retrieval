#!/usr/bin/env python3
# filepath: /home/tim-mayoh/repos/agentic-retrieval/llm/tools/dashboard_visualization.py
"""
Enhanced LLM Client Dashboard Visualization
Generates visualizations of LLM performance data collected by the monitor.
"""

import os
import sys
import json
# Attempt to import matplotlib, but don't fail if it's not installed
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("WARN: matplotlib.pyplot not found. Plotting will be disabled.")
    print("Please install matplotlib to enable plotting: pip install matplotlib")

from datetime import datetime
import glob
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def load_snapshots(monitoring_dir='llm/monitoring'):
    """Load all available snapshots"""
    snapshot_files = glob.glob(f"{monitoring_dir}/snapshot_*.json")
    snapshots = []
    
    for file_path in sorted(snapshot_files):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                # Extract timestamp from filename
                timestamp_str = os.path.basename(file_path).replace('snapshot_', '').replace('.json', '')
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                snapshots.append({
                    'timestamp': timestamp,
                    'data': data
                })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    return snapshots


def plot_response_times(snapshots, output_dir='llm/monitoring'):
    """Plot response time trends"""
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping plot_response_times due to missing matplotlib.")
        return
    if not snapshots:
        print("No data available for plotting")
        return
    
    # Extract data
    timestamps = [s['timestamp'] for s in snapshots]
    avg_times = [s['data']['global_metrics']['avg_response_time'] for s in snapshots]
    
    # Provider-specific times
    providers = {}
    for snapshot in snapshots:
        for provider_name, provider_data in snapshot['data']['providers'].items():
            if provider_name not in providers:
                providers[provider_name] = []
            
            response_time = provider_data['avg_response_time']
            # Handle infinity values
            if response_time == float('inf'):
                response_time = None
            providers[provider_name].append(response_time)
    
    # Create plot
    plt.figure(figsize=(12, 6))
    
    # Plot overall average
    plt.plot(timestamps, avg_times, 'k-', label='Overall Average', linewidth=2)
    
    # Plot per-provider times
    colors = ['b', 'g', 'r', 'c', 'm', 'y']
    for i, (provider_name, times) in enumerate(providers.items()):
        color = colors[i % len(colors)]
        # Filter out None values
        valid_points = [(t, v) for t, v in zip(timestamps, times) if v is not None]
        if valid_points:
            valid_timestamps, valid_times = zip(*valid_points)
            plt.plot(valid_timestamps, valid_times, f'{color}-', label=provider_name)
    
    # Format plot
    plt.title('LLM Response Times')
    plt.xlabel('Time')
    plt.ylabel('Response Time (ms)')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/response_times.png")
    plt.close()
    
    print(f"Response time plot saved to {output_dir}/response_times.png")


def plot_success_rates(snapshots, output_dir='llm/monitoring'):
    """Plot success rate trends"""
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping plot_success_rates due to missing matplotlib.")
        return
    if not snapshots:
        print("No data available for plotting")
        return
    
    # Extract data
    timestamps = [s['timestamp'] for s in snapshots]
    success_rates = [s['data']['global_metrics']['success_rate'] * 100 for s in snapshots]
    
    # Provider-specific rates
    providers = {}
    for snapshot in snapshots:
        for provider_name, provider_data in snapshot['data']['providers'].items():
            if provider_name not in providers:
                providers[provider_name] = []
            providers[provider_name].append(provider_data['success_rate'] * 100)
    
    # Create plot
    plt.figure(figsize=(12, 6))
    
    # Plot overall rate
    plt.plot(timestamps, success_rates, 'k-', label='Overall', linewidth=2)
    
    # Plot per-provider rates
    colors = ['b', 'g', 'r', 'c', 'm', 'y']
    for i, (provider_name, rates) in enumerate(providers.items()):
        color = colors[i % len(colors)]
        plt.plot(timestamps, rates, f'{color}-', label=provider_name)
    
    # Format plot
    plt.title('LLM Success Rates')
    plt.xlabel('Time')
    plt.ylabel('Success Rate (%)')
    plt.ylim(0, 105)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/success_rates.png")
    plt.close()
    
    print(f"Success rate plot saved to {output_dir}/success_rates.png")


def plot_cost_analysis(snapshots, output_dir='llm/monitoring'):
    """Plot cost analysis"""
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping plot_cost_analysis due to missing matplotlib.")
        return
    if not snapshots:
        print("No data available for plotting")
        return
    
    # Extract data
    timestamps = [s['timestamp'] for s in snapshots]
    total_costs = [s['data']['global_metrics']['total_cost_usd'] for s in snapshots]
    
    # Calculate cumulative cost
    cumulative_costs = np.cumsum(total_costs)
    
    # Create plot
    plt.figure(figsize=(12, 6))
    
    # Plot per-call cost
    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(timestamps, total_costs, 'b-', marker='o')
    ax1.set_title('Per-Snapshot Cost')
    ax1.set_ylabel('Cost ($)')
    ax1.grid(True, linestyle='--', alpha=0.7)
    
    # Plot cumulative cost
    ax2 = plt.subplot(2, 1, 2)
    ax2.plot(timestamps, cumulative_costs, 'r-', marker='o')
    ax2.set_title('Cumulative Cost')
    ax2.set_xlabel('Time')
    ax2.set_ylabel('Total Cost ($)')
    ax2.grid(True, linestyle='--', alpha=0.7)
    
    plt.tight_layout()
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/cost_analysis.png")
    plt.close()
    
    print(f"Cost analysis plot saved to {output_dir}/cost_analysis.png")


def plot_cache_performance(snapshots, output_dir='llm/monitoring'):
    """Plot cache performance"""
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping plot_cache_performance due to missing matplotlib.")
        return
    if not snapshots:
        print("No data available for plotting")
        return
    
    # Extract data
    timestamps = [s['timestamp'] for s in snapshots]
    hit_rates = [s['data']['cache_stats']['hit_rate'] * 100 for s in snapshots]
    
    # Create plot
    plt.figure(figsize=(12, 6))
    plt.plot(timestamps, hit_rates, 'g-', marker='o')
    
    # Format plot
    plt.title('Cache Performance')
    plt.xlabel('Time')
    plt.ylabel('Hit Rate (%)')
    plt.ylim(0, 105)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    plt.savefig(f"{output_dir}/cache_performance.png")
    plt.close()
    
    print(f"Cache performance plot saved to {output_dir}/cache_performance.png")


def generate_summary_report(snapshots, output_dir='llm/monitoring'):
    """Generate a summary report"""
    if not snapshots:
        print("No data available for report")
        return
    
    # Get latest data
    latest = snapshots[-1]['data']
    
    # Calculate statistics
    total_calls = latest['global_metrics']['total_calls']
    success_rate = latest['global_metrics']['success_rate'] * 100
    avg_response_time = latest['global_metrics']['avg_response_time']
    total_cost = latest['global_metrics']['total_cost_usd']
    cache_hit_rate = latest['cache_stats']['hit_rate'] * 100
    
    # Provider status
    provider_status = {name: data['state'] for name, data in latest['providers'].items()}
    
    # Generate report
    report = f"""
# Enhanced LLM Client Performance Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Overall Statistics
- Total API Calls: {total_calls}
- Success Rate: {success_rate:.1f}%
- Average Response Time: {avg_response_time:.0f}ms
- Total Cost: ${total_cost:.6f}
- Cache Hit Rate: {cache_hit_rate:.1f}%

## Provider Status
"""
    
    for provider, status in provider_status.items():
        report += f"- {provider}: {status.upper()}\n"
    
    # Add alerts
    alerts = latest.get('alerts', [])
    if alerts:
        report += "\n## Active Alerts\n"
        for alert in alerts:
            report += f"- {alert['level'].upper()}: {alert['message']}\n"
    
    # Save report
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = f"{output_dir}/performance_summary_{timestamp}.md"
    
    with open(report_path, 'w') as f:
        f.write(report)
    
    print(f"Summary report saved to {report_path}")
    return report_path


def main():
    """Main function"""
    print("📊 Enhanced LLM Client Dashboard Visualization")
    print("=" * 50)
    
    # Load snapshots
    print("Loading monitoring data...")
    snapshots = load_snapshots()
    
    if not snapshots:
        print("No monitoring data found. Run the monitor_llm.py script first.")
        return
    
    print(f"Found {len(snapshots)} data points.")
    
    # Generate visualizations
    print("\nGenerating visualizations...")
    plot_response_times(snapshots)
    plot_success_rates(snapshots)
    plot_cost_analysis(snapshots)
    plot_cache_performance(snapshots)
    
    # Generate report
    print("\nGenerating summary report...")
    report_path = generate_summary_report(snapshots)
    
    print("\n✅ Dashboard visualization complete!")
    print(f"All outputs saved to llm/monitoring/")


if __name__ == "__main__":
    # Check dependencies
    try:
        import numpy
    except ImportError:
        print("Missing dependencies. Please install required packages:")
        print("pip install numpy")
        sys.exit(1)
    
    main()
