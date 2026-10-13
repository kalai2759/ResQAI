"""ResQAI - Flask application."""
import hmac
import logging
import os
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import validation as v
from config import Config
from database import Database
try:
    from services import ai_service
except ImportError:
    import ai_service

try:
    from services import weather_service
except ImportError:
    weather_service = None

log = logging.getLogger("resqai")
DUMMY_HASH = generate_password_hash("not-a-real-password")

CSP = ("default-src 'self'; script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
       "style-src 'self' https://unpkg.com; img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class RateLimiter:
    """Tiny in-memory sliding-window limiter (per process; fine for a prototype)."""

    def __init__(self):
        self.hits = defaultdict(deque)

    def allow(self, key, limit, window):
        now = time.time()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY_IS_RANDOM"] and not test_config:
        log.warning("SECRET_KEY not set: using a random key (admin sessions reset on restart).")
    if app.config.get("ENV") == "production" and not test_config:
        # Hosts such as Render put a proxy in front of the app: trust one hop so
        # request.remote_addr (used by the rate limiter) is the real visitor IP.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db = Database(app.config["DATABASE_PATH"])
    db.init_schema()
    db.seed_demo_data()
    app.db = db
    limiter = RateLimiter()
    app.limiter = limiter
    _bootstrap_admin(app, db)

    # ---------- helpers ----------
    def rate_limit(name, limit, window):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                if app.config["RATELIMIT_ENABLED"] and not limiter.allow(
                        f"{name}:{request.remote_addr}", limit, window):
                    if request.path.startswith("/api/"):
                        return jsonify(error="Too many requests. Please wait a moment."), 429
                    abort(429)
                return fn(*a, **kw)
            return wrapper
        return deco

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("admin_user"):
                flash("Please sign in to continue.", "error")
                return redirect(url_for("admin_login"))
            return fn(*a, **kw)
        return wrapper

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals.update(CATEGORIES=v.CATEGORIES, SEVERITIES=v.SEVERITIES, STATUSES=v.STATUSES,
                                 RESOURCE_TYPES=v.RESOURCE_TYPES)

    @app.context_processor
    def inject():
        return {"admin_user": session.get("admin_user"), "ai_live": ai_service.ai_configured(app.config)}

    # ---------- security hooks ----------
    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(str(sent), expected):
                if request.path.startswith("/api/"):
                    return jsonify(error="Invalid or missing CSRF token. Reload the page and try again."), 400
                return render_template("error.html", code=400, title="Security check failed",
                                       message="Your form session expired or was invalid. Go back, reload the page and try again."), 400

    @app.after_request
    def security_headers(resp):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.path.startswith(("/admin", "/api")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------- public pages ----------
    @app.get("/")
    def index():
        return render_template("index.html", stats=db.stats(),
                               recent=db.list_incidents(limit=4),
                               quick=_quick_numbers(db.list_resources(rtype="Emergency contact")))

    @app.get("/dashboard")
    def dashboard():
        filters = v.parse_filters(request.args)
        return render_template("dashboard.html", stats=db.stats(), incidents=db.list_incidents(filters, limit=100),
                               filters=filters, weather_default=app.config["WEATHER_DEFAULT_NAME"])

    @app.get("/map")
    def map_page():
        return render_template("map.html")

    @app.route("/report", methods=["GET", "POST"])
    @rate_limit("report", 10, 600)
    def report():
        if request.method == "GET":
            return render_template("report.html", form={}, errors={})
        data, errors = v.validate_incident(request.form)
        if errors:
            return render_template("report.html", form=request.form, errors=errors), 400
        try:
            incident_id = db.create_incident(data)
        except sqlite3.Error:
            log.exception("Could not save report")
            return render_template("report.html", form=request.form,
                                   errors={"form": "We could not save your report. Please try again."}), 500
        return redirect(url_for("report_confirmation", incident_id=incident_id))

    @app.get("/report/lookup")
    def report_lookup():
        raw = v.clean_text(request.args.get("incident_id")).upper()
        if v.valid_incident_id(raw) and db.get_incident(raw):
            return redirect(url_for("report_detail", incident_id=raw))
        return render_template("report.html", form={}, errors={},
                               lookup_error="No report found with that ID. IDs look like RQ-20260101-A1B2C3."), 404

    @app.get("/report/<incident_id>")
    def report_detail(incident_id):
        inc = db.get_incident(incident_id) if v.valid_incident_id(incident_id) else None
        if not inc:
            abort(404)
        return render_template("report_detail.html", incident=inc)

    @app.get("/report/<incident_id>/confirmation")
    def report_confirmation(incident_id):
        inc = db.get_incident(incident_id) if v.valid_incident_id(incident_id) else None
        if not inc:
            abort(404)
        return render_template("report_confirm.html", incident=inc)

    @app.get("/assistant")
    def assistant():
        return render_template("ai_assistant.html", max_chars=app.config["AI_MAX_MESSAGE_CHARS"])

    @app.get("/resources")
    def resources():
        rtype = v.clean_text(request.args.get("type"))
        rtype = rtype if rtype in v.RESOURCE_TYPES else None
        q = v.clean_text(request.args.get("q"))[:80] or None
        return render_template("resources.html", resources=db.list_resources(rtype, q), rtype=rtype, q=q or "")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    # ---------- JSON API ----------
    @app.get("/api/incidents")
    def api_incidents():
        return jsonify(incidents=db.list_incidents(v.parse_filters(request.args)))

    @app.get("/api/resources")
    def api_resources():
        return jsonify(resources=db.list_resources(map_only=request.args.get("map") == "1"))

    @app.get("/api/stats")
    def api_stats():
        return jsonify(db.stats())

    @app.get("/api/weather")
@rate_limit("weather", 30, 60)
def api_weather():
    if weather_service is None:
        return jsonify(error="Weather service is temporarily unavailable."), 503

    c = app.config
    return jsonify(weather_service.get_weather(
        c["WEATHER_DEFAULT_LAT"],
        c["WEATHER_DEFAULT_LON"],
        c["WEATHER_DEFAULT_NAME"],
        c["WEATHER_TIMEOUT"],
        c["WEATHER_CACHE_SECONDS"]
    ))

    @app.post("/api/chat")
    @rate_limit("chat", 12, 60)
    def api_chat():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Send a JSON body with a 'message' field."), 400
        message = payload.get("message")
        if not isinstance(message, str) or not v.clean_text(message):
            return jsonify(error="Please type a question first."), 400
        message = v.clean_text(message)
        if len(message) > app.config["AI_MAX_MESSAGE_CHARS"]:
            return jsonify(error=f"Message too long (maximum {app.config['AI_MAX_MESSAGE_CHARS']} characters)."), 400
        history = ai_service.clean_history(payload.get("history"), app.config["AI_MAX_HISTORY"],
                                           app.config["AI_MAX_MESSAGE_CHARS"])
        return jsonify(ai_service.get_reply(message, history, app.config))

    # ---------- admin ----------
    @app.route("/admin/login", methods=["GET", "POST"])
    @rate_limit("login", 8, 300)
    def admin_login():
        if request.method == "GET":
            return render_template("admin_login.html")
        username = v.clean_text(request.form.get("username"))[:60]
        password = request.form.get("password", "")[:200]
        user = db.get_admin(username)
        ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password) and user
        if not ok:
            return render_template("admin_login.html", error="Incorrect username or password."), 401
        session.clear()  # prevents session fixation
        session.permanent = True
        session["admin_user"] = user["username"]
        csrf_token()
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("index"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        filters = v.parse_filters(request.args)
        return render_template("admin_dashboard.html", stats=db.stats(), filters=filters,
                               incidents=db.list_incidents(filters, public=False, limit=200))

    @app.get("/admin/incidents/<incident_id>")
    @admin_required
    def admin_incident(incident_id):
        inc = db.get_incident(incident_id, public=False) if v.valid_incident_id(incident_id) else None
        if not inc:
            abort(404)
        return render_template("admin_incident.html", incident=inc)

    @app.post("/admin/incidents/<incident_id>/status")
    @admin_required
    def admin_set_status(incident_id):
        status = v.clean_text(request.form.get("status"))
        notes = v.clean_text(request.form.get("admin_notes"))[:v.LIMITS["admin_notes"]]
        if status not in v.STATUSES or not v.valid_incident_id(incident_id):
            flash("Choose a valid status.", "error")
        elif db.update_status(incident_id, status, notes, session["admin_user"]):
            flash(f"Status updated to {status}.", "success")
        else:
            abort(404)
        return redirect(url_for("admin_incident", incident_id=incident_id.upper()))

    @app.post("/admin/incidents/<incident_id>/delete")
    @admin_required
    def admin_delete(incident_id):
        if v.valid_incident_id(incident_id) and db.delete_incident(incident_id):
            flash("Report deleted.", "success")
            return redirect(url_for("admin_dashboard"))
        abort(404)

    # ---------- errors ----------
    def _error(code, title, message):
        if request.path.startswith("/api/"):
            return jsonify(error=title), code
        tpl = {404: "404.html", 500: "500.html"}.get(code, "error.html")
        return render_template(tpl, code=code, title=title, message=message), code

    @app.errorhandler(404)
    def e404(_):
        return _error(404, "Page not found", "That page does not exist or has moved.")

    @app.errorhandler(413)
    def e413(_):
        return _error(413, "Request too large", "The data you sent was too large.")

    @app.errorhandler(429)
    def e429(_):
        return _error(429, "Too many requests", "Please wait a few minutes and try again.")

    @app.errorhandler(405)
    def e405(_):
        return _error(405, "Method not allowed", "That action is not supported on this page.")

    @app.errorhandler(sqlite3.Error)
    def edb(exc):
        log.exception("Database error")
        return _error(500, "Something went wrong", "The database had a problem. Please try again.")

    @app.errorhandler(500)
    def e500(_):
        return _error(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    return app


def _quick_numbers(contacts):
    """Show the most important helplines first: 112, 108, 101, 100."""
    order = ["112", "108", "101", "100"]
    picked = [c for n in order for c in contacts if c["phone"] == n]
    return picked[:4]


def _bootstrap_admin(app, db):
    """Create the first admin account if none exists. Never stores a plain-text password."""
    if db.admin_count() > 0:
        return
    username = app.config["ADMIN_USERNAME"]
    password = app.config["ADMIN_PASSWORD"]
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    db.create_admin(username, generate_password_hash(password))
    if generated:
        print("=" * 60 + f"\nFIRST-RUN ADMIN ACCOUNT\n  username: {username}\n  password: {password}\n"
              "This password is shown ONCE and is not stored in plain text.\n"
              "To choose your own, set ADMIN_PASSWORD before the first run.\n" + "=" * 60, flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    create_app().run(host="0.0.0.0", port=port, debug=Config.DEBUG)
