"""
Test ALL 125 models and generate a complete breakdown of every non-working model
with exact error codes and descriptions.
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

with open("live_models_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

NVIDIA_MODELS = catalog.get("nvidia-nim", [])
GEMINI_MODELS = catalog.get("google-gemini", [])

results = {
    "nvidia-nim": {"working": {}, "not_working": {}},
    "google-gemini": {"working": {}, "not_working": {}}
}

def test_nvidia(model_name):
    try:
        headers = {
            "Authorization": f"Bearer {Config.NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "temperature": 0.1
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
                return model_name, True, "200 OK", content.strip()[:30]
            return model_name, False, "200 Empty Response", "No content returned"
        else:
            try:
                err_data = r.json()
                detail = err_data.get("detail") or err_data.get("error", {}).get("message") or err_data.get("title") or r.text[:80]
            except Exception:
                detail = r.text[:80]
            return model_name, False, f"HTTP {r.status_code}", detail
    except requests.exceptions.Timeout:
        return model_name, False, "Timeout", "Request timed out after 8s"
    except Exception as e:
        return model_name, False, "Connection Error", str(e)[:60]

def test_gemini(model_name):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": Config.GOOGLE_API_KEY}
        payload = {
            "contents": [{"parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 5, "temperature": 0.1}
        }
        r = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
        if r.status_code == 200:
            candidates = r.json().get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and parts[0].get("text"):
                    return model_name, True, "200 OK", parts[0].get("text").strip()[:30]
            return model_name, False, "200 Empty Response", "No candidates / parts returned"
        else:
            try:
                err_data = r.json()
                msg = err_data.get("error", {}).get("message") or err_data.get("error", {}).get("status") or r.text[:80]
            except Exception:
                msg = r.text[:80]
            return model_name, False, f"HTTP {r.status_code}", msg
    except requests.exceptions.Timeout:
        return model_name, False, "Timeout", "Request timed out after 10s"
    except Exception as e:
        return model_name, False, "Connection Error", str(e)[:60]

print(f"Testing {len(NVIDIA_MODELS)} NVIDIA models...")
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(test_nvidia, m): m for m in NVIDIA_MODELS}
    for f in as_completed(futures):
        m, ok, status_code, detail = f.result()
        if ok:
            results["nvidia-nim"]["working"][m] = {"status": status_code, "sample": detail}
        else:
            results["nvidia-nim"]["not_working"][m] = {"error": status_code, "detail": detail}

print(f"Testing {len(GEMINI_MODELS)} Gemini models...")
for m in GEMINI_MODELS:
    m, ok, status_code, detail = test_gemini(m)
    if ok:
        results["google-gemini"]["working"][m] = {"status": status_code, "sample": detail}
    else:
        results["google-gemini"]["not_working"][m] = {"error": status_code, "detail": detail}
    time.sleep(0.4)

with open("full_models_audit.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("Saved full audit to full_models_audit.json")
