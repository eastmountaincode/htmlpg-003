#!/usr/bin/env python3
"""API client to fetch box status from the centralized htmlpg app."""

import requests
import os
import time
from typing import Dict, Any
from dotenv import load_dotenv
from util import get_file_type

load_dotenv(".env.local")

API_BASE = os.getenv("API_BASE")
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "8"))


def fetch_box_status(box_number: int, retries: int = 1, delay: int = 3) -> Dict[str, Any]:
    """Fetch the status of a single box with retries."""
    url = f"{API_BASE}/boxes/{box_number}/files"
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            data.setdefault("empty", True)
            if not data.get("empty") and data.get("name"):
                data["type"] = get_file_type(data["name"])
            return data
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1}/{retries} failed for box {box_number}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return {"empty": True, "error": str(e)}


def fetch_all_boxes() -> Dict[int, Dict[str, Any]]:
    """Fetch status of all 4 boxes."""
    results = {}
    for box_num in [1, 2, 3, 4]:
        print(f"Fetching box {box_num}...")
        results[box_num] = fetch_box_status(box_num)
    return results
