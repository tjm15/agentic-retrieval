#!/usr/bin/env python3
"""
Test script to verify the system works with realistic Gemini API timeouts.
This version has proper progress indicators and realistic timeout expectations.
"""

import subprocess
import sys
import time
import signal
import os

def run_with_progress():
    """Run the main application with progress monitoring"""
    print("🚀 Starting Agentic Retrieval System with Realistic API Timeouts")
    print("=" * 70)
    print("⏱️  Note: Gemini API calls can take 2-5 minutes each")
    print("🔄 Progress indicators will show the system is working")
    print("⏹️  Press Ctrl+C to stop if needed")
    print("=" * 70)
    
    # Change to the correct directory
    os.chdir('/home/tim-mayoh/repos/agentic-retrieval')
    
    process = None  # Ensure process is always defined
    try:
        # Run the main application
        cmd = [sys.executable, 'main.py', '--query', 'What are the main planning policies for this development?']
        
        print(f"📋 Running: {' '.join(cmd)}")
        print(f"⏰ Started at: {time.strftime('%H:%M:%S')}")
        print("\n" + "📡 SYSTEM OUTPUT:" + "\n" + "-" * 50)
        
        # Run the process and capture output in real-time
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        start_time = time.time()
        last_output_time = start_time
        
        # Monitor output with timeout detection
        while True:
            if process.stdout is not None:
                output = process.stdout.readline()
            else:
                output = ''
            if output == '' and process.poll() is not None:
                break
                
            if output:
                current_time = time.time()
                elapsed = current_time - start_time
                since_last = current_time - last_output_time
                
                # Add timestamps to output
                timestamp = time.strftime('%H:%M:%S')
                print(f"[{timestamp}] {output.strip()}")
                
                last_output_time = current_time
                
                # Show elapsed time for long operations
                if "Sending request to Gemini API" in output:
                    print(f"    ⏳ API call started - allowing up to 5 minutes...")
                elif "Received response from Gemini API" in output:
                    print(f"    ✅ API call completed!")
            
            # Check if process is still alive
            if process.poll() is not None:
                break
                
        # Get final return code
        return_code = process.poll()
        end_time = time.time()
        total_time = end_time - start_time
        
        print("\n" + "-" * 50)
        print(f"⏰ Completed at: {time.strftime('%H:%M:%S')}")
        print(f"⏱️  Total runtime: {total_time:.1f} seconds")
        print(f"🏁 Exit code: {return_code}")
        
        if return_code == 0:
            print("✅ SUCCESS: System completed successfully!")
        elif return_code == 130:  # Ctrl+C
            print("⏹️  STOPPED: Interrupted by user")
        else:
            print(f"⚠️  WARNING: Process exited with code {return_code}")
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Stopped by user at {time.strftime('%H:%M:%S')}")
        try:
            if process is not None:
                process.terminate()
        except:
            pass
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    run_with_progress()
