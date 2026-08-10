import os
import sys
import subprocess
import time
import webbrowser

def kill_port(port):
    try:
        output = subprocess.check_output("netstat -aon", shell=True).decode()
        for line in output.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = int(parts[-1])
                    print(f"Releasing port {port} (killing PID {pid})...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def main():
    # Change working directory to project root (where launcher.py resides)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    print("==============================================================")
    print("                AeroSense GCS Launcher")
    print("==============================================================")
    print()
    
    # Releasing ports
    print("[1/4] Releasing ports 5001 and 8050...")
    kill_port(5001)
    kill_port(8050)
    
    # Starting GCS Flask server
    print("[2/4] Starting GCS API Server on port 5001...")
    api_proc = subprocess.Popen([sys.executable, "Ground/ground_station/aerosense_api.py"], 
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    
    # Starting Dash server
    print("[3/4] Starting Dash Dashboard on port 8050...")
    dash_proc = subprocess.Popen([sys.executable, "dashboard/aerosense_dashboard.py"], 
                                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    
    # Waiting a moment for servers to bind
    time.sleep(2)
    
    # Opening browser
    print("[4/4] Opening Ground Control Station and Dashboard...")
    webbrowser.open("http://localhost:5001")
    webbrowser.open("http://localhost:8050")
    
    print("\n==============================================================")
    print(" AeroSense GCS and Dashboard are now running!")
    print(" - GCS Web App: http://localhost:5001")
    print(" - Plotly Dash Dashboard: http://localhost:8050")
    print("\n Press Ctrl+C or close this window to exit and stop all servers.")
    print("==============================================================")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping background servers...")
        api_proc.terminate()
        dash_proc.terminate()
        time.sleep(1)
        # Force-kill if any are hanging
        kill_port(5001)
        kill_port(8050)
        print("Done.")

if __name__ == "__main__":
    main()
