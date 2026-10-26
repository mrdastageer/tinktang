"""
Scan through all models and find ALL currently active working ones
"""
import json
import sys
import time
from pathlib import Path
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.config import Config

# Load live catalog
with open("live_models_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

NVIDIA_CANDIDATES = catalog.get("nvidia-nim", [])
GEMINI_CANDIDATES = catalog.get("google-gemini", [])

print(f"Loaded {len(NVIDIA_CANDIDATES)} NVIDIA models and {len(GEMINI_CANDIDATES)} Gemini models to test.")

def test_nvidia(model_name):
    """Test NVIDIA model with prompt"""
    try:
        headers = {
            "Authorization": f"Bearer {Config.NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hello, respond with one word."}],
            "max_tokens": 10,
            "temperature": 0.2
        }
        r = requests.post(
            Config.NVIDIA_BASE_URL + "/chat/completions",
            headers=headers,
            json=payload,
            timeout=8
        )
        if r.status_code == 200:
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if content and content.strip():
                return model_name, True, content.strip().replace("\n", " ")[:30]
        return model_name, False, f"HTTP {r.status_code}"
    except Exception as e:
        return model_name, False, str(e)[:30]

def test_gemini(model_name):
    """Test Gemini model with prompt"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": Config.GOOGLE_API_KEY}
        payload = {
            "contents": [{"parts": [{"text": "Hello, respond with one word."}]}],
            "generationConfig": {"maxOutputTokens": 10, "temperature": 0.2}
        }
        r = requests.post(url, headers=headers, params=params, json=payload, timeout=12)
        if r.status_code == 200:
            candidates = r.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and parts[0].get("text"):
                    return model_name, True, parts[0].get("text").strip().replace("\n", " ")[:30]
        return model_name, False, f"HTTP {r.status_code}"
    except Exception as e:
        return model_name, False, str(e)[:30]

print("\n1. Testing all NVIDIA models (in parallel)...")
working_nvidia = []
with ThreadPoolExecutor(max_workers=6) as executor:
    futures = {executor.submit(test_nvidia, m): m for m in NVIDIA_CANDIDATES}
    for f in as_completed(futures):
        m, ok, res = f.result()
        if ok:
            print(f"  [OK] {m:50} -> {res}")
            working_nvidia.append(m)

print(f"\nTotal working NVIDIA models: {len(working_nvidia)}")

print("\n2. Testing all Gemini models (sequentially to avoid rate limits)...")
working_gemini = []
for m in GEMINI_CANDIDATES:
    m, ok, res = test_gemini(m)
    if ok:
        print(f"  [OK] {m:50} -> {res}")
        working_gemini.append(m)
    else:
        # If rate limited, sleep longer
        if "429" in res or "503" in res:
            time.sleep(2)
    time.sleep(0.5)

print(f"\nTotal working Gemini models: {len(working_gemini)}")

# Save verified models
verified = {
    "nvidia-nim": sorted(working_nvidia),
    "google-gemini": sorted(working_gemini)
}

with open("verified_working_models.json", "w", encoding="utf-8") as f:
    json.dump(verified, f, indent=2)

print("\nSaved confirmed working models to verified_working_models.json")
