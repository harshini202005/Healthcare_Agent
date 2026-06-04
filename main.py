#!/usr/bin/env python3
"""
Healthcare Assistant - Main Launcher
Run this file to start the backend server + frontend
"""

import sys
import os
import subprocess
import threading
import time
import webbrowser
import urllib.request

def wait_and_open_browser(url="http://localhost:8000", timeout=30):
    """Wait for server to be ready, then open browser."""
    # Use 127.0.0.1 for the health-check so we always hit IPv4
    # (localhost can resolve to ::1 on macOS which uvicorn 0.0.0.0 won't answer)
    check_url = url.replace("localhost", "127.0.0.1")
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(check_url, timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    webbrowser.open(url)
    print(f"🌐 Opened {url} in your browser")

def main():
    print("🏥 Healthcare Assistant - Starting Server...")
    print("=" * 60)
    
    # Check if virtual environment is activated
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Virtual environment not activated!")
        print("\n📝 To activate, run:")
        print("   source .venv/bin/activate")
        print("\nOr let me start it anyway...\n")
    
    # Get the project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        url = "http://localhost:8000"
        print(f"🚀 Starting server on {url}")
        print(f"📱 Frontend + Backend served at the same URL")
        print("⏹️  Press Ctrl+C to stop the server")
        print("=" * 60)
        print()
        
        # Start browser opener in background thread
        browser_thread = threading.Thread(
            target=wait_and_open_browser,
            args=(url,),
            daemon=True
        )
        browser_thread.start()
        
        # Start uvicorn server
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000"
        ], cwd=project_dir)
        
    except KeyboardInterrupt:
        print("\n\n✅ Server stopped successfully!")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        print("\n💡 Make sure you have installed dependencies:")
        print("   pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()