"""
main.py
=======
No-Show Reduction Engine — automated 24-hour appointment reminder sender.

This script is the single entry point for the whole system. Run it on a
schedule (cron, GitHub Actions, Railway Scheduled Task — see README.md) and
it will:

    1. Load every appointment from `appointments.csv`.
    2. Find appointments starting 23-25 hours from "now" that have not yet
       received a reminder (`reminder_sent == False`).
    3. Render a branded HTML reminder email for each one (Jinja2).
    4. Send it via Gmail SMTP.
    5. Mark the appointment as `reminder_sent = True` in the CSV so it is
       never emailed twice (idempotency).

Design notes for anyone reading this as a portfolio piece:
    - The script is intentionally dependency-light: stdlib `csv`, `smtplib`,
      and `email` do the heavy lifting; Jinja2 and python-dotenv are the
      only third-party packages.
    - All datetimes are timezone-aware (see config.BUSINESS_TIMEZONE) to
      avoid the classic "server runs in UTC, client is in another timezone"
      bug that plagues naive scheduling scripts.
    - The CSV is treated as a tiny "database". In a real production system
      you would likely swap this for a proper DB (Postgres, SQLite) or a
      booking-platform API (Calendly, Square Appointments, etc.) — the
      `load_appointments` / `mark_reminder_sent` functions are the only two
      places that would need to change to do that.
"""

from __future__ import annotations

import csv
import logging
import smtplib
import sys
from dataclasses import dataclass, fields
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
# A clear, timestamped console log is what makes this tool feel
# "production-ready" during a demo: anyone watching the console can see
# exactly what happened and why, without reading the code.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("no_show_reminder")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Appointment:
    """A single row from appointments.csv, parsed into a typed structure.

    Keeping the raw CSV fieldnames as the dataclass attribute names makes
    round-tripping (read -> mutate -> write) trivial and less error-prone.
    """

    appointment_id: str
    client_name: str
    contact_email: str
    appointment_datetime: datetime
    service_name: str
    reminder_sent: bool

    def to_csv_row(self) -> dict:
        """Serialize back to the string format expected by the CSV file."""
        return {
            "appointment_id": self.appointment_id,
            "client_name": self.client_name,
            "contact_email": self.contact_email,
            "appointment_datetime": self.appointment_datetime.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "service_name": self.service_name,
            "reminder_sent": str(self.reminder_sent),
        }


CSV_FIELDNAMES: List[str] = [f.name for f in fields(Appointment)]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def _parse_bool(value: str) -> bool:
    """Parse the CSV's textual BOOLEAN column ('True'/'False', case-insensitive)."""
    return value.strip().lower() in {"true", "1", "yes"}


def load_appointments(csv_path: Path) -> List[Appointment]:
    """Read appointments.csv into a list of typed, timezone-aware Appointment objects.

    Every appointment_datetime is parsed as naive local time and then
    localized to `config.BUSINESS_TIMEZONE`. This means the CSV itself never
    needs to store a UTC offset -- the business simply lists times "as the
    front desk sees them on the wall clock", and the script handles the
    timezone math.
    """
    appointments: List[Appointment] = []

    if not csv_path.exists():
        logger.error("Appointments file not found: %s", csv_path)
        return appointments

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):  # header is row 1
            try:
                naive_dt = datetime.strptime(
                    row["appointment_datetime"].strip(), "%Y-%m-%d %H:%M"
                )
                aware_dt = naive_dt.replace(tzinfo=config.BUSINESS_TIMEZONE)

                appointment = Appointment(
                    appointment_id=row["appointment_id"].strip(),
                    client_name=row["client_name"].strip(),
                    contact_email=row["contact_email"].strip(),
                    appointment_datetime=aware_dt,
                    service_name=row["service_name"].strip(),
                    reminder_sent=_parse_bool(row["reminder_sent"]),
                )
                appointments.append(appointment)
            except (KeyError, ValueError) as exc:
                # A malformed row shouldn't crash the whole batch -- log it
                # and keep going, so one bad row doesn't block everyone
                # else's reminder.
                logger.warning(
                    "Skipping malformed row %d in %s: %s", row_number, csv_path, exc
                )

    return appointments


def save_appointments(csv_path: Path, appointments: List[Appointment]) -> None:
    """Write the full appointment list back to disk.

    We rewrite the whole file rather than patching a single line because
    CSV rows don't have stable byte offsets once you factor in variable
    field widths -- rewriting the full file is simple and, for the small
    row counts this kind of small-business tool deals with, plenty fast.
    """
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for appointment in appointments:
            writer.writerow(appointment.to_csv_row())


