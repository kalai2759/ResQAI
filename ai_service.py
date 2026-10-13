"""AI assistant. Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set, otherwise demo mode.

The API key is read server-side only and is never sent to the browser.
"""
import logging
import re

import requests

log = logging.getLogger("resqai.ai")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = (
    "You are the ResQAI preparedness assistant for a hackathon prototype. Give short, practical, general "
    "emergency-preparedness guidance (about floods, storms, supplies, contact lists, safety planning), "
    "mainly for readers in India. Rules: you cannot dispatch rescue teams or contact emergency services; "
    "never invent official alerts, shelter locations, phone numbers or road conditions; say clearly that your "
    "answers are general guidance, not verified official information; for anyone in immediate danger, tell them "
    "to call 112 (India) or their local emergency number first; point to official sources (NDMA, IMD, state "
    "disaster authorities) for warnings. Keep answers under 200 words. Do not give medical diagnoses."
)

URGENT_RE = re.compile(r"\b(trapped|drowning|bleeding|unconscious|heart attack|can'?t breathe|"
                       r"rescue me|help me now|life.threatening|in danger right now|on fire)\b", re.I)
URGENT_NOTICE = ("If you or someone near you is in immediate danger, call 112 (India's emergency number) or "
                 "your local emergency service now. ResQAI cannot contact emergency services or send help.")
DISCLAIMER = "General guidance only - not verified official information."

DEMO_ANSWERS = [
    (("heavy rain", "rainfall", "before rain", "prepare before", "monsoon"),
     "Before heavy rainfall:\n- Charge phones and power banks; keep a torch and spare batteries.\n"
     "- Move valuables, documents and electronics to higher shelves; keep documents in a waterproof bag.\n"
     "- Clear drains and balconies near your home; check roof and windows.\n"
     "- Store drinking water and non-perishable food for at least 3 days.\n"
     "- Write down emergency numbers and agree a family meeting point.\n"
     "- Follow forecasts from IMD and your state disaster authority."),
    (("warning", "alert", "flood warning", "official"),
     "If an official flood warning is issued:\n- Follow the instructions of local authorities first.\n"
     "- Move to higher ground if told to, and do not wait for water to rise.\n"
     "- Switch off electricity at the mains if water may enter the house, and do not touch wet electrical items.\n"
     "- Never walk, swim or drive through flood water - it can be deeper and faster than it looks.\n"
     "- Take your emergency kit, medicines and documents. Check on neighbours who may need help.\n"
     "Check official channels (NDMA SACHET, IMD, your state authority) for the actual warning."),
    (("supplies", "kit", "household", "essentials"),
     "Household emergency kit ideas:\n- Drinking water (about 3 litres per person per day) and dry food for 3 days.\n"
     "- First-aid kit and any regular medicines.\n- Torch, spare batteries, power bank, whistle.\n"
     "- Copies of ID and key documents in a waterproof bag.\n- Cash in small notes, basic toiletries, warm clothing.\n"
     "- Items for infants, elderly family members or pets if relevant."),
    (("contact list", "contacts", "emergency contact", "phone numbers"),
     "How to prepare an emergency contact list:\n- Include 112, local police, fire, ambulance (108 in many states) and your state helpline.\n"
     "- Add two family contacts in your city and one outside your region.\n- Add your doctor, workplace/school and building caretaker.\n"
     "- Keep it on paper as well as in your phone, and share it with your household.\n- Review it every six months."),
    (("cyclone", "storm", "wind"),
     "For a cyclone or storm:\n- Stay updated through IMD and local authorities.\n- Secure loose objects outside; stay indoors away from windows.\n"
     "- Keep your emergency kit ready and phones charged.\n- Follow evacuation orders promptly if they are issued."),
]
DEMO_DEFAULT = ("This demo assistant only has a few preset topics: preparing for heavy rain, what to do after an "
                "official flood warning, household emergency supplies, and building an emergency contact list. "
                "Try one of the suggested questions, or configure an AI API key for open-ended answers.")


def ai_configured(config):
    return bool(config.get("ANTHROPIC_API_KEY"))


def demo_reply(message):
    text = message.lower()
    for keys, answer in DEMO_ANSWERS:
        if any(k in text for k in keys):
            return answer
    return DEMO_DEFAULT


def clean_history(raw, max_items, max_chars):
    """Keep only well-formed {role, content} items from the browser, and trim them."""
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw[-max_items:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") \
                and isinstance(item.get("content"), str) and item["content"].strip():
            out.append({"role": item["role"], "content": item["content"].strip()[:max_chars * 2]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def get_reply(message, history, config):
    """Return a dict: reply, mode ('live' | 'demo'), notice, urgent_notice (optional), ok."""
    urgent = URGENT_NOTICE if URGENT_RE.search(message) else None
    result = {"ok": True, "disclaimer": DISCLAIMER, "urgent_notice": urgent}

    if not ai_configured(config):
        result.update(mode="demo", reply=demo_reply(message),
                      notice="Demo mode: predefined answers, not generated by an AI model (no API key configured).")
        return result

    messages = clean_history(history, config["AI_MAX_HISTORY"], config["AI_MAX_MESSAGE_CHARS"])
    messages.append({"role": "user", "content": message})
    try:
        resp = requests.post(
            API_URL, timeout=config["AI_TIMEOUT"],
            headers={"x-api-key": config["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config["AI_MODEL"], "max_tokens": 600, "system": SYSTEM_PROMPT, "messages": messages})
        if resp.status_code == 429:
            raise RuntimeError("The AI provider is rate limiting requests.")
        if resp.status_code != 200:
            raise RuntimeError(f"The AI provider returned HTTP {resp.status_code}.")
        body = resp.json()
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text").strip()
        if not text:
            raise RuntimeError("The AI provider returned an empty answer.")
        result.update(mode="live", reply=text, notice="Generated by an AI model. Check official sources.")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        log.warning("AI request failed: %s", type(exc).__name__)  # never log the key or message text
        result.update(mode="demo", reply=demo_reply(message),
                      notice="The AI service is unavailable right now, so this is a predefined demo answer.")
    return result
