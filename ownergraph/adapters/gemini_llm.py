"""LlmClient over the Gemini REST API (key from GEMINI_API_KEY). The LLM only words/plans; facts come from graph rows.
Free-tier friendly: spaces calls (`min_interval`) and retries 429/5xx with back-off."""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request


class GeminiLlm:
    def __init__(self, key=None, model="gemini-3.1-flash-lite", timeout=60, opener=urllib.request.urlopen,
                 sleep=time.sleep, min_interval=0.0, attempts=6):
        self.key = key or os.environ.get("GEMINI_API_KEY")
        self.model, self.timeout, self.opener, self.sleep = model, timeout, opener, sleep
        self.min_interval, self.attempts, self._last = min_interval, attempts, 0.0
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set")

    def complete(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.key}"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}).encode()
        for attempt in range(self.attempts):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            try:
                req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
                with self.opener(req, timeout=self.timeout) as r:
                    j = json.load(r)
                return j["candidates"][0]["content"]["parts"][0]["text"].strip()
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.attempts - 1:
                    raise
                self.sleep(min(60, 4 * 2 ** attempt))
        raise RuntimeError("unreachable")
