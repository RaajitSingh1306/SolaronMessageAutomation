import logging
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from contextlib import asynccontextmanager

from config import Config
from routes import (
    contacts_router,
    crm_router,
    diagnostics_router,
    fetch_router,
    plants_router,
    report_router,
    send_router,
    upload_router,
)
from services.scheduler import hydrate_state_from_cache, scheduler

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

Config.init_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Validate configuration
    warnings = Config.validate()
    for w in warnings:
        logger.warning("CONFIG WARNING: %s", w)

    # 1. Initialize Operational Database
    from database import init_db
    init_db()

    # 2. Initialize CRM Database and auto-seed directory if empty
    try:
        from crm.db import init_crm_db
        from crm.queue_manager import seed_customers_from_phone_cache
        init_crm_db()
        seed_customers_from_phone_cache()
        logger.info("CRM Database initialized and verified.")
    except Exception as e:
        logger.warning("CRM initialization note: %s", e)
    
    # 3. Start background automation scheduler
    if Config.AUTO_SYNC_ENABLED:
        try:
            scheduler.start()
        except Exception as e:
            logger.warning("Scheduler startup note: %s", e)

    # 2. Non-blocking state hydration in background thread so server starts instantly (< 0.2s)
    if Config.AUTO_LOAD_ON_STARTUP:
        import threading

        def _bg_hydrate():
            try:
                hydrated = hydrate_state_from_cache()
                if hydrated:
                    logger.info("Fleet data loaded successfully in background.")
            except Exception as e:
                logger.warning("Startup cache hydration note: %s", e)

        threading.Thread(target=_bg_hydrate, daemon=True, name="StartupHydrator").start()

    yield

    # Shutdown
    try:
        scheduler.stop()
    except Exception:
        pass


app = FastAPI(title="Solaron Messenger", lifespan=lifespan)

API_KEY = os.getenv("API_KEY")


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=Config.STATIC_FOLDER), name="static")
templates = Jinja2Templates(directory=Config.TEMPLATES_FOLDER)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(fetch_router)
app.include_router(plants_router)
app.include_router(report_router)
app.include_router(send_router)
app.include_router(upload_router)
app.include_router(diagnostics_router)
app.include_router(contacts_router)
app.include_router(crm_router)



@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"API_KEY": API_KEY},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_server(host: str = "127.0.0.1", port: int = 5000):
    """Run uvicorn server passing the app instance directly."""
    print("\n" + "=" * 60)
    print("  [SOLARON MESSAGING DASHBOARD]")
    print(f"  --> Dashboard URL: http://{host}:{port}")
    print("=" * 60 + "\n")
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    run_server()
