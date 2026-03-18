#!/usr/bin/env python3
"""Pusher WebSocket client — listens for real-time box update events."""

import os
import json
import time
import threading
from dotenv import load_dotenv

try:
    import pysher
    PUSHER_AVAILABLE = True
except ImportError:
    print("pysher not found — install with: pip install pysher")
    PUSHER_AVAILABLE = False
    pysher = None

load_dotenv(".env.local")

PUSHER_APP_KEY = os.getenv("PUSHER_APP_KEY")
PUSHER_CLUSTER = os.getenv("PUSHER_CLUSTER", "us2")
PUSHER_CHANNEL = os.getenv("PUSHER_CHANNEL", "garden")

# If no Pusher event received within this window, force a full reconnect
ACTIVITY_TIMEOUT = 120  # seconds


class PusherListener:
    def __init__(self, on_box_update_callback=None):
        self.on_box_update = on_box_update_callback
        self.pusher = None
        self.channel = None
        self.connected = False
        self.last_activity = time.monotonic()
        self._lock = threading.Lock()

    def connect(self):
        if not PUSHER_AVAILABLE or not PUSHER_APP_KEY:
            print("Pusher not available or PUSHER_APP_KEY not set")
            return False
        try:
            # Tear down any existing connection first
            self._teardown()

            self.pusher = pysher.Pusher(
                PUSHER_APP_KEY, cluster=PUSHER_CLUSTER, secure=True
            )
            self.pusher.connection.bind("pusher:connection_established", self._on_connect)
            self.pusher.connection.bind("pusher:connection_failed", self._on_connection_failed)
            self.pusher.connection.bind("pusher:error", self._on_error)
            self.pusher.connect()
            print(f"Connecting to Pusher (key: {PUSHER_APP_KEY[:8]}..., cluster: {PUSHER_CLUSTER})")

            # Wait up to 5 seconds for connection
            for _ in range(50):
                if self.connected:
                    break
                time.sleep(0.1)

            if not self.connected:
                print("Pusher connection timed out")
                return False

            return True
        except Exception as e:
            print(f"Error connecting to Pusher: {e}")
            return False

    def _subscribe(self):
        """Subscribe to channel and bind event handlers."""
        with self._lock:
            try:
                self.channel = self.pusher.subscribe(PUSHER_CHANNEL)
                self.channel.bind("file-uploaded", self._on_file_event)
                self.channel.bind("file-deleted", self._on_file_event)
                self.last_activity = time.monotonic()
                print(f"Subscribed to channel '{PUSHER_CHANNEL}'")
            except Exception as e:
                print(f"Error subscribing to channel: {e}")

    def _teardown(self):
        """Cleanly disconnect and reset state."""
        with self._lock:
            self.connected = False
            self.channel = None
            if self.pusher:
                try:
                    self.pusher.disconnect()
                except Exception:
                    pass
                self.pusher = None

    def _on_connect(self, data):
        """Called on initial connect AND on pysher auto-reconnects."""
        self.connected = True
        self.last_activity = time.monotonic()
        print("Pusher connected — (re)subscribing to channel")
        self._subscribe()

    def _on_connection_failed(self, data):
        self.connected = False
        print(f"Pusher connection failed: {data}")

    def _on_error(self, data):
        self.connected = False
        print(f"Pusher error: {data}")

    def _on_file_event(self, data):
        self.last_activity = time.monotonic()
        try:
            if isinstance(data, str):
                data = json.loads(data)
            box_number = data.get("boxNumber")
            if box_number and self.on_box_update:
                print(f"Pusher event: updating box {box_number}")
                self.on_box_update(int(str(box_number).strip()))
        except Exception as e:
            print(f"Error processing Pusher event: {e}")

    def check_health(self):
        """
        Check if the connection is actually alive.
        Returns True if healthy, False if a reconnect is needed.
        """
        if not self.connected:
            return False

        # If we haven't seen any activity (connect/event) in ACTIVITY_TIMEOUT,
        # the socket is probably silently dead
        idle = time.monotonic() - self.last_activity
        if idle > ACTIVITY_TIMEOUT:
            print(f"Pusher idle for {idle:.0f}s — assuming dead connection")
            return False

        return True

    def force_reconnect(self):
        """Full teardown and fresh reconnect."""
        print("Pusher: forcing full reconnect...")
        self._teardown()
        time.sleep(1)
        return self.connect()

    def disconnect(self):
        self._teardown()
