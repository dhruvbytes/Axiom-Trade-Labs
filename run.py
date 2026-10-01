import subprocess
import sys
import webbrowser
import threading
import time
import urllib.request
import urllib.error

def wait_and_open_browser():
    url = "http://127.0.0.1:8000/api/health"
    timeout = 60  # Max wait time 60 seconds
    start_time = time.time()
    
    print("[SYSTEM] Waiting for backend to boot completely...")
    
    # Jab tak server HTTP 200 OK response nahi deta, tab tak loop chalega
    while time.time() - start_time < timeout:
        try:
            response = urllib.request.urlopen(url)
            if response.getcode() == 200:
                # Server is officially ready!
                time.sleep(0.2) # Chota सा buffer UI smoothly load hone ke liye
                print("\n[SYSTEM] Server is LIVE! Opening Axiom Terminal...")
                webbrowser.open("http://127.0.0.1:8000")
                return
        except (urllib.error.URLError, ConnectionResetError):
            pass # Server abhi start ho raha hai, wait karo
        
        time.sleep(1) # Har 1 second mein check karo
        
    print("\n[ERROR] Server took too long to start. Please open http://127.0.0.1:8000 manually.")

def main():
    print("\n" + "="*50)
    print("🚀 IGNITING AXIOM TRADE LABS TERMINAL...")
    print("="*50 + "\n")
    
    # Polling function ko background mein start kar diya
    threading.Thread(target=wait_and_open_browser, daemon=True).start()
    
    # Server start command
    command = [
        sys.executable, "-m", "uvicorn", 
        "backend.main:app", 
        "--host", "127.0.0.1", 
        "--port", "8000", 
        "--reload"
    ]
    
    try:
        subprocess.run(command, check=True)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down Axiom Terminal safely...")
    except Exception as e:
        print(f"\n[ERROR] Failed to start server: {e}")

if __name__ == "__main__":
    main()