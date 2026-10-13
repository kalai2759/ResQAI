"""Input validation helpers. Everything user-supplied passes through here."""
import math
import re
from datetime import datetime

CATEGORIES = ["Flooding", "Road blockage", "Infrastructure damage", "Severe weather", "Other"]
SEVERITIES = ["Low", "Moderate", "High", "Critical"]
STATUSES = ["Pending Verification", "Verified", "Resolved", "Rejected"]
RESOURCE_TYPES = ["Emergency contact", "Hospital / medical", "Official resource", "Shelter / relief centre"]

LIMITS = {"title": 120, "description": 2000, "location_name": 150,
          "reporter_name": 80, "reporter_contact": 120, "admin_notes": 500}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"^RQ-\d{8}-[0-9A-F]{6}$")


def clean_text(value):
    """Return a stripped string with control characters removed."""
    if value is None:
        return ""
    return _CTRL.sub("", str(value)).strip()


def valid_incident_id(value):
    return bool(_ID.match(clean_text(value).upper()))


def _coord(raw, low, high, label, errors):
    raw = clean_text(raw)
    if raw == "":
        return None
    try:
        num = float(raw)
    except ValueError:
        errors[label] = f"{label.capitalize()} must be a number."
        return None
    if not math.isfinite(num) or not (low <= num <= high):
        errors[label] = f"{label.capitalize()} must be between {low} and {high}."
        return None
    return round(num, 6)


def validate_incident(form):
    """Return (clean_data, errors). errors is empty when the data is valid."""
    errors = {}
    data = {k: clean_text(form.get(k)) for k in
            ("title", "category", "description", "location_name", "severity",
             "reporter_name", "reporter_contact")}

    if len(data["title"]) < 5:
        errors["title"] = "Title must be at least 5 characters."
    if len(data["description"]) < 10:
        errors["description"] = "Description must be at least 10 characters."
    if len(data["location_name"]) < 2:
        errors["location_name"] = "Location name is required."
    if data["category"] not in CATEGORIES:
        errors["category"] = "Choose a category from the list."
    if data["severity"] not in SEVERITIES:
        errors["severity"] = "Choose a severity from the list."
    for field, limit in LIMITS.items():
        if field in data and len(data[field]) > limit:
            errors[field] = f"Maximum {limit} characters."

    data["latitude"] = _coord(form.get("latitude"), -90, 90, "latitude", errors)
    data["longitude"] = _coord(form.get("longitude"), -180, 180, "longitude", errors)
    if "latitude" not in errors and "longitude" not in errors:
        if (data["latitude"] is None) != (data["longitude"] is None):
            errors["latitude"] = "Provide both latitude and longitude, or leave both empty."
    return data, errors


def parse_date(value):
    try:
        return datetime.strptime(clean_text(value), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_filters(args):
    """Turn query-string arguments into safe filter values (invalid ones are dropped)."""
    category = clean_text(args.get("category"))
    status = clean_text(args.get("status"))
    return {
        "category": category if category in CATEGORIES else None,
        "status": status if status in STATUSES else None,
        "date_from": parse_date(args.get("date_from")),
        "date_to": parse_date(args.get("date_to")),
        "q": clean_text(args.get("q"))[:80] or None,
    }
