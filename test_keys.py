import os

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "deepseek/deepseek-chat:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


def _get_api_key() -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_openrouter_api_key_here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Configure it in your shell or .env before running test_keys.py."
        )
    return api_key


def run_model_ping_checks(api_key: str) -> None:
    for model in MODELS:
        print(f"Testing model: {model}...")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost:8080",
            "X-Title": "CyberLab App",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Ping!"}],
        }

        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
            print(f"  Status: {response.status_code}")
            if response.status_code >= 400:
                body_preview = response.text[:240].replace("\n", " ")
                print(f"  Error body: {body_preview}")
        except requests.RequestException as exc:
            print(f"  Request failed: {exc}")


if __name__ == "__main__":
    key = _get_api_key()
    run_model_ping_checks(key)
