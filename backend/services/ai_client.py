"""OpenRouter API Client for CyberLab."""

import httpx
import json
import re
import asyncio
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Model configuration - free tier models
# Based on testing (2026-03-23):
# - minimax-m2.5:free works well for topic extraction (structured JSON)
# - nemotron-3-super:free replaced gpt-oss-120b (hit 429 rate limits)
# - qwen3-coder:free works for validation script review
MODELS = {
    "grinder": "minimax/minimax-m2.5:free",
    "challenge_gen": "nvidia/nemotron-3-super-120b-a12b:free",
    "validator_review": "qwen/qwen3-coder:free",
    "fallback": "meta-llama/llama-3.3-70b-instruct:free",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HTTP_REFERER = "http://localhost:8080"


class OpenRouterClient:
    """Async HTTP client for OpenRouter API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = OPENROUTER_BASE_URL
        self._last_call_time: Optional[datetime] = None
        self._rate_limit_delay = 1.0  # 1 second between calls per spec

    async def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        if self._last_call_time:
            elapsed = (datetime.utcnow() - self._last_call_time).total_seconds()
            if elapsed < self._rate_limit_delay:
                await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_call_time = datetime.utcnow()

    async def call_model(
        self,
        model_key: str,
        system: str,
        user: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Call an AI model via OpenRouter with automatic fallback on rate limit.
        
        If the primary model returns 429 (rate limited), automatically
        retries with the fallback model.
        """
        await self._enforce_rate_limit()

        # Build list of models to try (primary + fallback)
        primary_model = MODELS.get(model_key, MODELS["fallback"])
        fallback_model = MODELS["fallback"]
        models_to_try = [primary_model]
        if fallback_model != primary_model:
            models_to_try.append(fallback_model)

        last_error = None
        for i, model in enumerate(models_to_try):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": HTTP_REFERER,
                        },
                        json={
                            "model": model,
                            "max_tokens": max_tokens,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    
                    # Validate we actually got content back
                    content = data.get("choices", [{}])[0].get("message", {}).get("content")
                    if not content:
                        raise ValueError(f"Model {model} returned empty content. Full response: {data}")
                    
                    return content
            except Exception as e:
                last_error = e
                print(f"[ai_client] Model {model} failed: {e}")
                if "429" in str(e):
                    await asyncio.sleep(3)  # back off before trying fallback
                    continue
                # For non-429 errors, try fallback if available
                if i < len(models_to_try) - 1:
                    continue

        # All models failed — raise so the grinder can catch and log properly
        raise RuntimeError(f"All models failed. Last error: {last_error}")


# Singleton client instance
_client: Optional[OpenRouterClient] = None


def get_client() -> OpenRouterClient:
    """Get or create the OpenRouter client singleton."""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


def parse_json_response(text: str) -> Dict[str, Any]:
    """Strip markdown fences and parse JSON from model response."""
    if not text:
        raise ValueError("Empty response text")
    
    text = text.strip()

    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from response: {text[:200]}...")
