# Appointment Reminder Automation

**Automated 24-hour appointment reminder system for small service businesses.**

Salons, clinics, tutors, personal trainers, and any business that runs on booked time slots lose real revenue to missed appointments. This project is a small, production-shaped MVP that closes that gap: it watches an appointment list, finds everyone whose visit is coming up in about a day, and sends them a branded reminder email automatically — with zero risk of double-sending.

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![Status](https://img.shields.io/badge/status-MVP-orange)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Table of Contents

- [Overview & Business Value](#overview--business-value)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Getting a Gmail App Password](#getting-a-gmail-app-password)
- [Deployment — Running It 24/7 for Free](#deployment--running-it-247-for-free)
- [Roadmap & Upsell Ideas](#roadmap--upsell-ideas)
- [License](#license)

---

## Overview & Business Value

No-show rates of **10-30%** are common for salons, clinics, and other appointment-based businesses, and a well-timed reminder sent 24 hours in advance is consistently the single highest-leverage fix — it gives the client enough time to actually reschedule instead of just forgetting.

**What this system does:**

- Reads a business's appointment list (a CSV today — easy to swap for a booking-platform API or database later).
- Automatically finds every appointment happening in roughly 24 hours.
- Sends each client a clean, branded HTML email reminder with the appointment details and a link to manage their booking.
- Never sends the same reminder twice, and logs everything it does so the business owner can audit it.

**Why this matters, in numbers:**

| Metric | Example (30 appointments/week, $60 avg ticket) |
|---|---|
| Baseline no-show rate | 20% (6 missed appointments/week) |
| No-show rate with 24h reminders (typical improvement) | 8–12% |
| Appointments recovered per week | ~3 |
| Recovered revenue per year | **~$9,000+** |
| Cost to run this system | Free to a few dollars/month hosting |

**Why this is a solid foundation, not just a script:**

- **Config-driven branding** — the same codebase white-labels for a new client in minutes by editing `config.py` / `.env`.
- **Idempotent by design** — safe to run every hour, forever, without ever spamming a client twice.
- **Timezone-correct** — appointments are always compared in the business's local timezone, regardless of where the server running the job actually lives.
- **Production-style logging** — every decision the script makes is visible in the console.

---

## How It Works

```
appointments.csv ──► load & parse (timezone-aware) ──► filter: due in 23–25h & not yet reminded
                                                              │
                                                              ▼
                                          render HTML email (Jinja2 + business config)
                                                              │
                                                              ▼
                                              send via SMTP (Gmail by default)
                                                              │
                                                              ▼
                                     mark reminder_sent = True ──► rewrite appointments.csv
```

The script is meant to run **periodically** (e.g. hourly via cron), not as a long-running server. Each run:

1. Loads every appointment and parses its timestamp as timezone-aware (see `BUSINESS_TIMEZONE` in `config.py`).
2. Finds appointments starting **23–25 hours** from now that don't already have `reminder_sent = True`. The 2-hour-wide window (instead of an exact 24h check) guarantees an hourly job catches every appointment exactly once.
3. Renders the HTML email with Jinja2, injecting the client's name, service, date/time, and the business's branding.
4. Sends it over SMTP (STARTTLS + login).
5. On a successful send, flips `reminder_sent` to `True` and rewrites the CSV — this is the idempotency guarantee: re-running the script never double-sends.
6. Logs everything — how many were found, who got emailed, what was skipped and why, and any SMTP errors — without letting one failed send crash the whole batch.

---

## Project Structure

```
├── appointments.csv         # The "database" of appointments (swap for a real DB/API later)
├── main.py                  # Core logic: load, filter, render, send, mark as sent
├── config.py                # Business metadata, timezone, sending window, SMTP settings
├── templates/
│   └── email_template.html  # Responsive, dark-themed HTML email (Jinja2)
├── email_visual_preview.html # Standalone preview of the reminder email
├── requirements.txt         # Python dependencies
├── .env.example             # Template for secrets/config (copy to .env)
└── README.md                # You are here
```

---

## Quick Start

**Prerequisites:** Python 3.9+, a Gmail account (or any SMTP provider) to send from.

```bash
# 1. Clone the repo and move into it
git clone https://github.com/ALHaiLfF/Appointment-Reminder-Automation.git
cd Appointment-Reminder-Automation

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your environment
cp .env.example .env
# now edit .env with your SMTP credentials and business details

# 5. (Optional) Safe dry run first — no emails sent, no CSV changes
DRY_RUN=true python main.py

# 6. Run it for real
python main.py
```

The included `appointments.csv` ships with sample data — a few appointments are timed to fall inside the 23–25 hour reminder window relative to *whenever you run it*, so the full pipeline (detect → render → send → mark as sent) is visible end to end immediately after setup. Run the script twice in a row and you'll see those same appointments correctly **skipped** the second time — that's idempotency in action.

---

## Configuration

Everything lives in `config.py`, populated from environment variables (via `.env`). No secrets are ever hardcoded in source.

| Variable | Default | Description |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server address |
| `SMTP_PORT` | `587` | SMTP port (STARTTLS) |
| `SMTP_USERNAME` | — | Sending account's email address |
| `SMTP_PASSWORD` | — | SMTP password (a Gmail **App Password**, not your login password) |
| `EMAIL_FROM_ADDRESS` | `SMTP_USERNAME` | "From" address shown to the client |
| `BUSINESS_NAME` | `Bright Smile Studio` | Shown in the email header and subject |
| `BUSINESS_PHONE` | — | Contact number for cancellations/reschedules |
| `BUSINESS_ADDRESS` | — | Shown as the appointment location |
| `BUSINESS_BOOKING_URL` | — | Link behind the "Manage Appointment" button |
| `BUSINESS_TIMEZONE` | `Europe/Warsaw` | IANA timezone the business operates in |
| `REMINDER_WINDOW_MIN_HOURS` | `23` | Lower bound of the "due for reminder" window |
| `REMINDER_WINDOW_MAX_HOURS` | `25` | Upper bound of the "due for reminder" window |
| `APPOINTMENTS_CSV_PATH` | `appointments.csv` | Path to the appointments file |
| `EMAIL_TEMPLATE_DIR` | `templates` | Folder containing the Jinja2 template |
| `DRY_RUN` | `false` | If `true`, logs what *would* be sent without emailing or touching the CSV |

> **Note on Windows:** if you see a `ZoneInfoNotFoundError`, install the `tzdata` package (`pip install tzdata`) — Windows doesn't ship the IANA timezone database that Python's `zoneinfo` relies on. It's already listed in `requirements.txt`.

---

## Getting a Gmail App Password

Gmail blocks plain-password SMTP login by default. You need an **App Password** — a 16-character code tied to your account instead of your real password.

1. Go to your [Google Account](https://myaccount.google.com/) → **Security**.
2. Make sure **2-Step Verification** is turned **ON** (App Passwords require it).
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
4. Under "Select app," choose **Other (Custom name)** and name it something like `No-Show Reminder Bot`.
5. Click **Generate** — Google shows a 16-character password.
6. Copy it into `.env` as `SMTP_PASSWORD` (spaces are fine either way).
7. Set `SMTP_USERNAME` and `EMAIL_FROM_ADDRESS` to the Gmail address that generated it.

If a Google Workspace admin has disabled App Passwords org-wide, swap in a transactional provider instead (SendGrid, Postmark, Amazon SES all have free tiers and work as a drop-in SMTP replacement — just change `SMTP_HOST` / `SMTP_PORT`).

---

## Deployment — Running It 24/7 for Free

This script only needs to run periodically — it doesn't need a web server.

### Option A — Cron on a Linux VPS / Raspberry Pi

```bash
crontab -e
```

```
0 * * * * cd /path/to/appointment-reminder-automation && /path/to/venv/bin/python main.py >> logs/reminder.log 2>&1
```

### Option B — Railway (Scheduled Task)

1. Push this repo to GitHub and connect it to a new [Railway](https://railway.app/) project.
2. Set the **Start Command** to `python main.py`.
3. Set the service's **Cron Schedule** to `0 * * * *` (hourly).
4. Add your `.env` values under **Variables**.
5. Deploy — Railway's free tier easily covers a job this light.

### Option C — GitHub Actions (fully free, no server needed)

`.github/workflows/reminder.yml`:

```yaml
name: Send Appointment Reminders

on:
  schedule:
    - cron: "0 * * * *"   # every hour, UTC
  workflow_dispatch: {}

jobs:
  send-reminders:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - name: Run reminder engine
        env:
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USERNAME: ${{ secrets.SMTP_USERNAME }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          EMAIL_FROM_ADDRESS: ${{ secrets.EMAIL_FROM_ADDRESS }}
          BUSINESS_NAME: ${{ vars.BUSINESS_NAME }}
          BUSINESS_TIMEZONE: ${{ vars.BUSINESS_TIMEZONE }}
        run: python main.py
      - name: Commit updated appointments.csv
        run: |
          git config user.name "reminder-bot"
          git config user.email "bot@example.com"
          git add appointments.csv
          git diff --cached --quiet || git commit -m "Update reminder_sent flags"
          git push
```

Add secrets under **Settings → Secrets and variables → Actions**.

> Whichever option you pick, the idempotency flag only works if `appointments.csv` persists between runs — either commit it back (as above) or, for real production use, swap it for a database (see Roadmap).

---

## Roadmap & Upsell Ideas

This MVP is built so each upgrade below is a contained add-on, not a rewrite:

- **SMS / WhatsApp reminders (Twilio)** — add a `send_sms_reminder()` alongside `send_reminder_email()`; SMS/WhatsApp is read within minutes and typically converts better than email.
- **Two-way confirmation** — let clients reply "confirm" / "reschedule" via a webhook or a link, turning this from a one-way reminder into active no-show prevention.
- **Google Sheets / booking-platform integration** — swap the CSV for `gspread` or a booking API (Calendly, Square, Acuity, Fresha); only `load_appointments()` / `save_appointments()` need to change.
- **Multi-client SaaS mode** — one database with a `businesses` table (mirroring today's `config.py` per tenant), a small admin dashboard, and one scheduler looping over every client.
- **No-show analytics** — log every send/skip to build a weekly "no-shows prevented" report, which is also the best way to prove the ROI numbers above with a client's real data.

---

## License

MIT — free to use and adapt for client work.
