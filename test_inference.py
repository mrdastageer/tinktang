"""
Thorough model testing with actual inference attempts
Tests models with retries and proper error handling
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

# Popular/recommended models to test first
NVIDIA_PRIORITY = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "meta/llama2-70b",
    "mistralai/mistral-large-2-instruct",
    "deepseek-ai/deepseek-v4.1-flash",
    "google/gemma-4-31b-it",
    "meta/codellama-70b",
    "01-ai/yi-large"
]

GEMINI_PRIORITY = [
    "gemini-1.5-flash",  # Stable production model
    "gemini-1.5-pro",    # Stable production model
    "gemini-2.0-flash-exp",  # Experimental
    "gemini-flash-latest",
    "gemini-pro-latest"
]

def test_nvidia_with_inference(model_name, retries=2):
    """Test NVIDIA model with actual inference"""
    for attempt in range(retries):
        try:
            headers = {
                "Authorization": f"Bearer {Config.NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'ok'"}],
                "max_tokens": 5,
                "temperature": 0.1
            }

            response = requests.post(
                Config.NVIDIA_BASE_URL + "/chat/completions",
                headers=headers,
                json=payload,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return True, "Working", content[:50]
                else:
                    return False, "No response content", None
            elif response.status_code == 404:
                return False, "Not Found (404)", None
            elif response.status_code == 429:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return False, "Rate Limited (429)", None
            else:
                return False, f"HTTP {response.status_code}", None

        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return False, "Timeout", None
        except Exception as e:
            return False, str(e)[:50], None

    return False, "Max retries exceeded", None

def test_gemini_with_inference(model_name, retries=3):
    """Test Gemini model with actual inference"""
    for attempt in range(retries):
        try:
            # Try without gemini/ prefix first
            test_name = model_name.replace("gemini/", "")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_name}:generateContent"

            headers = {"Content-Type": "application/json"}
            params = {"key": Config.GOOGLE_API_KEY}

            payload = {
                "contents": [{"parts": [{"text": "Say 'ok'"}]}],
                "generationConfig": {
                    "maxOutputTokens": 5,
                    "temperature": 0.1
                }
            }

            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=payload,
                timeout=20
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if content:
                        return True, "Working", content[:50]
                return False, "No candidates in response", None
            elif response.status_code == 404:
                return False, "Not Found (404)", None
            elif response.status_code == 503:
                # High demand - retry with exponential backoff
                if attempt < retries - 1:
                    wait = 3 * (2 ** attempt)
                    time.sleep(wait)
                    continue
                return False, "High Demand (503)", None
            elif response.status_code == 429:
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return False, "Rate Limited (429)", None
            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return False, error_msg[:60], None

        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return False, "Timeout", None
        except Exception as e:
            return False, str(e)[:50], None

    return False, "Max retries exceeded", None

def test_model_wrapper(provider, model):
    """Wrapper for parallel execution"""
    print(f"Testing {provider:15} {model:45}...", end=" ", flush=True)

    if provider == "nvidia-nim":
        success, reason, output = test_nvidia_with_inference(model)
    else:
        success, reason, output = test_gemini_with_inference(model)

    status = f"[OK]" if success else f"[FAIL: {reason}]"
    print(f"{status}")

    return (provider, model, success, reason, output)

def main():
    print("=" * 80)
    print("ThinkTank Model Testing with Live Inference")
    print("=" * 80)

    working = {"nvidia-nim": [], "google-gemini": []}
    failed = {"nvidia-nim": {}, "google-gemini": {}}

    print("\nTesting priority NVIDIA models...")
    print("-" * 80)
    for model in NVIDIA_PRIORITY:
        provider, model_name, success, reason, output = test_model_wrapper("nvidia-nim", model)
        if success:
            working[provider].append(model_name)
        else:
            failed[provider][model_name] = reason
        time.sleep(0.5)  # Rate limiting

    print("\nTesting priority Gemini models...")
    print("-" * 80)
    for model in GEMINI_PRIORITY:
        provider, model_name, success, reason, output = test_model_wrapper("google-gemini", model)
        if success:
            working[provider].append(model_name)
        else:
            failed[provider][model_name] = reason
        time.sleep(1)  # Rate limiting for Gemini

    # Summary
    print("\n" + "=" * 80)
    print("TESTED MODELS SUMMARY")
    print("=" * 80)

    print(f"\nNVIDIA NIM: {len(working['nvidia-nim'])}/{len(NVIDIA_PRIORITY)} Working")
    for m in working["nvidia-nim"]:
        print(f"  ✓ {m}")

    print(f"\nGoogle Gemini: {len(working['google-gemini'])}/{len(GEMINI_PRIORITY)} Working")
    for m in working["google-gemini"]:
        print(f"  ✓ {m}")

    if failed["nvidia-nim"]:
        print(f"\nNVIDIA Failed ({len(failed['nvidia-nim'])}):")
        for m, r in failed["nvidia-nim"].items():
            print(f"  ✗ {m}: {r}")

    if failed["google-gemini"]:
        print(f"\nGemini Failed ({len(failed['google-gemini'])}):")
        for m, r in failed["google-gemini"].items():
            print(f"  ✗ {m}: {r}")

    # Save results
    results = {
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "working_models": working,
        "failed_models": failed
    }

    with open("tested_working_models.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\nResults saved to: tested_working_models.json")
    print("=" * 80)

if __name__ == "__main__":
    main()
