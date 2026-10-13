# ResQAI — AI-Powered Disaster Response Platform
**Smarter Response. Safer Lives.**

> ⚠️ **Honest status:** ResQAI is a student **hackathon prototype**. It is **not** an official emergency service. It cannot dispatch rescue teams, cannot contact emergency services, and does not issue official alerts. Records marked **DEMO DATA** are fictional. In an emergency in India, call **112**.

---

## 1. Problem statement
During floods and storms, people struggle to find reliable preparedness information in one place, local problems (flooded roads, damaged structures) are reported informally and are hard to see together, and it is not always clear which information is official and which is only a rumour.

## 2. Proposed solution
A simple web platform where community members can **learn how to prepare**, **report local incidents**, **see reports on a map**, **find official helplines and resources**, and **ask a preparedness assistant** – while the interface always makes clear what is *unverified*, what is *demo data*, and what is *official*.

## 3. Objectives
- Make preparedness information easy to reach.
- Let people report incidents and look them up by ID.
- Show reports on a map and dashboard with filters.
- Let a signed-in reviewer verify, resolve or reject reports (nothing is "verified" automatically).
- Be honest: label demo data, never fabricate alerts or weather.

## 4. Target users
Students, community members, volunteers, and disaster-response organisations.

## 5. Features and their honest status

| Feature | Status |
|---|---|
| Home, About pages | ✅ Fully implemented and locally tested |
| Incident reporting form (validation, unique ID, confirmation, lookup by ID) | ✅ Fully implemented and locally tested |
| Dashboard (counts, filters, status bars, category chart) | ✅ Implemented and tested. *Chart.js loads from a CDN; if it can't load, a table with the same numbers is shown* |
| Disaster Map (Leaflet + OpenStreetMap, filters, legend, list view, resources) | ⚠️ Implemented. Data, filters, list view and missing-coordinate handling **tested**. Map tiles and Leaflet come from the internet (CDN/OSM) and **could not be tested in the build sandbox (no internet)** |
| Emergency resources directory (search, filter, sources) | ✅ Implemented and tested. ⚠️ Numbers are publicly listed ones **not independently verified** in this build (page says so) |
| Admin: login/logout, view, filter, change status, delete | ✅ Fully implemented and locally tested |
| AI assistant – **demo mode** (no key) | ✅ Demo-only (predefined answers, clearly labelled) – tested |
| AI assistant – **live mode** (Anthropic API) | ⚠️ Implemented but **depends on your API key**. Tested only with mocked responses, **never against the real API** |
| Weather panel (Open-Meteo, no key needed) | ⚠️ Implemented but **depends on internet**. Tested with mocked success/failure. Never saw a real live response in the build sandbox |
| Official alerts feed | ❌ **Not implemented.** The page links to IMD, NDMA SACHET and TNSDMA instead |
| Editing the *text* of a report | ❌ Not implemented (admins can change status/notes or delete) |
| Shelters/relief centres with real data | ❌ Only a DEMO placeholder – real data needs official sources |
| Replit deployment | ⚠️ Instructions provided; **not tested on Replit** |

## 6. Technology stack
Python 3 + Flask · SQLite · HTML/CSS/JavaScript (no build step) · Leaflet + OpenStreetMap · Chart.js · Open-Meteo (weather) · Anthropic Messages API (optional AI) · gunicorn (deployment).

## 7. Architecture overview
```
Browser  ──►  Flask app (app.py)  ──►  SQLite (database.py)
  │              │  ├─ services/ai_service.py      ─► AI provider (server-side key) or demo answers
  │              │  └─ services/weather_service.py ─► Open-Meteo (cached, with timeouts)
  └─ JS (app.js, map.js, dashboard.js) calls /api/* JSON endpoints
```
- **Templates** (Jinja2) render pages and automatically escape user text.
- **JSON API:** `/api/incidents`, `/api/resources`, `/api/stats`, `/api/weather`, `/api/chat` (POST).
- API keys live only on the server (environment variables).

