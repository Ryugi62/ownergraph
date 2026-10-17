import io, json, urllib.error
from ownergraph.adapters.gemini_llm import GeminiLlm


def ok(text):
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    return R(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())


def test_retries_on_429_then_succeeds():
    calls = []
    def opener(req, timeout=0):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError("u", 429, "rate", {}, None)
        return ok(" hi ")
    sleeps = []
    llm = GeminiLlm(key="k", opener=opener, sleep=sleeps.append, min_interval=0)
    assert llm.complete("x") == "hi" and len(calls) == 3 and len(sleeps) == 2


def test_gives_up_after_max_attempts_and_raises():
    def opener(req, timeout=0): raise urllib.error.HTTPError("u", 503, "down", {}, None)
    llm = GeminiLlm(key="k", opener=opener, sleep=lambda s: None, min_interval=0, attempts=3)
    try:
        llm.complete("x")
        assert False
    except urllib.error.HTTPError:
        pass


def test_does_not_retry_on_400():
    n = []
    def opener(req, timeout=0):
        n.append(1); raise urllib.error.HTTPError("u", 400, "bad", {}, None)
    try:
        GeminiLlm(key="k", opener=opener, sleep=lambda s: None, min_interval=0).complete("x")
    except urllib.error.HTTPError:
        pass
    assert len(n) == 1
