import unittest
from unittest import mock

import requests

import helpers  # noqa: F401  (sets up sys.path)
from services import ai_service, weather_service

KEYLESS = {"ANTHROPIC_API_KEY": "", "AI_MODEL": "m", "AI_TIMEOUT": (1, 1), "AI_MAX_HISTORY": 8, "AI_MAX_MESSAGE_CHARS": 500}
KEYED = dict(KEYLESS, ANTHROPIC_API_KEY="sk-test-fake-key-for-unit-tests")


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("bad json")
        return self._body


class AIServiceTests(unittest.TestCase):
    def test_demo_mode_without_key(self):
        with mock.patch("services.ai_service.requests.post") as post:
            out = ai_service.get_reply("What emergency supplies should a household consider?", [], KEYLESS)
        post.assert_not_called()
        self.assertEqual(out["mode"], "demo")
        self.assertIn("kit", out["reply"].lower())

    def test_demo_default_answer(self):
        out = ai_service.get_reply("tell me a joke", [], KEYLESS)
        self.assertEqual(out["mode"], "demo")
        self.assertIn("preset topics", out["reply"])

    def test_all_suggested_questions_have_specific_demo_answers(self):
        for q in ("What should I prepare before heavy rainfall?",
                  "What should I do if an official flood warning is issued?",
                  "What emergency supplies should a household consider?",
                  "How can I prepare an emergency contact list?"):
            self.assertNotEqual(ai_service.demo_reply(q), ai_service.DEMO_DEFAULT, q)

    def test_live_mode_success(self):
        body = {"content": [{"type": "text", "text": "Stay safe."}]}
        with mock.patch("services.ai_service.requests.post", return_value=FakeResp(200, body)) as post:
            out = ai_service.get_reply("hello", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}], KEYED)
        self.assertEqual(out["mode"], "live")
        self.assertEqual(out["reply"], "Stay safe.")
        kwargs = post.call_args.kwargs
        self.assertIn("timeout", kwargs)
        self.assertEqual(kwargs["headers"]["x-api-key"], KEYED["ANTHROPIC_API_KEY"])
        self.assertEqual(kwargs["json"]["messages"][-1], {"role": "user", "content": "hello"})
        self.assertIn("cannot dispatch", kwargs["json"]["system"])

    def test_live_failures_fall_back_to_labelled_demo(self):
        failures = [FakeResp(500, {}), FakeResp(429, {}), FakeResp(200, None), FakeResp(200, {"content": []}),
                    requests.Timeout("slow"), requests.ConnectionError("down")]
        for f in failures:
            kw = {"side_effect": f} if isinstance(f, Exception) else {"return_value": f}
            with mock.patch("services.ai_service.requests.post", **kw):
                out = ai_service.get_reply("heavy rainfall tips", [], KEYED)
            self.assertEqual(out["mode"], "demo")
            self.assertIn("unavailable", out["notice"])

    def test_urgent_detection(self):
        out = ai_service.get_reply("help I am trapped", [], KEYLESS)
        self.assertIn("112", out["urgent_notice"])
        self.assertIsNone(ai_service.get_reply("how to pack a kit", [], KEYLESS)["urgent_notice"])

    def test_history_cleaning(self):
        raw = [{"role": "system", "content": "evil"}, {"role": "assistant", "content": "first"},
               {"role": "user", "content": "ok"}, "junk", {"role": "user", "content": 5}]
        self.assertEqual(ai_service.clean_history(raw, 8, 500), [{"role": "user", "content": "ok"}])
        self.assertEqual(ai_service.clean_history("nope", 8, 500), [])


GOOD = {"current": {"time": "2026-10-12T10:00", "temperature_c": 0, "temperature_2m": 29.5, "relative_humidity_2m": 70,
                    "precipitation": 0.2, "wind_speed_10m": 12, "weather_code": 63}}


class WeatherTests(unittest.TestCase):
    def setUp(self):
        weather_service.clear_cache()

    def call(self, **kw):
        return weather_service.get_weather(13.08, 80.27, "Chennai", 2, 600)

    def test_success_has_source_and_time(self):
        with mock.patch("services.weather_service.requests.get", return_value=FakeResp(200, GOOD)):
            out = self.call()
        self.assertTrue(out["available"])
        self.assertEqual(out["condition"], "Rain")
        self.assertEqual(out["temperature_c"], 29.5)
        self.assertIn("Open-Meteo", out["source"])
        self.assertTrue(out["retrieved_at"])

    def test_caching(self):
        with mock.patch("services.weather_service.requests.get", return_value=FakeResp(200, GOOD)) as g:
            self.call(); self.call()
        self.assertEqual(g.call_count, 1)

    def test_failures_return_unavailable_without_fake_data(self):
        cases = [requests.Timeout("t"), requests.ConnectionError("c"), FakeResp(500, {}), FakeResp(429, {}),
                 FakeResp(200, None), FakeResp(200, {}), FakeResp(200, {"current": {"temperature_2m": "hot"}})]
        for case in cases:
            weather_service.clear_cache()
            kw = {"side_effect": case} if isinstance(case, Exception) else {"return_value": case}
            with mock.patch("services.weather_service.requests.get", **kw):
                out = self.call()
            self.assertFalse(out["available"], case)
            self.assertNotIn("temperature_c", out)
            self.assertTrue(out["message"])
            self.assertTrue(out["retrieved_at"])


if __name__ == "__main__":
    unittest.main()
