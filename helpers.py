"""Shared test helpers. Every test gets its own temporary database - the real one is never touched."""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app  # noqa: E402

ADMIN_USER, ADMIN_PASS = "tester", "correct-horse-battery-1"

VALID_REPORT = {
    "title": "Water over the road", "category": "Flooding", "severity": "High",
    "description": "Knee-deep water covering the whole road near the bus stop.",
    "location_name": "Test Street, Chennai", "latitude": "13.05", "longitude": "80.25",
    "reporter_name": "Asha", "reporter_contact": "asha@example.com",
}


class AppTestCase(unittest.TestCase):
    config_overrides = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        cfg = {"DATABASE_PATH": os.path.join(self.tmp, "test.db"), "TESTING": True, "SECRET_KEY": "test-secret",
               "SECRET_KEY_IS_RANDOM": False, "ADMIN_USERNAME": ADMIN_USER, "ADMIN_PASSWORD": ADMIN_PASS,
               "ANTHROPIC_API_KEY": "", "RATELIMIT_ENABLED": False}
        cfg.update(self.config_overrides)
        self.app = create_app(cfg)
        self.db = self.app.db
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def token(self, client=None, path="/report"):
        client = client or self.client
        html = client.get(path).get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)

    def post(self, path, data=None, client=None, token=True, **kw):
        client = client or self.client
        data = dict(data or {})
        if token:
            data["csrf_token"] = self.token(client)
        return client.post(path, data=data, **kw)

    def login(self, client=None, user=ADMIN_USER, password=ADMIN_PASS):
        return self.post("/admin/login", {"username": user, "password": password}, client=client)

    def submit_report(self, **overrides):
        data = dict(VALID_REPORT, **overrides)
        return self.post("/report", data)
