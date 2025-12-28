import sys
import os
import cv2

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adb_wrapper import ADBWrapper

def capture():
    adb = ADBWrapper()
    if not adb.connect():
        print("Error: No device connected.")
        return

    print("Taking screenshot...")
    img = adb.take_screenshot()
    if img is not None:
        filename = "captura_lobby_anchor.png"
        cv2.imwrite(filename, img)
        print(f"Screenshot saved to {os.path.abspath(filename)}")
    else:
        print("Failed to capture screenshot.")

if __name__ == "__main__":
    capture()
