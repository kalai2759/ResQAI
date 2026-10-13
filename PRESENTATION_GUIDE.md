# Presentation Guide — ResQAI (5–7 minutes)

## Slide outline
1. **Title** — ResQAI: Smarter Response. Safer Lives. Team name.
2. **Problem** — Scattered information in floods; hard to tell verified from unverified.
3. **Solution** — One place to prepare, report, see, find help, ask.
4. **Features** — Report · Map · Dashboard · Resources · Assistant · Admin review.
5. **How it works** — Browser → Flask → SQLite; services for AI and weather (diagram in README).
6. **Honesty & safety by design** — DEMO DATA labels, "unverified" status, no fake alerts, 112 message, key kept on server.
7. **Security** — Validation, CSRF, hashed passwords, rate limits, tests.
8. **Testing** — 75 automated tests + 34 browser checks (say exactly what could not be tested: live AI, live weather, map tiles).
9. **Limitations & future work** — Official alert feeds, verified shelters, multilingual, PostgreSQL.
10. **Thank you / questions.**

## Live demonstration sequence (about 4 minutes)
1. **Home** – point out the "not an official service" bar and the 112 message.
2. **Dashboard** – show counts, the chart, and say "these 7 are DEMO DATA". Apply a filter (Category = Flooding).
3. **Report Incident** – submit a report (title, category, severity, description, location, coordinates). Show the **incident ID** on the confirmation page. Mention contact details stay private.
4. **Dashboard / Map** – the new report appears as **Pending (unverified)**. Click its marker, show the popup, show the legend and the list view.
5. **Admin** – sign in (footer link), open the report, change status to **Verified**, save. Go back to the map: marker colour changes.
6. **AI Assistant** – click a suggested question. Point at the "Demo mode" banner and **DEMO ANSWER** tag. Type "I am trapped" to show the 112 warning.
7. **Resources** – search "ambulance"; show the source and "not verified in this build" notes.
8. **Sign out.**

## Prepare before presenting
- Run `python app.py` first and copy the admin password from the terminal (or set `ADMIN_PASSWORD`).
- Test the internet connection: the map tiles and weather need it. If the internet fails, say so and use the map's list view.
- Delete your practice reports in the admin page if you want a clean demo.

## Say these things honestly
- "The assistant is in demo mode" (unless you configured a key).
- "Numbers are publicly listed and must be verified before real use."
- "This has not been used in a real emergency or by real organisations."
