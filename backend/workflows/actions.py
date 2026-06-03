"""
Action executors for the workflow engine.
Each action type maps to a function that performs the actual work.

Notification delivery channels (in priority order):
  1. Email via Resend  — if RESEND_API_KEY is set in .env
  2. Email via SMTP    — if SMTP_HOST is set in .env
  3. In-app only       — always stored in notifications table (fallback)
"""

import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Email delivery ────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    """
    Try to send an email. Returns True if sent, False if skipped/failed.
    Priority: Resend API → SMTP → skip.
    """
    if not to or "@" not in to:
        return False

    resend_key = os.getenv("RESEND_API_KEY")
    smtp_host = os.getenv("SMTP_HOST")

    if resend_key:
        return _send_via_resend(resend_key, to, subject, body)
    elif smtp_host:
        return _send_via_smtp(smtp_host, to, subject, body)
    else:
        logger.info(f"No email provider configured — skipping email to {to}")
        return False


def _send_via_resend(api_key: str, to: str, subject: str, body: str) -> bool:
    try:
        import httpx
        from_addr = os.getenv("EMAIL_FROM", "Healthcare Assistant <notifications@yourdomain.com>")
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_addr, "to": [to], "subject": subject, "text": body},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"Email sent via Resend to {to}: {subject}")
            return True
        logger.warning(f"Resend failed {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Resend error: {e}")
        return False


