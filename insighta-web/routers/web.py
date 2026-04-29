import os
import secrets
import httpx
from fastapi import APIRouter, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
router = APIRouter()

API_BASE = os.environ.get("BACKEND_URL")
PORTAL_URL = os.environ.get("PORTAL_URL")
API_HEADERS = {"X-API-Version": "1"}


def _api_headers(request: Request) -> dict:
    token = request.cookies.get("access_token")
    h = {**API_HEADERS}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def _get_user(request: Request) -> dict | None:
    """Fetch current user info from backend using cookie token."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{API_BASE}/auth/me",
                headers={"Authorization": f"Bearer {token}", **API_HEADERS},
            )
        if resp.status_code == 200:
            return resp.json().get("data")
    except Exception:
        pass
    return None


async def _try_refresh(request: Request, response: Response) -> bool:
    """Attempt token refresh using refresh_token cookie. Returns True if successful."""
    rt = request.cookies.get("refresh_token")
    if not rt:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{API_BASE}/auth/refresh",
                json={"refresh_token": rt},
            )
        if resp.status_code == 200:
            data = resp.json()
            response.set_cookie("access_token", data["access_token"], httponly=True, samesite="lax", max_age=180)
            response.set_cookie("refresh_token", data["refresh_token"], httponly=True, samesite="lax", max_age=300)
            return True
    except Exception:
        pass
    return False


def _require_auth(func):
    """Decorator: redirect to /login if no valid session."""
    import functools

    @functools.wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return RedirectResponse("/login", status_code=302)
        return await func(request, *args, **kwargs)

    return wrapper


# ── CSRF ──────────────────────────────────────────────────────────────────────

def _generate_csrf() -> str:
    return secrets.token_hex(32)


def _check_csrf(request: Request, token: str) -> bool:
    expected = request.cookies.get("csrf_token")
    return expected and secrets.compare_digest(expected, token)


# ── Login / OAuth ─────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("access_token"):
        return RedirectResponse("/dashboard")
    csrf = _generate_csrf()
    resp = templates.TemplateResponse("auth/login.html", {"request": request})
    resp.set_cookie("csrf_token", csrf, httponly=True, samesite="lax")
    return resp


@router.get("/auth/github")
async def github_login(request: Request):
    """Redirect user to backend GitHub OAuth flow with redirect_to set."""
    redirect_to = f"{PORTAL_URL}/auth/callback"
    return RedirectResponse(
        f"{API_BASE}/auth/github?redirect_to={redirect_to}",
        status_code=302,
    )


@router.get("/auth/callback")
async def auth_callback(request: Request, access_token: str = None, refresh_token: str = None):
    """
    Receive tokens from backend redirect (query params or cookies already set).
    Backend sets HTTP-only cookies on its domain; for same-domain deployments
    cookies flow automatically. For cross-domain we accept query params once.
    """
    resp = RedirectResponse("/dashboard", status_code=302)

    # If backend set tokens as query params (cross-domain fallback — remove in prod)
    at = request.query_params.get("access_token") or access_token
    rt = request.query_params.get("refresh_token") or refresh_token

    if at:
        resp.set_cookie("access_token", at, httponly=True, samesite="lax", max_age=180)
    if rt:
        resp.set_cookie("refresh_token", rt, httponly=True, samesite="lax", max_age=300)

    return resp


@router.post("/logout")
async def logout(request: Request):
    rt = request.cookies.get("refresh_token")
    if rt:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{API_BASE}/auth/logout", json={"refresh_token": rt})
        except Exception:
            pass
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    resp.delete_cookie("csrf_token")
    return resp


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login")

    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = _api_headers(request)
        try:
            profiles_resp = await client.get(f"{API_BASE}/api/profiles?limit=1", headers=headers)
            total = profiles_resp.json().get("total", 0) if profiles_resp.status_code == 200 else 0

            male_resp = await client.get(f"{API_BASE}/api/profiles?gender=male&limit=1", headers=headers)
            male_count = male_resp.json().get("total", 0) if male_resp.status_code == 200 else 0

            female_resp = await client.get(f"{API_BASE}/api/profiles?gender=female&limit=1", headers=headers)
            female_count = female_resp.json().get("total", 0) if female_resp.status_code == 200 else 0

        except Exception:
            total = male_count = female_count = 0

    return templates.TemplateResponse("profiles/dashboard.html", {
        "request": request,
        "total": total,
        "male_count": male_count,
        "female_count": female_count,
    })


# ── Profiles list ─────────────────────────────────────────────────────────────

@router.get("/profiles", response_class=HTMLResponse)
async def profiles_list(
    request: Request,
    page: int = 1,
    limit: int = 20,
    gender: str = None,
    country_id: str = None,
    age_group: str = None,
    sort_by: str = "created_at",
    order: str = "asc",
):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login")

    params = {"page": page, "limit": limit, "sort_by": sort_by, "order": order}
    if gender:
        params["gender"] = gender
    if country_id:
        params["country_id"] = country_id
    if age_group:
        params["age_group"] = age_group

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{API_BASE}/api/profiles",
            params=params,
            headers=_api_headers(request),
        )

    body = resp.json() if resp.status_code == 200 else {}

    return templates.TemplateResponse("profiles/list.html", {
        "request": request,
        "profiles": body.get("data", []),
        "page": body.get("page", page),
        "total_pages": body.get("total_pages", 1),
        "total": body.get("total", 0),
        "links": body.get("links", {}),
        "filters": {"gender": gender, "country_id": country_id, "age_group": age_group, "sort_by": sort_by, "order": order},
    })


# ── Profile detail ────────────────────────────────────────────────────────────

@router.get("/profiles/{profile_id}", response_class=HTMLResponse)
async def profile_detail(request: Request, profile_id: str):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{API_BASE}/api/profiles/{profile_id}",
            headers=_api_headers(request),
        )

    if resp.status_code == 404:
        return templates.TemplateResponse("profiles/404.html", {"request": request}, status_code=404)

    profile = resp.json().get("data", {}) if resp.status_code == 200 else {}
    return templates.TemplateResponse("profiles/detail.html", {
        "request": request,
        "profile": profile,
    })


# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = None, page: int = 1, limit: int = 20):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login")

    results = []
    total = 0
    total_pages = 0
    error = None

    if q:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{API_BASE}/api/profiles/search",
                params={"q": q, "page": page, "limit": limit},
                headers=_api_headers(request),
            )
        if resp.status_code == 200:
            body = resp.json()
            results = body.get("data", [])
            total = body.get("total", 0)
            total_pages = body.get("total_pages", 1)
        else:
            error = resp.json().get("message", "Search failed")

    return templates.TemplateResponse("profiles/search.html", {
        "request": request,
        "q": q or "",
        "results": results,
        "total": total,
        "total_pages": total_pages,
        "page": page,
        "error": error,
    })


# ── Account ───────────────────────────────────────────────────────────────────

@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/login")

    user = await _get_user(request)
    if not user:
        # Token expired - try refresh
        return RedirectResponse("/login")

    return templates.TemplateResponse("auth/account.html", {
        "request": request,
        "user": user,
    })