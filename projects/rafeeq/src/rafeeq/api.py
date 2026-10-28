from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent import Model, run_agent
from .config import Settings
from .domain import decide, propose, verify
from .intake import application_options, begin_review, my_applications, propose_application, register
from .schemas import Application, Booking, Chat, Decision, Permit, Register, Reply, Verify
from .storage import Store


def create_app(settings: Settings | None = None, model: Model | None = None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.runtime)
    app = FastAPI(title="Rafeeq · Municipal Services", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.store = store
    # Serialize turns and writes in this single-worker educational service.
    lock = asyncio.Lock()
    web = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            origin = request.headers.get("origin")
            if request.headers.get("x-rafeeq-client") != "1" or (origin and origin != str(request.base_url).rstrip("/")):
                return JSONResponse({"detail": "Same-origin client header required."}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(PermissionError)
    async def permission_error(request: Request, exc: PermissionError):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(ValueError)
    async def bad_request(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(TimeoutError)
    async def rate_error(request: Request, exc: TimeoutError):
        return JSONResponse({"detail": str(exc)}, status_code=429)

    def session(request: Request) -> str:
        sid = request.cookies.get("rafeeq_session", "")
        if not sid:
            raise HTTPException(401, "Start a session first.")
        store.session(sid)
        return sid

    def officer(x_officer_token: str = Header(default="")) -> None:
        if not settings.officer_token or not secrets.compare_digest(x_officer_token, settings.officer_token):
            raise HTTPException(403, "Finance officer authorization required.")

    def reviewer(x_reviewer_token: str = Header(default="")) -> None:
        if not settings.reviewer_token or not secrets.compare_digest(x_reviewer_token, settings.reviewer_token):
            raise HTTPException(403, "Licensing reviewer authorization required.")

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")

    # Relative assets also support opening the HTML directly for a visual preview.
    @app.get("/style.css", include_in_schema=False)
    def stylesheet():
        return FileResponse(web / "style.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def javascript():
        return FileResponse(web / "app.js", media_type="text/javascript")

    @app.get("/markdown.js", include_in_schema=False)
    def markdown_script():
        return FileResponse(web / "markdown.js", media_type="text/javascript")

    @app.get("/chat-forms.js", include_in_schema=False)
    def forms_script():
        return FileResponse(web / "chat-forms.js", media_type="text/javascript")

    @app.get("/healthz")
    def health():
        return {"ok": True, "ai_configured": bool(settings.api_key), "model": settings.model,
                "simulation_date": "2026-11-01", "officer_enabled": bool(settings.officer_token),
                "reviewer_enabled": bool(settings.reviewer_token)}

    @app.post("/api/session")
    def new_session(response: Response, request: Request):
        old = request.cookies.get("rafeeq_session")
        if old:
            try:
                store.session(old)
                return {"ok": True}
            except PermissionError:
                pass
        response.set_cookie("rafeeq_session", store.new_session(), httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", max_age=86400)
        return {"ok": True}

    @app.delete("/api/session")
    def clear_session(response: Response, sid: str = Depends(session)):
        with store.connect() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (sid,))
            db.execute("UPDATE actions SET status='cancelled' WHERE session_id=? AND status='pending'", (sid,))
        response.delete_cookie("rafeeq_session")
        return {"ok": True}

    @app.post("/api/verify")
    def verify_identity(req: Verify, sid: str = Depends(session)):
        store.rate_limit(sid)
        verify(store, sid, req)
        return {"ok": True, "expires_in_seconds": 900}

    @app.get("/api/me")
    def me(sid: str = Depends(session)):
        return my_applications(store, sid)

    @app.post("/api/register")
    def register_citizen(req: Register, sid: str = Depends(session)):
        store.rate_limit(sid)
        result = register(store, sid, req)
        store.event(store.trace_session(sid), "synthetic_profile_consent", consent=True)
        return result

    @app.get("/api/application-options")
    def options(sid: str = Depends(session)):
        return application_options()

    @app.post("/api/application-draft")
    async def draft(req: Application, sid: str = Depends(session)):
        store.rate_limit(sid)
        async with lock:
            result = propose_application(store, sid, req)
            store.event(result["action_id"], "application_proposed", status=result["status"])
            return result

    @app.post("/api/inspection-proposal")
    async def inspection_proposal(req: Booking, sid: str = Depends(session)):
        store.rate_limit(sid)
        async with lock:
            return propose(store, sid, "book_inspection", req.model_dump(mode="json"))

    @app.get("/api/reviewer/applications", dependencies=[Depends(reviewer)])
    def review_queue():
        with store.connect() as db:
            return [dict(r) for r in db.execute("SELECT permit_id,type,status,district,info_requested FROM permits"
                                               " WHERE applicant_id LIKE 'DEMO-%' AND status IN ('submitted','needs_info')")]

    @app.post("/api/reviewer/begin-review", dependencies=[Depends(reviewer)])
    async def review(req: Permit):
        async with lock:
            result = begin_review(store, req.permit_id)
            store.event(req.permit_id, "officer_started_review", status=result["status"])
            return result

    @app.post("/api/chat", response_model=Reply)
    async def chat(req: Chat, sid: str = Depends(session)):
        store.rate_limit(sid)
        async with lock:
            return await run_agent(store, sid, req.message, settings, model)

    @app.get("/api/actions")
    def actions(sid: str = Depends(session)):
        import json
        with store.connect() as db:
            rows = [dict(r) for r in db.execute(
                "SELECT id,tool,args,status,expires,result FROM actions WHERE session_id=? ORDER BY rowid DESC LIMIT 10", (sid,))]
        for r in rows:
            r["args"], r["result"] = json.loads(r["args"]), json.loads(r["result"] or "null")
        return rows

    @app.post("/api/actions/{action_id}/decision")
    async def citizen_decision(action_id: str, req: Decision, sid: str = Depends(session)):
        store.rate_limit(sid)
        async with lock:
            result = decide(store, sid, action_id, req.approve)
            store.event(action_id, "citizen_decision", status=result["status"])
            return result

    @app.get("/api/officer/actions", dependencies=[Depends(officer)])
    def officer_actions():
        import json
        with store.connect() as db:
            rows = [dict(r) for r in db.execute(
                "SELECT id,tool,args,status,result FROM actions WHERE status='awaiting_officer'")]
        for r in rows:
            r["args"], r["result"] = json.loads(r["args"]), json.loads(r["result"] or "null")
        return rows

    @app.post("/api/officer/actions/{action_id}/decision", dependencies=[Depends(officer)])
    async def officer_decision(action_id: str, req: Decision):
        async with lock:
            result = decide(store, None, action_id, req.approve, officer=True)
            store.event(action_id, "officer_decision", status=result["status"])
            return result

    return app
