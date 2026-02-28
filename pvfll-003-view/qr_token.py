#!/usr/bin/env python3
"""
Rotating QR token generation — matches frontend qr-token.ts exactly.
HMAC-SHA256 of "{deviceId}{timeSlot}" where timeSlot = floor(unix_time / interval).
"""

import hmac
import hashlib
import os
import time
from dotenv import load_dotenv

load_dotenv(".env.local")

QR_SECRET = os.getenv("QR_SECRET", "")
QR_INTERVAL_SECONDS = int(os.getenv("QR_INTERVAL_SECONDS", "1800"))
DEVICE_ID = os.getenv("DEVICE_ID", "htmlpg-003")
BASE_URL = "https://htmlpg.andrew-boylan.com"


def generate_token(timestamp_seconds: int = None) -> str:
    """Generate HMAC token for the current (or given) time slot."""
    if timestamp_seconds is None:
        timestamp_seconds = int(time.time())
    time_slot = timestamp_seconds // QR_INTERVAL_SECONDS
    message = f"{DEVICE_ID}{time_slot}"
    return hmac.new(QR_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()[:16]


def get_qr_url(timestamp_seconds: int = None) -> str:
    """Generate the full QR code URL for the current time slot."""
    token = generate_token(timestamp_seconds)
    return f"{BASE_URL}/v/{DEVICE_ID}/{token}"


def seconds_until_next_slot() -> float:
    """Seconds remaining until the next time slot boundary."""
    now = time.time()
    current_slot_end = ((int(now) // QR_INTERVAL_SECONDS) + 1) * QR_INTERVAL_SECONDS
    return current_slot_end - now


if __name__ == "__main__":
    print(f"Device ID:  {DEVICE_ID}")
    print(f"Interval:   {QR_INTERVAL_SECONDS}s")
    print(f"Token:      {generate_token()}")
    print(f"QR URL:     {get_qr_url()}")
    print(f"Next slot:  {seconds_until_next_slot():.1f}s")