def _send_via_smtp(host: str, to: str, subject: str, body: str) -> bool:
    try:
        import smtplib
        from email.mime.text import MIMEText
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER", "")
        password = os.getenv("SMTP_PASS", "")
        from_addr = os.getenv("EMAIL_FROM", user)

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to

        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, [to], msg.as_string())

        logger.info(f"Email sent via SMTP to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False


def _get_patient_email(patient_id: str) -> str:
    """Look up patient email from DB. Returns empty string if not found."""
    try:
        from backend.database import get_db
        db = get_db()
        resp = db.client.table("patients").select("email").eq("id", patient_id).limit(1).execute()
        if resp.data:
            return resp.data[0].get("email", "")
    except Exception:
        pass
    # Fallback: if patient_id looks like an email address itself
    if "@" in patient_id:
        return patient_id
    return ""


def _get_doctor_email(doctor_id: str) -> str:
    """Look up doctor email from DB."""
    try:
        from backend.database import get_db
        db = get_db()
        resp = db.client.table("doctors").select("email").eq("id", doctor_id).limit(1).execute()
        if resp.data:
            return resp.data[0].get("email", "")
    except Exception:
        pass
    return ""


# ── Action executors ──────────────────────────────────────────────────────

def execute_action(action: dict, trigger_data: dict, workflow_run_id: str) -> dict:
    action_type = action.get("type")
    config = action.get("config", {})

    try:
        if action_type == "send_notification":
            return _send_notification(config, trigger_data, workflow_run_id)
        elif action_type == "auto_book_followup":
            return _auto_book_followup(config, trigger_data)
        elif action_type == "notify_doctor":
            return _notify_doctor(config, trigger_data, workflow_run_id)
        elif action_type == "run_agent":
            return _run_agent_action(config, trigger_data)
        else:
            return {"status": "skipped", "reason": f"Unknown action type: {action_type}"}
    except Exception as e:
        logger.error(f"Action {action_type} failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


def _get_doctor_name(doctor_id: str) -> str:
    """Look up doctor name from DB."""
    if not doctor_id:
        return ""
    try:
        from backend.database import get_db
        db = get_db()
        resp = db.client.table("doctors").select("name").eq("id", doctor_id).limit(1).execute()
        if resp.data:
            return resp.data[0].get("name", "")
    except Exception:
        pass
    return ""


def _send_notification(config: dict, trigger_data: dict, workflow_run_id: str) -> dict:
    """
    Notify a patient:
    1. Always stores in notifications table (in-app bell)
    2. Also sends email if provider configured + patient email known
    """
    from backend.database import get_db

    patient_id = trigger_data.get("patient_id", "unknown")
    title = _interpolate(config.get("title", "Notification"), trigger_data)
    message = _interpolate(config.get("message", ""), trigger_data)
    notif_type = config.get("type", "info")

    # Build rich metadata for the detail view
    metadata: dict = {
        k: v for k, v in trigger_data.items()
        if k in ("doctor_id", "specialty", "date", "time", "confirmation_number", "reason")
    }
    doctor_id = trigger_data.get("doctor_id", "")
    if doctor_id:
        doctor_name = _get_doctor_name(doctor_id)
        if doctor_name:
            metadata["doctor_name"] = doctor_name

    # 1. Store in DB (in-app notification)
    db = get_db()
    db.client.table("notifications").insert({
        "patient_id": patient_id,
        "workflow_run_id": workflow_run_id,
        "title": title,
        "message": message,
        "type": notif_type,
        "metadata": metadata,
    }).execute()

    # 2. Send email if possible
    email = _get_patient_email(patient_id)
    email_sent = _send_email(
        to=email,
        subject=f"[Healthcare] {title}",
        body=f"{message}\n\n---\nThis is an automated message from your healthcare clinic.",
    ) if email else False

    logger.info(f"Patient notification → {patient_id} | in-app=✓ | email={'✓' if email_sent else '✗ (no email)'}")
    return {
        "status": "success",
        "patient_id": patient_id,
        "title": title,
        "in_app": True,
        "email_sent": email_sent,
    }


def _notify_doctor(config: dict, trigger_data: dict, workflow_run_id: str) -> dict:
    """
    Notify a doctor:
    1. Stores in notifications table under doctor:{doctor_id}
    2. Sends email to doctor's registered email
    """
    from backend.database import get_db

    doctor_id = trigger_data.get("doctor_id", "")
    patient_id = trigger_data.get("patient_id", "")
    title = _interpolate(config.get("title", "Patient Alert"), trigger_data)
    message = _interpolate(config.get("message", ""), trigger_data)

    metadata = {
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        **{k: v for k, v in trigger_data.items()
           if k in ("specialty", "date", "time", "confirmation_number", "reason")},
    }

    # 1. Store in DB
    db = get_db()
    db.client.table("notifications").insert({
        "patient_id": f"doctor:{doctor_id}",
        "workflow_run_id": workflow_run_id,
        "title": title,
        "message": message,
        "type": "doctor_alert",
        "metadata": metadata,
    }).execute()

    # 2. Email the doctor using their registered email
    doctor_email = _get_doctor_email(doctor_id)
    email_sent = _send_email(
        to=doctor_email,
        subject=f"[Patient Alert] {title}",
        body=f"Patient ID: {patient_id}\n\n{message}\n\n---\nHealthcare System",
    ) if doctor_email else False

    logger.info(f"Doctor notification → {doctor_id} ({doctor_email or 'no email'}) | in-app=✓ | email={'✓' if email_sent else '✗'}")
    return {
        "status": "success",
        "doctor_id": doctor_id,
        "doctor_email": doctor_email or "not found",
        "in_app": True,
        "email_sent": email_sent,
    }


def _auto_book_followup(config: dict, trigger_data: dict) -> dict:
    from backend.tools import booking

    patient_id = trigger_data.get("patient_id")
    specialty = trigger_data.get("specialty", "general-practice")
    days_after = config.get("days_after", 7)
    preferred_time = config.get("preferred_time", "10:00")
    reason = config.get("reason", "Follow-up appointment")

    target_date = (datetime.now() + timedelta(days=days_after)).strftime("%Y-%m-%d")
    result = booking.book(
        user_id=patient_id,
        date=target_date,
        time=preferred_time,
        specialty=specialty,
        reason=reason,
    )

    if result.get("error"):
        return {"status": "failed", "error": result.get("message")}

    return {
        "status": "success",
        "confirmation": result.get("confirmation_number"),
        "date": target_date,
    }


def _run_agent_action(config: dict, trigger_data: dict) -> dict:
    """
    Run the AI agent in a dedicated thread with its own event loop and collect its response.
    asyncio.get_event_loop().run_until_complete() raises RuntimeError when called
    from inside a running event loop (FastAPI / scheduler), so we spin a new thread.
    """
    import asyncio
    import json as _json
    import threading
    from backend.agent.orchestrator import run as agent_run

    prompt = config.get("prompt", "Review this patient case and take appropriate action.")
    context_str = "\n".join(f"{k}: {v}" for k, v in trigger_data.items())
    full_prompt = f"{prompt}\n\nPatient context:\n{context_str}"
    session_id = f"workflow_{trigger_data.get('patient_id', 'unknown')}"

    result_holder: dict = {}

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _gather():
                async for chunk in agent_run(session_id, full_prompt):
                    if not chunk.startswith("data: "):
                        continue
                    try:
                        evt = _json.loads(chunk[6:])
                        if evt.get("type") == "final":
                            result_holder["response"] = evt.get("content", "")
                        elif evt.get("type") == "error":
                            result_holder["error"] = evt.get("message", "Agent error")
                    except Exception:
                        pass
            loop.run_until_complete(_gather())
        except Exception as exc:
            result_holder["error"] = str(exc)
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)

    if t.is_alive():
        return {"status": "failed", "error": "Agent timed out after 120s"}
    if "error" in result_holder:
        return {"status": "failed", "error": result_holder["error"]}
    return {"status": "success", "mode": "agentic", "response": result_holder.get("response", "")}


def _interpolate(template: str, data: dict) -> str:
    for key, val in data.items():
        template = template.replace(f"{{{{{key}}}}}", str(val))
    return template
