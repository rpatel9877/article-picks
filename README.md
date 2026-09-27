# Weekly Reading Picks

Automates steps 1 to 3 of the Friday client email:

1. **Monday reminder.** Every Monday at 9 AM the team gets an email with a link to the submission page.
2. **Submission page.** Team members pick their name, paste one or more links, and optionally say why. Links are accepted until **Thursday at 12:00 PM**; anything later rolls into next week automatically.
3. **Thursday report.** Right after the deadline, a Word document is emailed with every link listed next to the person who sent it, and the **likely top 5 in bold** based on his criteria.

Each link is opened and read as soon as it is submitted, so the report is ready the moment the deadline passes.

## How the top 5 are chosen

A link is never suggested if it is behind a paywall, strongly partisan, not about finance, investing, or economics, too technical, or too short. Everything else is scored 1 to 5 by AI on:

| Criterion | Weight |
|---|---|
| Fits our approach and view of the markets | 30% |
| Fresh angle, not widely covered in the mainstream press | 25% |
| About finance, investing, or economics | 20% |
| Right depth (not too technical, not too short) | 15% |
| Non-partisan | 10% |

The AI compares each article to the firm's own description of its worldview and to past Friday emails, both of which are edited on the Settings page. Ties go to links more than one person submitted. The report also includes a short reason for every link and a draft client intro for each top pick.

Paywall checks combine a list of subscription sites (WSJ, FT, Bloomberg, and others), the page's own subscriber-only markers, and "subscribe to continue" wording. Sites that block automated reading are flagged for a manual check instead of being assumed free.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the values
python app.py               # open http://localhost:5000
```

- Submission page: `http://localhost:5000/`
- Admin dashboard: `http://localhost:5000/admin` (password from `ADMIN_PASSWORD`)

To see a sample report without internet access or an API key: `python manage.py demo`. It creates `data/reports/Article-Submissions-<date>.docx` from fictional sample links.

## First-time setup (5 minutes, all in the browser)

Open **Settings** and fill in:

1. **Team members**, one per line: `Name, email`
2. **Send the Thursday report to**: email
3. **Our approach and view of the markets**: a few plain sentences
4. **Past Friday emails**: paste two or three past client emails (recommended; this is what teaches the AI the firm's taste)

## Deploy

The app is a standard Python web app. `render.yaml` sets it up on Render with a small persistent disk for the database; Railway, Azure App Service, or an internal server work the same way.

Set these environment variables: `FIRM_NAME`, `APP_URL` (the public link), `SECRET_KEY`, `ADMIN_PASSWORD`, `ANTHROPIC_API_KEY`, and the `SMTP_*` settings.

Email works with any SMTP account:

| Provider | Host | Port |
|---|---|---|
| Microsoft 365 / Outlook | smtp.office365.com | 587 |
| Gmail / Google Workspace | smtp.gmail.com | 587 (use an app password) |

Run it as a single process (`--workers 1`), as in the `Procfile`. The built-in scheduler checks every 10 minutes whether the reminder or report is due, and records each send so nothing is ever sent twice. If your host puts idle apps to sleep, set `CRON_KEY` and point a free cron service at `https://your-app/tasks/tick?key=YOUR_KEY` every 10 minutes.

## Notebook walkthrough

`walkthrough.ipynb` runs the same pipeline step by step: clean links, read each article, score it, rank the top 5, build the Word doc, and preview the emails. It uses its own `notebook_data/` folder, so it never touches the live app, and it doesn't send email unless you turn that on.

```bash
pip install -r requirements.txt -r requirements-notebook.txt
jupyter lab walkthrough.ipynb
```

Leave `USE_SAMPLE_DATA = True` for an offline demo, or set it to `False` and paste real links into `SUBMISSIONS`.

## Everyday use

**Team:** open the link, choose your name (it's remembered next time), paste links, submit.

**Dashboard:**
- See every link with its score and the current top 5 as submissions come in
- **Download Word report** any time for a preview
- **Email report now** to send it early or resend it
- **Send reminder now** for an extra nudge
- **Remove** a link that shouldn't be considered
- Switch the **Week** menu to look at past weeks

## Cost

Scoring one article with Claude costs roughly one to two cents. At 20 to 40 links a week, that is under $1 a week. Without an API key, the app still works and ranks with basic rules (length, readability, topic keywords).

## Project layout

| File | What it does |
|---|---|
| `app.py` | Web pages: submission form, dashboard, settings |
| `cycle.py` | Weekly deadline logic (Thursday noon, time zone aware) |
| `fetcher.py` | Opens links, extracts article text, detects paywalls |
| `scorer.py` | AI scoring against the criteria, fallback rules, top 5 ranking |
| `report.py` | Builds the Word document |
| `jobs.py` | Monday reminder, Thursday report, background scoring |
| `scheduler.py` | Runs the job check every 10 minutes |
| `mailer.py` | Sends email (saves to `data/outbox` if email isn't set up) |
| `db.py` | SQLite storage and editable settings |
| `manage.py` | Command line: `report`, `reminder`, `tick`, `demo` |
| `walkthrough.ipynb` | Step-by-step notebook version of the pipeline |
| `tests/` | Automated tests: `python -m pytest -q` |

## Possible next steps

- Thursday morning "last call" to people who haven't submitted yet
- Microsoft 365 sign-in instead of a shared password
- Steps 4 and 5: turn Adam's final five and the draft intros into the email template and route it to compliance
