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


def create_app(service) -> FastAPI:
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

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (WEB / "index.html").read_text(encoding="utf-8")

    return app
