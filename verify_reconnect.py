import sys
import os
import time

# Add parent directory to path to import adb_wrapper
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adb_wrapper import ADBWrapper

def test_reconnection():
    print("Initializing ADB Wrapper...")
    adb = ADBWrapper()
    
    print("\n--- Starting Reconnection Test ---")
    print("Please follow these steps:")
    print("1. Ensure device is CONNECTED.")
    print("2. Unplug the device.")
    print("3. Wait for 'Connected: False'.")
    print("4. Plug the device back in.")
    print("5. Wait for 'Connected: True'.")
    print("----------------------------------\n")

    try:
        while True:
            is_connected = adb.is_connected()
            status = "Connected" if is_connected else "Disconnected"
            
            if is_connected:
                # Get some info to prove it's really talking to the device
                try:
                    s = adb.device.serial
                    print(f"[{time.strftime('%H:%M:%S')}] {status}: {s}")
                except:
                    print(f"[{time.strftime('%H:%M:%S')}] {status} (Error getting serial)")
            else:
                 print(f"[{time.strftime('%H:%M:%S')}] {status}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nTest stopped by user.")

if __name__ == "__main__":
    test_reconnection()