# ---------------------------------------------------------------------------
# Reminder window logic
# ---------------------------------------------------------------------------
def is_due_for_reminder(appointment: Appointment, now: datetime) -> bool:
    """True if `appointment` starts within the configured reminder window
    and has not already received a reminder.

    The window (default 23-25 hours from now) exists because this script is
    designed to run periodically rather than at the exact second 24 hours
    before each appointment. Running it hourly with a 2-hour-wide window
    guarantees every appointment is caught exactly once.
    """
    if appointment.reminder_sent:
        return False

    hours_until_appointment = (
        appointment.appointment_datetime - now
    ).total_seconds() / 3600.0

    return (
        config.REMINDER_WINDOW_MIN_HOURS
        <= hours_until_appointment
        <= config.REMINDER_WINDOW_MAX_HOURS
    )


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------
def render_reminder_email(appointment: Appointment) -> str:
    """Render the HTML email body for a single appointment using Jinja2."""
    env = Environment(
        loader=FileSystemLoader(config.EMAIL_TEMPLATE_PATH),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(config.EMAIL_TEMPLATE_FILENAME)

    return template.render(
        appointment_id=appointment.appointment_id,
        client_name=appointment.client_name,
        service_name=appointment.service_name,
        appointment_date=appointment.appointment_datetime.strftime("%A, %B %d, %Y"),
        appointment_time=appointment.appointment_datetime.strftime("%H:%M"),
        business_name=config.BUSINESS_NAME,
        business_phone=config.BUSINESS_PHONE,
        business_address=config.BUSINESS_ADDRESS,
        business_logo_url=config.BUSINESS_LOGO_URL,
        booking_url=config.BUSINESS_BOOKING_URL,
    )


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------
def send_reminder_email(appointment: Appointment, html_body: str) -> None:
    """Send one rendered reminder email via SMTP (Gmail by default).

    Raises:
        smtplib.SMTPException: on any SMTP-level failure (auth, connection,
            recipient refused, etc.) so the caller can log it and move on
            to the next appointment without crashing the whole batch.
    """
    subject = config.EMAIL_SUBJECT_TEMPLATE.format(business_name=config.BUSINESS_NAME)

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.EMAIL_FROM_ADDRESS
    message["To"] = appointment.contact_email
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.sendmail(
            from_addr=config.EMAIL_FROM_ADDRESS,
            to_addrs=[appointment.contact_email],
            msg=message.as_string(),
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run() -> None:
    """Main entry point: find due appointments, email them, mark them sent."""
    logger.info("=" * 70)
    logger.info("No-Show Reduction Engine starting up")
    logger.info(
        "Business: %s | Timezone: %s | Reminder window: %.0f-%.0fh | Dry run: %s",
        config.BUSINESS_NAME,
        config.BUSINESS_TIMEZONE_NAME,
        config.REMINDER_WINDOW_MIN_HOURS,
        config.REMINDER_WINDOW_MAX_HOURS,
        config.DRY_RUN,
    )

    csv_path = Path(config.APPOINTMENTS_CSV_PATH)
    appointments = load_appointments(csv_path)
    now = datetime.now(config.BUSINESS_TIMEZONE)

    logger.info("Loaded %d appointment(s) from %s", len(appointments), csv_path)
    logger.info("Current time (business timezone): %s", now.strftime("%Y-%m-%d %H:%M %Z"))

    due_appointments = [a for a in appointments if is_due_for_reminder(a, now)]
    logger.info(
        "%d appointment(s) due for a reminder (window: %.0f-%.0f hours from now)",
        len(due_appointments),
        config.REMINDER_WINDOW_MIN_HOURS,
        config.REMINDER_WINDOW_MAX_HOURS,
    )

    if not due_appointments:
        logger.info("Nothing to send. Exiting cleanly.")
        return

    sent_count = 0
    failed_count = 0

    for appointment in due_appointments:
        hours_out = (appointment.appointment_datetime - now).total_seconds() / 3600.0
        logger.info(
            "-> Processing %s (%s, %s) | appointment in %.1fh",
            appointment.appointment_id,
            appointment.client_name,
            appointment.contact_email,
            hours_out,
        )

        try:
            html_body = render_reminder_email(appointment)
        except Exception:
            logger.exception(
                "Failed to render email template for %s -- skipping.",
                appointment.appointment_id,
            )
            failed_count += 1
            continue

        if config.DRY_RUN:
            logger.info(
                "   [DRY RUN] Would send reminder to %s for appointment %s -- "
                "no email sent, CSV not modified.",
                appointment.contact_email,
                appointment.appointment_id,
            )
            continue

        try:
            send_reminder_email(appointment, html_body)
        except smtplib.SMTPAuthenticationError:
            logger.error(
                "   SMTP authentication failed. Check SMTP_USERNAME / "
                "SMTP_PASSWORD (a Gmail App Password is required -- see "
                "README.md). Aborting remaining sends this run."
            )
            failed_count += 1
            break
        except smtplib.SMTPException as exc:
            logger.error(
                "   SMTP error while emailing %s for appointment %s: %s",
                appointment.contact_email,
                appointment.appointment_id,
                exc,
            )
            failed_count += 1
            continue
        except OSError as exc:
            # Covers connection-level failures (DNS, timeout, refused, etc.)
            # that smtplib surfaces as plain OSError/socket errors.
            logger.error(
                "   Network error while emailing %s for appointment %s: %s",
                appointment.contact_email,
                appointment.appointment_id,
                exc,
            )
            failed_count += 1
            continue

        # Idempotency: flip the flag the moment the send succeeds so a
        # crash or re-run immediately after never double-sends.
        appointment.reminder_sent = True
        sent_count += 1
        logger.info(
            "   Reminder sent successfully to %s.", appointment.contact_email
        )

    if not config.DRY_RUN:
        save_appointments(csv_path, appointments)
        logger.info("Updated %s with new reminder_sent flags.", csv_path)

    logger.info(
        "Run complete. Sent: %d | Failed: %d | Skipped (not due): %d",
        sent_count,
        failed_count,
        len(appointments) - len(due_appointments),
    )
    logger.info("=" * 70)


if __name__ == "__main__":
    run()
