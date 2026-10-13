import json
import re
from pathlib import Path
from unittest import mock

import helpers
from helpers import AppTestCase, VALID_REPORT

ROOT = Path(__file__).resolve().parent.parent


class PageTests(AppTestCase):
    def test_01_homepage_loads(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("not an official emergency service", r.get_data(as_text=True))

    def test_homepage_quick_numbers_lead_with_112(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertLess(html.index(">112<"), html.index(">108<"))

    def test_02_dashboard_loads(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("DEMO DATA", r.get_data(as_text=True))

    def test_03_map_page_loads(self):
        self.assertEqual(self.client.get("/map").status_code, 200)

    def test_04_report_form_loads(self):
        html = self.client.get("/report").get_data(as_text=True)
        self.assertIn('name="title"', html)
        self.assertIn('name="csrf_token"', html)

    def test_all_nav_links_work(self):
        html = self.client.get("/").get_data(as_text=True)
        nav = re.search(r'<nav id="site-nav".*?</nav>', html, re.S).group(0)
        links = re.findall(r'href="(/[^"]*)"', nav)
        self.assertGreaterEqual(len(links), 7)
        for link in links:
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_resources_page_filters(self):
        html = self.client.get("/resources?type=Emergency+contact&q=ambulance").get_data(as_text=True)
        self.assertIn("108", html)
        self.assertNotIn("Sample Hospital", html)
        self.assertIn("Not verified in this build", html)

    def test_20_error_pages(self):
        r = self.client.get("/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Page not found", r.get_data(as_text=True))
        r = self.client.get("/api/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"], "Page not found")
        self.assertEqual(self.client.get("/report/not-an-id").status_code, 404)

    def test_500_page_does_not_leak_details(self):
        with mock.patch.object(self.app.db, "stats", side_effect=RuntimeError("secret internals")):
            self.app.config["PROPAGATE_EXCEPTIONS"] = False
            r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret internals", r.get_data(as_text=True))

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertIn("Content-Security-Policy", r.headers)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")


class ReportTests(AppTestCase):
    def test_05_valid_report_submitted_and_confirmed(self):
        r = self.submit_report()
        self.assertEqual(r.status_code, 302)
        conf = self.client.get(r.headers["Location"])
        self.assertEqual(conf.status_code, 200)
        self.assertRegex(conf.get_data(as_text=True), r"RQ-\d{8}-[0-9A-F]{6}")
        self.assertIn("Pending Verification", conf.get_data(as_text=True))

    def test_06_invalid_reports_rejected(self):
        bad_cases = [
            {"title": ""}, {"title": "abc"}, {"category": "Alien invasion"}, {"severity": "Extreme"},
            {"description": "short"}, {"location_name": ""}, {"latitude": "999"}, {"longitude": "-181"},
            {"latitude": "abc"}, {"latitude": "nan"}, {"longitude": ""}, {"title": "x" * 500},
            {"description": "d" * 5000}, {"reporter_contact": "c" * 500},
        ]
        before = len(self.db.list_incidents(public=False))
        for case in bad_cases:
            r = self.submit_report(**case)
            self.assertEqual(r.status_code, 400, case)
        self.assertEqual(len(self.db.list_incidents(public=False)), before)

    def test_07_report_stored_in_sqlite(self):
        self.submit_report(title="Stored in database")
        rows = [i for i in self.db.list_incidents(public=False) if i["title"] == "Stored in database"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Pending Verification")
        self.assertEqual(rows[0]["is_demo"], 0)
        self.assertTrue(rows[0]["created_at"] and rows[0]["updated_at"])

    def test_report_without_coordinates_ok(self):
        r = self.submit_report(latitude="", longitude="")
        self.assertEqual(r.status_code, 302)

    def test_single_coordinate_rejected(self):
        self.assertEqual(self.submit_report(longitude="").status_code, 400)

    def test_08_search_by_incident_id(self):
        loc = self.submit_report().headers["Location"]
        iid = re.search(r"(RQ-\d{8}-[0-9A-F]{6})", loc).group(1)
        r = self.client.get(f"/report/lookup?incident_id={iid.lower()}")
        self.assertEqual(r.status_code, 302)
        self.assertIn(iid, r.headers["Location"])
        self.assertEqual(self.client.get("/report/lookup?incident_id=RQ-20200101-FFFFFF").status_code, 404)
        self.assertEqual(self.client.get("/report/lookup?incident_id=' OR 1=1 --").status_code, 404)

    def test_09_filters_return_expected_results(self):
        self.submit_report(title="Unique zebra flooding", category="Flooding")
        self.submit_report(title="Unique zebra bridge", category="Infrastructure damage")
        html = self.client.get("/dashboard?q=zebra&category=Flooding").get_data(as_text=True)
        self.assertIn("Unique zebra flooding", html)
        self.assertNotIn("Unique zebra bridge", html)
        html = self.client.get("/dashboard?status=Verified").get_data(as_text=True)
        self.assertNotIn("Unique zebra", html)
        html = self.client.get("/dashboard?q=nothingmatchesthis").get_data(as_text=True)
        self.assertIn("No reports match", html)
        self.assertEqual(self.client.get("/dashboard?date_from=garbage&category=%27%3B--").status_code, 200)

    def test_14_user_input_is_escaped(self):
        self.submit_report(title="<script>alert(1)</script> bad", description="<img src=x onerror=alert(1)> text here")
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        iid = self.db.list_incidents(public=False)[0]["incident_id"]
        detail = self.client.get(f"/report/{iid}").get_data(as_text=True)
        self.assertNotIn("<img src=x", detail)

    def test_sql_injection_text_is_harmless(self):
        self.submit_report(title="Robert'); DROP TABLE incidents;-- ok")
        self.assertGreater(len(self.db.list_incidents(public=False)), 1)
        self.assertEqual(self.client.get("/dashboard?q=%27%20OR%201%3D1--").status_code, 200)

    def test_private_contact_not_public(self):
        self.submit_report(reporter_name="PrivateName", reporter_contact="private@secret.test")
        iid = [i for i in self.db.list_incidents(public=False) if i["reporter_name"] == "PrivateName"][0]["incident_id"]
        for path in ("/dashboard", f"/report/{iid}", "/map", "/api/incidents", f"/report/{iid}/confirmation"):
            body = self.client.get(path).get_data(as_text=True)
            self.assertNotIn("private@secret.test", body, path)
            self.assertNotIn("PrivateName", body, path)

    def test_csrf_required_on_report(self):
        r = self.post("/report", VALID_REPORT, token=False)
        self.assertEqual(r.status_code, 400)

    def test_dashboard_updates_after_add_and_delete(self):
        before = self.db.stats()["total"]
        self.submit_report(title="Counting report one")
        self.assertEqual(self.db.stats()["total"], before + 1)
        self.assertIn("Counting report one", self.client.get("/dashboard").get_data(as_text=True))
        iid = [i for i in self.db.list_incidents(public=False) if i["title"] == "Counting report one"][0]["incident_id"]
        self.login()
        self.post(f"/admin/incidents/{iid}/delete")
        self.assertEqual(self.db.stats()["total"], before)
        self.assertNotIn("Counting report one", self.client.get("/dashboard").get_data(as_text=True))


class MapTests(AppTestCase):
    def test_18_missing_coordinates_do_not_crash_map(self):
        self.submit_report(latitude="", longitude="", title="No coordinates here")
        self.assertEqual(self.client.get("/map").status_code, 200)
        data = self.client.get("/api/incidents").get_json()["incidents"]
        self.assertTrue(any(i["latitude"] is None for i in data))

    def test_map_api_hides_rejected_and_private_fields(self):
        data = self.client.get("/api/incidents").get_json()["incidents"]
        self.assertTrue(all(i["status"] != "Rejected" for i in data))
        for i in data:
            self.assertNotIn("reporter_contact", i)
            self.assertNotIn("reporter_name", i)
            self.assertNotIn("admin_notes", i)

    def test_map_api_filters(self):
        data = self.client.get("/api/incidents?category=Flooding&status=Pending+Verification").get_json()["incidents"]
        self.assertTrue(data)
        self.assertTrue(all(i["category"] == "Flooding" and i["status"] == "Pending Verification" for i in data))

    def test_demo_data_labelled(self):
        data = self.client.get("/api/incidents").get_json()["incidents"]
        demo = [i for i in data if i["is_demo"]]
        self.assertTrue(demo)
        self.assertTrue(all("[DEMO]" in i["title"] for i in demo))
        res = self.client.get("/api/resources?map=1").get_json()["resources"]
        self.assertTrue(res and all(r["is_demo"] for r in res))


class AdminTests(AppTestCase):
    def make_incident(self):
        self.submit_report(title="Needs review")
        return [i for i in self.db.list_incidents(public=False) if i["title"] == "Needs review"][0]["incident_id"]

    def test_12_login_and_logout(self):
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        r = self.post("/admin/logout")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_13_invalid_login_rejected(self):
        for user, pw in [(helpers.ADMIN_USER, "wrong"), ("nobody", "x"), ("", ""), ("' OR 1=1 --", "x")]:
            r = self.login(user=user, password=pw)
            self.assertEqual(r.status_code, 401, (user, pw))
            self.assertIn("Incorrect username or password", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_login_requires_csrf(self):
        r = self.post("/admin/login", {"username": helpers.ADMIN_USER, "password": helpers.ADMIN_PASS}, token=False)
        self.assertEqual(r.status_code, 400)

    def test_11_unauthorised_admin_actions_rejected(self):
        iid = self.make_incident()
        for path in ("/admin", f"/admin/incidents/{iid}"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/admin/login", r.headers["Location"])
        r = self.post(f"/admin/incidents/{iid}/status", {"status": "Verified"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/admin/login", r.headers["Location"])
        r = self.post(f"/admin/incidents/{iid}/delete")
        self.assertIn("/admin/login", r.headers["Location"])
        self.assertEqual(self.db.get_incident(iid)["status"], "Pending Verification")

    def test_10_admin_can_update_status(self):
        iid = self.make_incident()
        self.login()
        for status in ("Verified", "Resolved", "Rejected", "Pending Verification"):
            r = self.post(f"/admin/incidents/{iid}/status", {"status": status, "admin_notes": "checked"})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.db.get_incident(iid)["status"], status)
        full = self.db.get_incident(iid, public=False)
        self.assertEqual(full["reviewed_by"], helpers.ADMIN_USER)
        self.assertEqual(full["admin_notes"], "checked")

    def test_admin_invalid_status_rejected(self):
        iid = self.make_incident()
        self.login()
        self.post(f"/admin/incidents/{iid}/status", {"status": "Totally Verified!!"})
        self.assertEqual(self.db.get_incident(iid)["status"], "Pending Verification")

    def test_admin_status_needs_csrf(self):
        iid = self.make_incident()
        self.login()
        r = self.post(f"/admin/incidents/{iid}/status", {"status": "Verified"}, token=False)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.get_incident(iid)["status"], "Pending Verification")

    def test_admin_sees_private_contact(self):
        iid = self.make_incident()
        self.login()
        self.assertIn("asha@example.com", self.client.get(f"/admin/incidents/{iid}").get_data(as_text=True))

    def test_admin_password_is_hashed(self):
        user = self.db.get_admin(helpers.ADMIN_USER)
        self.assertNotIn(helpers.ADMIN_PASS, user["password_hash"])
        self.assertTrue(user["password_hash"].startswith(("scrypt:", "pbkdf2:")))

    def test_session_cookie_flags(self):
        r = self.login()
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_login_rate_limited(self):
        self.app.config["RATELIMIT_ENABLED"] = True
        codes = [self.login(password="bad").status_code for _ in range(10)]
        self.assertIn(429, codes)

    def test_admin_delete(self):
        iid = self.make_incident()
        self.login()
        self.post(f"/admin/incidents/{iid}/delete")
        self.assertIsNone(self.db.get_incident(iid))


class ApiTests(AppTestCase):
    def chat(self, payload, token=True, raw=None):
        headers = {"X-CSRF-Token": self.token() if token else "bad"}
        if raw is not None:
            return self.client.post("/api/chat", data=raw, headers=headers, content_type="application/json")
        return self.client.post("/api/chat", json=payload, headers=headers)

    def test_21_json_formats_and_status_codes(self):
        for path in ("/api/incidents", "/api/resources", "/api/stats"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.mimetype, "application/json")
        self.assertEqual(self.client.get("/healthz").get_json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/chat").status_code, 405)

    def test_15_ai_demo_mode_without_key(self):
        r = self.chat({"message": "What should I prepare before heavy rainfall?"})
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(body["mode"], "demo")
        self.assertIn("Demo mode", body["notice"])
        self.assertIn("torch", body["reply"].lower())
        self.assertIn("not verified official", body["disclaimer"].lower())

    def test_16_missing_ai_credentials_handled(self):
        self.assertEqual(self.app.config["ANTHROPIC_API_KEY"], "")
        page = self.client.get("/assistant").get_data(as_text=True)
        self.assertIn("Demo mode", page)
        self.assertEqual(self.chat({"message": "something unusual"}).status_code, 200)

    def test_chat_validation(self):
        self.assertEqual(self.chat({"message": ""}).status_code, 400)
        self.assertEqual(self.chat({"message": 123}).status_code, 400)
        self.assertEqual(self.chat({"message": "x" * 5000}).status_code, 400)
        self.assertEqual(self.chat(None, raw="not json").status_code, 400)
        self.assertEqual(self.chat({"message": "hi"}, token=False).status_code, 400)

    def test_chat_urgent_message_points_to_112(self):
        body = self.chat({"message": "I am trapped and bleeding"}).get_json()
        self.assertIn("112", body["urgent_notice"])
        self.assertIn("cannot contact emergency services", body["urgent_notice"])

    def test_chat_rate_limited(self):
        self.app.config["RATELIMIT_ENABLED"] = True
        codes = [self.chat({"message": "hello"}).status_code for _ in range(15)]
        self.assertIn(429, codes)

    def test_weather_api_failure_graceful(self):
        import requests
        from services import weather_service
        weather_service.clear_cache()
        with mock.patch("services.weather_service.requests.get", side_effect=requests.ConnectionError("down")):
            r = self.client.get("/api/weather")
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(body["available"])
        self.assertNotIn("temperature_c", body)
        self.assertIn("message", body)

    def test_oversized_request_rejected(self):
        r = self.client.post("/api/chat", data="x" * 100000, content_type="application/json",
                             headers={"X-CSRF-Token": self.token()})
        self.assertEqual(r.status_code, 413)


class StatsTests(AppTestCase):
    def test_19_dashboard_statistics_correct(self):
        base = self.db.stats()
        self.submit_report(category="Flooding")
        self.submit_report(category="Other")
        iid = self.db.list_incidents(public=False)[0]["incident_id"]
        self.db.update_status(iid, "Verified", None, "t")
        s = self.db.stats()
        self.assertEqual(s["total"], base["total"] + 2)
        self.assertEqual(s["verified"], base["verified"] + 1)
        self.assertEqual(s["pending"], base["pending"] + 1)
        self.assertEqual(sum(s["by_status"].values()), s["total"])
        self.assertEqual(sum(s["by_category"].values()), s["total"])
        self.assertEqual(s["demo"], base["demo"])
        self.assertEqual(self.client.get("/api/stats").get_json()["total"], s["total"])


class SecretsTests(AppTestCase):
    def test_22_no_secrets_in_templates_or_js(self):
        files = list((ROOT / "templates").glob("*.html")) + list((ROOT / "static").rglob("*.js"))
        self.assertTrue(files)
        for f in files:
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("ANTHROPIC_API_KEY", text, f.name)
            self.assertNotIn("x-api-key", text.lower(), f.name)
            self.assertIsNone(re.search(r"sk-[A-Za-z0-9_-]{16,}", text), f.name)

    def test_secret_value_never_rendered(self):
        self.app.config["ANTHROPIC_API_KEY"] = "sk-test-SUPERSECRETVALUE1234567890"
        for path in ("/assistant", "/", "/dashboard", "/about"):
            self.assertNotIn("SUPERSECRETVALUE", self.client.get(path).get_data(as_text=True))

    def test_env_files_not_served(self):
        for path in ("/static/../.env", "/.env", "/instance/resqai.db", "/static/../app.py", "/app.py", "/config.py"):
            self.assertIn(self.client.get(path).status_code, (301, 308, 400, 404), path)

    def test_no_real_env_or_db_in_project(self):
        self.assertTrue((ROOT / ".env.example").exists())
        self.assertIn(".env", (ROOT / ".gitignore").read_text())
