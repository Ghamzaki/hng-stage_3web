import os
import time
import logging
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from routers.web import router as web_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("insighta-web")

_rate_buckets: dict[str, list] = defaultdict(list)

app = FastAPI(title="Insighta Web Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("BACKEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = round((time.time() - start) * 1000, 2)
    logger.info("%s %s | %s | %.2fms", request.method, request.url.path, response.status_code, ms)
    return response


app.include_router(web_router)

import os as _os
if _os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse("/login")
