# Viva Questions and Simple Answers — ResQAI

**1. What problem does ResQAI solve?** It puts disaster-preparedness information, incident reports, a map and official helplines in one place, and makes clear what is verified and what is not.

**2. Is it an official emergency service?** No. It is a hackathon prototype. It cannot send help or contact emergency services. People should call 112.

**3. Why Flask?** It is a small Python web framework that is easy for beginners and enough for routes, forms and JSON APIs.

**4. Why SQLite?** It needs no server – the database is one file – so it is perfect for a prototype. For many users I would move to PostgreSQL.

**5. What is the unique incident ID for?** So a reporter can look their report up later. It looks like `RQ-20261012-A1B2C3` (date + random hex), generated with Python's `secrets` module and checked for uniqueness.

**6. What does "Pending Verification" mean?** Nobody has checked the report. Only a signed-in admin can set Verified, Resolved or Rejected.

**7. How do you protect the admin area?** Login with a hashed password, sessions in secure cookies, CSRF tokens on every change, rate-limited login, and a logout button.

**8. What is password hashing?** Storing a one-way scrambled version of the password instead of the password itself, so a stolen database does not reveal passwords.

**9. What is CSRF?** An attack where another website tricks your logged-in browser into sending a request. A secret token in each form (which the attacker can't know) blocks it.

**10. What is SQL injection and how do you prevent it?** Typing SQL code into a form to attack the database. We always pass user input as parameters (`?`), never glue it into SQL text. There is a test for it.

**11. What is XSS and how do you prevent it?** Injecting JavaScript into a page. Flask templates escape text automatically, our JavaScript uses `textContent`, and a Content-Security-Policy blocks inline scripts.

**12. Where is the AI key kept?** Only in a server environment variable. The browser talks to our `/api/chat`; the server talks to the AI provider.

**13. What happens without an AI key?** The assistant runs in demo mode with predefined answers and says so on screen. It does not pretend to be AI.

**14. Is the AI always right?** No. It gives general guidance only and is told not to invent alerts, phone numbers or road conditions. Users are told to check official sources.

**15. How do you get weather?** From the Open-Meteo API with a timeout and a 10-minute cache. If it fails, we show "unavailable" – never made-up numbers.

**16. Does ResQAI show official alerts?** No. That feature is not implemented. We link to IMD, NDMA SACHET and the state authority.

**17. What is DEMO DATA?** Fictional sample records (in Chennai) so the app has something to show. They are labelled and stored with `is_demo = 1`.

**18. How do you avoid duplicate demo records on restart?** A `meta` table remembers that seeding already happened.

**19. How did you test it?** 75 automated tests (pages, forms, validation, admin security, AI demo mode, weather failures, statistics) with a temporary database, plus a real-browser check. Live AI, live weather and map tiles were not tested because the build environment had no internet.

**20. What are the limitations?** No automatic verification, no official alert feed, no real shelter data, in-memory rate limiting, one admin role, SQLite scale.

**21. How would you make it real?** Partner with local authorities for verified data, add official alert feeds, add moderation workflows and roles, use PostgreSQL, run a security review and meet privacy-law requirements.

**22. What is a rate limit?** A cap on how many requests one visitor can make in a time window, to slow down spam and guessing of passwords.

**23. Why is contact information private?** It is personal data. It is only visible to signed-in admins, and optional for reporters.

**24. What would you do if a report is false?** An admin sets it to Rejected; it disappears from the public list and map but stays in the admin view.
