"""SQLite data layer. Every query is parameterised (no string-built SQL with user data)."""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from validation import CATEGORIES, STATUSES

PUBLIC_FIELDS = ("incident_id, title, category, description, location_name, latitude, longitude, "
                 "severity, status, is_demo, created_at, updated_at")

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    location_name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    severity TEXT NOT NULL,
    reporter_name TEXT,
    reporter_contact TEXT,
    status TEXT NOT NULL DEFAULT 'Pending Verification',
    admin_notes TEXT,
    reviewed_by TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at);

CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    phone TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    source TEXT,
    source_url TEXT,
    last_verified TEXT,
    status_note TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _like(text):
    """Escape LIKE wildcards in user search text."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class Database:
    def __init__(self, path):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---------- setup ----------
    def init_schema(self):
        with self.connect() as c:
            c.executescript(SCHEMA)

    def _meta_get(self, c, key):
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def seed_demo_data(self, force=False):
        """Insert demo records once. Safe to call on every start-up."""
        from seed_data import DEMO_INCIDENTS, RESOURCES
        with self.connect() as c:
            if self._meta_get(c, "seeded") == "1" and not force:
                return False
            now = utc_now()
            for row in DEMO_INCIDENTS:
                c.execute(
                    "INSERT INTO incidents (incident_id, title, category, description, location_name,"
                    " latitude, longitude, severity, status, is_demo, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
                    (self._new_id(c), row["title"], row["category"], row["description"],
                     row["location_name"], row["latitude"], row["longitude"], row["severity"],
                     row["status"], now, now))
            for r in RESOURCES:
                c.execute(
                    "INSERT INTO resources (name, type, description, phone, address, latitude, longitude,"
                    " source, source_url, last_verified, status_note, is_demo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["name"], r["type"], r.get("description"), r.get("phone"), r.get("address"),
                     r.get("latitude"), r.get("longitude"), r.get("source"), r.get("source_url"),
                     r.get("last_verified"), r.get("status_note"), 1 if r.get("is_demo") else 0))
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded', '1')")
            return True

    def reset_demo_data(self):
        """Remove demo incidents and resources, then insert them again. Real reports are kept."""
        with self.connect() as c:
            c.execute("DELETE FROM incidents WHERE is_demo = 1")
            c.execute("DELETE FROM resources")
            c.execute("DELETE FROM meta WHERE key = 'seeded'")
        return self.seed_demo_data(force=True)

    # ---------- incidents ----------
    def _new_id(self, c):
        for _ in range(10):
            candidate = f"RQ-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"
            if not c.execute("SELECT 1 FROM incidents WHERE incident_id = ?", (candidate,)).fetchone():
                return candidate
        raise RuntimeError("Could not generate a unique incident ID")

    def create_incident(self, data):
        now = utc_now()
        with self.connect() as c:
            incident_id = self._new_id(c)
            c.execute(
                "INSERT INTO incidents (incident_id, title, category, description, location_name, latitude,"
                " longitude, severity, reporter_name, reporter_contact, status, is_demo, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,'Pending Verification',0,?,?)",
                (incident_id, data["title"], data["category"], data["description"], data["location_name"],
                 data["latitude"], data["longitude"], data["severity"], data["reporter_name"] or None,
                 data["reporter_contact"] or None, now, now))
        return incident_id

    def get_incident(self, incident_id, public=True):
        cols = PUBLIC_FIELDS if public else "*"
        with self.connect() as c:
            row = c.execute(f"SELECT {cols} FROM incidents WHERE incident_id = ?",  # cols is a constant
                            (incident_id.upper(),)).fetchone()
        return dict(row) if row else None

    def list_incidents(self, filters=None, public=True, limit=300):
        filters = filters or {}
        cols = PUBLIC_FIELDS if public else "*"
        where, params = [], []
        if public:
            where.append("status != 'Rejected'")
        if filters.get("category"):
            where.append("category = ?"); params.append(filters["category"])
        if filters.get("status"):
            where.append("status = ?"); params.append(filters["status"])
        if filters.get("date_from"):
            where.append("substr(created_at, 1, 10) >= ?"); params.append(filters["date_from"])
        if filters.get("date_to"):
            where.append("substr(created_at, 1, 10) <= ?"); params.append(filters["date_to"])
        if filters.get("q"):
            like = _like(filters["q"])
            where.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                         "OR location_name LIKE ? ESCAPE '\\' OR incident_id LIKE ? ESCAPE '\\')")
            params += [like] * 4
        sql = f"SELECT {cols} FROM incidents"
        if where:
            sql += " WHERE " + " AND ".join(where)  # fragments above are constants
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def update_status(self, incident_id, status, notes, admin_name):
        if status not in STATUSES:
            raise ValueError("Invalid status")
        with self.connect() as c:
            cur = c.execute(
                "UPDATE incidents SET status = ?, admin_notes = ?, reviewed_by = ?, updated_at = ? "
                "WHERE incident_id = ?", (status, notes or None, admin_name, utc_now(), incident_id.upper()))
            return cur.rowcount > 0

    def delete_incident(self, incident_id):
        with self.connect() as c:
            return c.execute("DELETE FROM incidents WHERE incident_id = ?", (incident_id.upper(),)).rowcount > 0

    def stats(self):
        with self.connect() as c:
            total = c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            demo = c.execute("SELECT COUNT(*) FROM incidents WHERE is_demo = 1").fetchone()[0]
            by_status = {s: 0 for s in STATUSES}
            for r in c.execute("SELECT status, COUNT(*) n FROM incidents GROUP BY status"):
                by_status[r["status"]] = r["n"]
            by_cat = {k: 0 for k in CATEGORIES}
            for r in c.execute("SELECT category, COUNT(*) n FROM incidents GROUP BY category"):
                by_cat[r["category"]] = r["n"]
        return {"total": total, "demo": demo, "pending": by_status["Pending Verification"],
                "verified": by_status["Verified"], "resolved": by_status["Resolved"],
                "rejected": by_status["Rejected"], "by_status": by_status, "by_category": by_cat}

    # ---------- resources ----------
    def list_resources(self, rtype=None, q=None, map_only=False):
        where, params = [], []
        if rtype:
            where.append("type = ?"); params.append(rtype)
        if q:
            like = _like(q)
            where.append("(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\')")
            params += [like] * 3
        if map_only:
            where.append("latitude IS NOT NULL AND longitude IS NOT NULL")
        sql = "SELECT * FROM resources"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY is_demo, type, name"
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    # ---------- admin users ----------
    def admin_count(self):
        with self.connect() as c:
            return c.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]

    def create_admin(self, username, password_hash):
        with self.connect() as c:
            c.execute("INSERT INTO admin_users (username, password_hash, created_at) VALUES (?,?,?)",
                      (username, password_hash, utc_now()))

    def get_admin(self, username):
        with self.connect() as c:
            row = c.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
