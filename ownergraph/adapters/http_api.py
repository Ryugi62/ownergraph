from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from ..application.serialize import answer_to_dict

WEB = Path(__file__).parent / "web"


class AskBody(BaseModel):
    question: str
    summarize: bool = True

    @field_validator("question")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("question must not be blank")
        return v.strip()[:500]


def create_app(service, repo=None) -> FastAPI:
    app = FastAPI(title="OwnerGraph")

    @app.post("/api/ask")
    def ask(body: AskBody):
        if not body.summarize:  # AC-20: deterministic graph path first, LLM wording is a separate, optional call
            real = service.llm
            class _NoLlm:
                def complete(self, p): raise RuntimeError("summary skipped")
            service.llm = _NoLlm()
            try:
                # planning for non-path questions needs the LLM; deterministic routes do not
                return answer_to_dict(service.ask(body.question))
            finally:
                service.llm = real
        return answer_to_dict(service.ask(body.question))

    @app.get("/api/drift")
    def drift():
        """UC-9 governance drift: per OWNERS file, the share of listed approvers who approved anything in the last 90 days."""
        from datetime import timedelta
        from ..domain.health import summarize_drift
        if repo is None:
            return {"error": "no repository configured"}
        since = service.clock.now() - timedelta(days=90)
        s = summarize_drift(repo.owners_listing(), repo.active_approvers(since))
        worst = sorted((f for f in s.files if f.listed), key=lambda f: (f.ratio, -f.listed, f.path))[:15]
        return {"window_days": 90, "owners_files": len(s.files), "unique_approvers": s.unique_approvers,
                "inactive_approvers": s.inactive_approvers, "inactive_share": round(s.inactive_share, 4),
                "worst_files": [{"path": f.path, "listed": f.listed, "active": f.active, "ratio": round(f.ratio, 3)} for f in worst]}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (WEB / "index.html").read_text(encoding="utf-8")

    return app
