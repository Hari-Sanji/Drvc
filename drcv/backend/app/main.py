import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .db import Base, SessionLocal, engine, upgrade_schema
from .routers import analysis, auth, cases, misc, public, records, reports, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("drcv")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    upgrade_schema()
    from .models import AuditLog
    from .security import rechain_from
    from .seed import seed_if_empty
    db = SessionLocal()
    try:
        first_unchained = db.query(AuditLog.id).filter(AuditLog.entry_hash.is_(None)).order_by(AuditLog.id).first()
        if first_unchained:
            log.info("Backfilling audit hash chain from entry #%s", first_unchained[0])
            rechain_from(first_unchained[0])
        seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Digital Record Context Verification API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", [])[1:]) or "input"
        msgs.append(f"{loc}: {e.get('msg')}")
    return JSONResponse({"detail": "Invalid input — " + "; ".join(msgs[:3])}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong while processing the request. Please try again."}, status_code=500)


for r in (auth.router, users.router, cases.router, records.router, analysis.router, reports.router, misc.router,
          public.router):
    app.include_router(r)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    raise HTTPException(404, "API endpoint not found.")


# ---- serve the built frontend (single-page app) ----
if config.FRONTEND_DIST.exists():
    assets = config.FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (config.FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and config.FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(config.FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "DRCV API is running. Build the frontend (frontend/ → npm run build) or open /api/docs."}
