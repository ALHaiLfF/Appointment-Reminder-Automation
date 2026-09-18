"""
config.py
=========
Central configuration for the No-Show Reduction Engine.

Everything a client would want to customize when white-labeling this tool
for their own business lives in this one file (plus secrets in `.env`).
Nothing sensitive (passwords, API keys) should ever be hardcoded here —
those are loaded from environment variables via `.env` at runtime.

Why a separate config.py instead of hardcoding values in main.py?
    - Non-developers (or a junior dev doing white-label setup) can edit
      this single file without touching the core sending logic.
    - Keeps business-specific data (brand name, timezone, sending window)
      cleanly separated from the mechanics of "how do I send an email".
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load variables from a local .env file (if present) into the process
# environment. This must happen before we read any os.environ values below.
load_dotenv()


# ---------------------------------------------------------------------------
# Business / branding metadata
# ---------------------------------------------------------------------------
# These values are injected into the email template so the same codebase can
# be re-skinned for any client (a salon, a clinic, a tutoring service, etc.)
# by editing only this section.

BUSINESS_NAME: str = os.getenv("BUSINESS_NAME", "Bright Smile Studio")
BUSINESS_PHONE: str = os.getenv("BUSINESS_PHONE", "+1 (555) 010-2020")
BUSINESS_ADDRESS: str = os.getenv(
    "BUSINESS_ADDRESS", "12 Maple Street, Springfield"
)
# Where a client can go to cancel or reschedule their appointment.
BUSINESS_BOOKING_URL: str = os.getenv(
    "BUSINESS_BOOKING_URL", "https://example.com/manage-booking"
)
BUSINESS_LOGO_URL: str = os.getenv("BUSINESS_LOGO_URL", "")


# ---------------------------------------------------------------------------
# Timezone configuration
# ---------------------------------------------------------------------------
# All appointment timestamps in appointments.csv are treated as "naive" local
# time in this timezone. We attach this timezone to every datetime we parse
# so comparisons against "now" are timezone-aware and unambiguous, even if
# the server running the cron job lives in a different timezone (e.g. a
# Railway/GitHub Actions worker that runs in UTC).
#
# Change this to whatever timezone your business operates in, e.g.:
#   "America/New_York", "Europe/Warsaw", "Europe/London", "UTC"
BUSINESS_TIMEZONE_NAME: str = os.getenv("BUSINESS_TIMEZONE", "Europe/Warsaw")
BUSINESS_TIMEZONE: ZoneInfo = ZoneInfo(BUSINESS_TIMEZONE_NAME)


# ---------------------------------------------------------------------------
# Reminder sending window
# ---------------------------------------------------------------------------
# We want to remind clients "24 hours before" their appointment. Because this
# script is intended to run periodically (e.g. once per hour via cron), we
# don't look for an exact 24h-away match -- we use a window instead. Any
# appointment whose start time falls between REMINDER_WINDOW_MIN_HOURS and
# REMINDER_WINDOW_MAX_HOURS from "now" is considered due for a reminder.
#
# A 23-25 hour window with an hourly cron job guarantees every appointment
# is caught by at least one run, with no duplicates (thanks to the
# `reminder_sent` idempotency flag).
REMINDER_WINDOW_MIN_HOURS: float = float(
    os.getenv("REMINDER_WINDOW_MIN_HOURS", "0")
)
REMINDER_WINDOW_MAX_HOURS: float = float(
    os.getenv("REMINDER_WINDOW_MAX_HOURS", "48")
)


# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
APPOINTMENTS_CSV_PATH: str = os.getenv("APPOINTMENTS_CSV_PATH", "appointments.csv")
EMAIL_TEMPLATE_PATH: str = os.getenv(
    "EMAIL_TEMPLATE_DIR", "templates"
)
EMAIL_TEMPLATE_FILENAME: str = "email_template.html"


# ---------------------------------------------------------------------------
# SMTP / Gmail configuration
# ---------------------------------------------------------------------------
# Gmail requires an "App Password" (not your normal account password) when
# sending via SMTP with 2FA enabled. See README.md for step-by-step setup.
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
# The "From" display name/address shown to the client. Defaults to the SMTP
# username if a dedicated sender address isn't provided.
EMAIL_FROM_ADDRESS: str = os.getenv("EMAIL_FROM_ADDRESS", SMTP_USERNAME)
EMAIL_SUBJECT_TEMPLATE: str = os.getenv(
    "EMAIL_SUBJECT_TEMPLATE", "Reminder: Your appointment at {business_name} is tomorrow"
)


# ---------------------------------------------------------------------------
# Runtime / safety switches
# ---------------------------------------------------------------------------
# DRY_RUN=true renders every email and logs exactly what *would* be sent,
# without opening an SMTP connection or mutating the CSV. This is invaluable
# for demos, portfolio walkthroughs, and safe local testing.
DRY_RUN: bool = os.getenv("DRY_RUN", "false").strip().lower() in {"1", "true", "yes"}
