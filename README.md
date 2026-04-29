# Insighta Labs+ — Web Portal

Server-side rendered web portal for the Insighta Labs+ platform. Built with FastAPI + Jinja2.

## Pages

| Route | Description |
|---|---|
| `/login` | GitHub OAuth login page |
| `/dashboard` | Metrics overview (total, male, female counts) |
| `/profiles` | Profile list with filters, sort, and pagination |
| `/profiles/<id>` | Profile detail view |
| `/search` | Natural language search |
| `/account` | Current user info |

## Authentication

- Authentication uses **HTTP-only cookies** — tokens are never accessible via JavaScript
- `access_token` cookie: 3-minute lifetime
- `refresh_token` cookie: 5-minute lifetime
- Token refresh is handled server-side transparently
- All routes check for a valid `access_token` cookie; missing → redirect to `/login`

## CSRF Protection

A `csrf_token` cookie is set on the login page and checked on form submissions (logout). The token uses `secrets.compare_digest` for timing-safe comparison.

## Setup

```bash
git clone https://github.com/your-org/insighta-web
cd insighta-web

pip install -r requirements.txt

cp .env.example .env
# Set BACKEND_URL and PORTAL_URL

uvicorn main:app --reload --port 3000
```

## Environment Variables

| Variable | Description |
|---|---|
| `BACKEND_URL` | URL of the Insighta backend API |
| `PORTAL_URL` | Public URL of this portal (used for OAuth redirects) |

## GitHub OAuth Callback

The portal's OAuth callback URL to register in GitHub: `https://your-backend.vercel.app/auth/github/callback`

The backend handles the OAuth exchange and redirects back to the portal at `/auth/callback` with tokens set as cookies.