## 8. Database structure (SQLite)
- **incidents**: id, incident_id (e.g. `RQ-20261012-A1B2C3`), title, category, description, location_name, latitude, longitude, severity, reporter_name*, reporter_contact*, status, admin_notes*, reviewed_by*, is_demo, created_at, updated_at. (*private – never shown publicly)
- **resources**: name, type, description, phone, address, latitude, longitude, source, source_url, last_verified, status_note, is_demo
- **admin_users**: username, password_hash (never the password)
- **meta**: remembers that demo data was already inserted (so restarts don't duplicate it)

Indexes on incident status, category and created_at. Timestamps are UTC ISO-8601.

## 9. Folder structure
```
resqai/
├── app.py              # routes, security, error handling
├── wsgi.py             # entry point for gunicorn
├── config.py           # settings from environment variables
├── database.py         # all SQL (parameterised)
├── validation.py       # input validation
├── seed_data.py        # DEMO incidents + resources/helplines
├── requirements.txt  .env.example  .gitignore
├── services/           # ai_service.py, weather_service.py
├── templates/          # HTML pages (base.html + one per page)
├── static/css|js/      # style.css, app.js, map.js, dashboard.js
├── scripts/init_db.py  # create DB / reset demo data
├── tests/              # test_app.py, test_database.py, test_services.py, browser_check.py (optional)
└── README.md  PROJECT_ABSTRACT.md  PRESENTATION_GUIDE.md  VIVA_QUESTIONS.md
```

## 10. Installation (local)
You need Python 3.10+.
```bash
cd resqai
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env   (then edit .env)
```

## 11. Run locally
```bash
python app.py
```
Open **http://localhost:5000**. The database is created automatically on first run.

**Admin account (first run):** if you set `ADMIN_PASSWORD` in `.env`, that is your password. If not, a random password is printed **once** in the terminal window — copy it then. The username is `ADMIN_USERNAME` (default `admin`). Sign in at `/admin/login` (link in the footer). If you lose the password, delete `instance/resqai.db` and restart (this also deletes all reports).

Optional commands:
```bash
python scripts/init_db.py           # create tables + demo data (safe to repeat)
python scripts/init_db.py --reset   # delete demo records and re-insert them (real reports are kept)
```

## 12. Run the automated tests
```bash
python -m unittest discover -s tests -v
```
(or `pip install pytest` and run `pytest`). Tests use a **temporary database** and never touch yours.
At build time: **75 tests ran, 75 passed, 0 failed** (Python 3.12, Flask 3.1).

Optional real-browser check (needs `pip install playwright && playwright install chromium`):
```bash
python tests/browser_check.py
```
At build time 34 of 34 browser checks passed in headless Chromium (desktop and 375px mobile widths). **Internet was unavailable**, so Leaflet, OpenStreetMap tiles, Chart.js and live weather were *not* exercised – the fallbacks were.

## 13. Replit setup and deployment
> I could not test on Replit from the build environment. Replit's screens change; follow the idea, not the exact button names. Replit hosting may require a paid plan and is not guaranteed to be free or permanent.

1. Create a Replit account → **Create Repl → Import from upload** (or create a Python Repl and drag the project files in).
2. **Secrets** (padlock icon) → add `SECRET_KEY` (long random text), `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `RESQAI_ENV=production`, and optionally `ANTHROPIC_API_KEY`. Do **not** upload a `.env` file.
3. In the Shell: `pip install -r requirements.txt`
4. **Quick test run:** `python app.py` (binds to `0.0.0.0` and uses the `PORT` variable, default 5000).
5. **Deploy:** use Replit's *Deploy* button. Set the run command to:
   ```
   gunicorn wsgi:app --bind 0.0.0.0:${PORT:-5000} --workers 1
   ```
   `--workers 1` keeps the in-memory rate limiter consistent.
6. **Important:** SQLite is a file. Some deployment types have a temporary file system, which would lose reports on redeploy. Check your Replit deployment type, or use a persistent location, via `DATABASE_PATH`.

## 14. Environment variables
| Variable | Needed? | Meaning |
|---|---|---|
| `SECRET_KEY` | Strongly recommended | Signs login sessions. Without it a random key is used and admin sessions reset on restart |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Optional | First-run admin. No password → random one printed once |
| `ANTHROPIC_API_KEY` | Optional | Turns on the live AI assistant. Empty → demo mode |
| `AI_MODEL` | Optional | Model name (default `claude-sonnet-5-5`; change it if your account uses another) |
| `RESQAI_ENV` | Optional | `production` enables secure cookies and disables debug |
| `DATABASE_PATH` | Optional | Where the SQLite file lives |

Weather needs **no key** (Open-Meteo is free for non-commercial use; check their terms before any commercial use). Never put keys in HTML, JavaScript or GitHub.

## 15. Demo mode
- **AI:** with no `ANTHROPIC_API_KEY` the assistant shows a yellow "Demo mode" banner and gives predefined answers (four preparedness topics + a default). Every answer is tagged **DEMO ANSWER**. It is *not* an AI model.
- **Data:** the 7 sample incidents and 3 sample facilities have `[DEMO]` in their names and a **DEMO DATA** badge. Real helplines (112, 108…) are listed separately with sources.
- **Weather:** if Open-Meteo can't be reached you see "Live weather unavailable" – never invented numbers.

## 16. Known limitations
- Reports are not verified automatically; only an admin can mark one Verified.
- No official alert feed; no real shelter data; helpline numbers not independently verified here.
- The rate limiter is in memory (per process) and resets on restart.
- Single admin role; no password-reset, no two-factor authentication, no account lockout beyond rate limiting.
- Reports cannot be edited by the reporter. Contact details are stored as plain text in SQLite (collect only what you need).
- SQLite suits a prototype, not heavy traffic.
- English only. Map needs internet.

## 17. Security considerations
Implemented: server-side validation and length limits · parameterised SQL everywhere · automatic HTML escaping · CSRF tokens on every POST (forms and the chat API) · password hashing (Werkzeug scrypt) · session cookies HttpOnly + SameSite=Lax (+Secure in production) · session reset at login · login/chat/report/weather rate limiting · 32 KB request limit · Content-Security-Policy and other headers · no inline scripts · API key server-side only · admin pages never cached · no debug mode in production · private contact details only visible to admins · database and source files not reachable through `/static`.
Not covered (prototype): HTTPS (provided by the host), audit logging, formal penetration testing, privacy-law compliance for storing contact data.

## 18. Future enhancements
Official alert feeds (e.g. NDMA SACHET CAP), verified shelter data from district authorities, SMS/WhatsApp reporting, photo uploads with moderation, multi-language support (Tamil, Hindi), multiple reviewer roles, PostgreSQL, push notifications, offline-friendly pages.

## 19. Workflow
Report → stored as *Pending Verification* → appears on dashboard/map as **unverified** → admin reviews → *Verified / Rejected* → later *Resolved*. Rejected reports are hidden from public lists and the map.

## 20. Abstract, presentation, viva
See `PROJECT_ABSTRACT.md`, `PRESENTATION_GUIDE.md` (outline + live demo sequence) and `VIVA_QUESTIONS.md`.
