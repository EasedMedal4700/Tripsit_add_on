import re
import json
import os
import hashlib

def normalize(name: str) -> str:
    """Normalize substance names for matching."""
    if not name: return ""
    return re.sub(r"[- ,]", "", name.lower())

def get_report_id(url):
    match = re.search(r'ID=(\d+)', url)
    if match:
        return match.group(1)
    return hashlib.md5(url.encode()).hexdigest()

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
