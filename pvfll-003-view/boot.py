import time
from display import init_display, display_centered_message, display_boot_splash, display_portal_message, load_file_icon
from util import is_wifi_connected
from api import fetch_all_boxes
from pusher_events import PusherListener

WIFI_RETRY_INTERVAL = 10  # seconds between WiFi checks


def boot_sequence() -> tuple:
    """
    Boot sequence:
      1. Initialize display + load file icon
      2. Check Wi-Fi connectivity (wait with portal message if not connected)
      3. Connect to Pusher WebSocket
      4. Fetch initial box data
    Returns (box_data, pusher_listener) or (None, None) on failure.
    """

    # Step 1: Initialize display + show boot splash
    try:
        init_display()
        load_file_icon()
        display_boot_splash("Booting...")
        time.sleep(2)
    except Exception as e:
        print(f"Error initializing display: {e}")
        return None, None

    # Step 2: Check Wi-Fi — show portal instructions and retry until connected
    display_boot_splash("Checking Wi-Fi...")
    if not is_wifi_connected():
        print("No Wi-Fi — showing captive portal instructions")
        display_portal_message()
        while not is_wifi_connected():
            time.sleep(WIFI_RETRY_INTERVAL)
        print("Wi-Fi connected!")
        display_boot_splash("Wi-Fi connected!")
        time.sleep(1)

    # Step 3: Connect to Pusher
    display_boot_splash("Connecting...")
    pusher_listener = PusherListener()
    if pusher_listener.connect():
        print("WebSocket connected")
    else:
        display_boot_splash("WebSocket failed")
        print("Failed to connect to WebSocket")
        return None, None

    # Step 4: Fetch initial data
    display_boot_splash("Fetching data...")
    try:
        box_data = fetch_all_boxes()
        display_boot_splash("Boot complete!")
        time.sleep(1)
        return box_data, pusher_listener
    except Exception as e:
        display_boot_splash("Data fetch failed")
        print(f"Error fetching data: {e}")
        return None, None
