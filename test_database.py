import os
import sqlite3

from helpers import AppTestCase, VALID_REPORT
from database import Database
import validation as v


class DatabaseTests(AppTestCase):
    def test_tables_created_automatically(self):
        with sqlite3.connect(self.db.path) as c:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"incidents", "resources", "admin_users", "meta"} <= names)

    def test_indexes_exist(self):
        with sqlite3.connect(self.db.path) as c:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("idx_incidents_status", names)

    def test_demo_data_not_duplicated_on_restart(self):
        n = len(self.db.list_incidents(public=False))
        self.assertGreater(n, 0)
        from app import create_app
        create_app({"DATABASE_PATH": self.db.path, "TESTING": True, "ADMIN_PASSWORD": "x" * 12})
        create_app({"DATABASE_PATH": self.db.path, "TESTING": True, "ADMIN_PASSWORD": "x" * 12})
        self.assertEqual(len(self.db.list_incidents(public=False)), n)
        self.assertEqual(self.db.admin_count(), 1)

    def test_reset_demo_keeps_real_reports(self):
        self.submit_report(title="Real citizen report")
        self.db.update_status(self.db.list_incidents(public=False)[0]["incident_id"], "Resolved", None, "t")
        demo_before = self.db.stats()["demo"]
        self.db.reset_demo_data()
        self.assertEqual(self.db.stats()["demo"], demo_before)
        titles = [i["title"] for i in self.db.list_incidents(public=False)]
        self.assertIn("Real citizen report", titles)

    def test_incident_ids_unique_and_formatted(self):
        ids = {self.db.create_incident(v.validate_incident(VALID_REPORT)[0]) for _ in range(25)}
        self.assertEqual(len(ids), 25)
        self.assertTrue(all(v.valid_incident_id(i) for i in ids))

    def test_update_changes_timestamp_and_status(self):
        iid = self.db.create_incident(v.validate_incident(VALID_REPORT)[0])
        self.assertTrue(self.db.update_status(iid, "Verified", "ok", "admin"))
        row = self.db.get_incident(iid)
        self.assertEqual(row["status"], "Verified")
        self.assertFalse(self.db.update_status("RQ-20200101-000000", "Verified", None, "a"))
        with self.assertRaises(ValueError):
            self.db.update_status(iid, "Bogus", None, "a")

    def test_public_rows_exclude_private_columns(self):
        iid = self.db.create_incident(v.validate_incident(VALID_REPORT)[0])
        pub = self.db.get_incident(iid)
        self.assertNotIn("reporter_contact", pub)
        self.assertEqual(self.db.get_incident(iid, public=False)["reporter_contact"], "asha@example.com")

    def test_like_wildcards_escaped(self):
        self.assertEqual(self.db.list_incidents({"q": "%"}), [])
        self.assertEqual(self.db.list_incidents({"q": "_"}), [])

    def test_date_filter(self):
        today = self.db.list_incidents(public=False)[0]["created_at"][:10]
        self.assertTrue(self.db.list_incidents({"date_from": today, "date_to": today}))
        self.assertEqual(self.db.list_incidents({"date_to": "2000-01-01"}), [])

    def test_tests_use_separate_database(self):
        from config import Config
        self.assertNotEqual(os.path.abspath(self.db.path), os.path.abspath(Config.DATABASE_PATH))


class ValidationTests(AppTestCase):
    def test_valid_data(self):
        data, errors = v.validate_incident(VALID_REPORT)
        self.assertEqual(errors, {})
        self.assertEqual(data["latitude"], 13.05)

    def test_control_characters_removed(self):
        data, _ = v.validate_incident(dict(VALID_REPORT, title="Hello\x00 world\x07!"))
        self.assertEqual(data["title"], "Hello world!")

    def test_boundaries(self):
        self.assertEqual(v.validate_incident(dict(VALID_REPORT, latitude="90", longitude="180"))[1], {})
        self.assertIn("latitude", v.validate_incident(dict(VALID_REPORT, latitude="90.0001"))[1])
        self.assertIn("longitude", v.validate_incident(dict(VALID_REPORT, longitude="inf"))[1])

    def test_parse_filters_drops_invalid(self):
        f = v.parse_filters({"category": "Nope", "status": "x", "date_from": "13/13/2020", "q": "  hi  "})
        self.assertEqual(f, {"category": None, "status": None, "date_from": None, "date_to": None, "q": "hi"})
