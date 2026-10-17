"""LlmClient over the Gemini REST API (key from GEMINI_API_KEY). The LLM only words/plans; facts come from graph rows."""
from __future__ import annotations
import json, os, urllib.request


class GeminiLlm:
    def __init__(self, key: str | None = None, model: str = "gemini-2.5-flash-lite", timeout: int = 40):
        self.key = key or os.environ.get("GEMINI_API_KEY")
        self.model, self.timeout = model, timeout
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set")

    def complete(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            j = json.load(r)
        return j["candidates"][0]["content"]["parts"][0]["text"].strip()
