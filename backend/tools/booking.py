import random
import logging
from datetime import datetime
from typing import Optional, Tuple
from backend.database import get_db

logger = logging.getLogger(__name__)


def _validate_time(time_str: str) -> Tuple[bool, Optional[str]]:
    try:
        hour, minute = map(int, time_str.split(":"))
        if minute % 15 != 0:
            return False, f"Time must be in 15-min intervals (00, 15, 30, 45). Got: {minute}"
        if not (0 <= hour <= 23):
            return False, f"Hour must be 00–23. Got: {hour}"
        total = hour * 60 + minute
        if total < 8 * 60:
            return False, "Clinic opens at 08:00 AM."
        if total > 17 * 60 + 45:
            return False, "Last slot is 05:45 PM."
        return True, None
    except Exception:
        return False, f"Invalid time format. Expected HH:MM, got: {time_str}"


def _validate_date(date_str: str) -> Tuple[bool, Optional[str]]:
    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False, f"Invalid date format. Expected YYYY-MM-DD, got: {date_str}"
    if appt_date < datetime.now().date():
        return False, f"Cannot book in the past. Today is {datetime.now().date().isoformat()}."
    return True, None


def book(
    user_id: str,
    date: str,
    time: str,
    specialty: Optional[str] = None,
    reason: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> dict:
    specialty = specialty or "General Practice"

    ok, err = _validate_date(date)
    if not ok:
        return {"error": True, "message": err, "suggestion": "Use YYYY-MM-DD format."}

    ok, err = _validate_time(time)
    if not ok:
        return {"error": True, "message": err, "suggestion": "Available: 08:00–17:45 in 15-min steps."}

    db = get_db()

    if doctor_id:
        doctor = db.get_doctor_by_id(doctor_id)
        if not doctor:
            return {"error": True, "message": f"Doctor not found: {doctor_id}", "suggestion": "Use get_doctors to find valid IDs."}
        if doctor["specialty"].lower() != specialty.lower():
            return {"error": True, "message": f"Dr. {doctor['name']} specialises in {doctor['specialty']}, not {specialty}."}
        if db.check_doctor_conflict(doctor_id, date, time):
            return {"error": True, "message": f"Dr. {doctor['name']} is already booked at {time} on {date}.", "suggestion": "Use get_available_slots."}
        assigned = doctor
    else:
        available = db.get_available_doctors(specialty, date, time)
        if not available:
            return {"error": True, "message": f"No {specialty} doctors available at {time} on {date}.", "suggestion": "Use get_available_slots."}
        assigned = available[0]
        doctor_id = assigned["id"]

    confirmation_number = f"APT-{random.randint(10000, 99999)}"
    booking_data = {
        "confirmation_number": confirmation_number,
        "patient_id": user_id,
        "doctor_id": doctor_id,
        "appointment_date": date,
        "appointment_time": time,
        "specialty": specialty,
        "reason": reason,
        "status": "confirmed",
    }

    db.create_appointment(booking_data)
    logger.info(f"Appointment booked: {confirmation_number} — {user_id} with {assigned['name']}")

    try:
        from backend.workflows.engine import trigger_workflow
        trigger_workflow("appointment_booked", {
            "patient_id": user_id, "doctor_id": doctor_id, "specialty": specialty,
            "date": date, "time": time, "confirmation_number": confirmation_number,
            "reason": reason or "",
        })
    except Exception:
        pass

    return {
        "message": f"Appointment booked with Dr. {assigned['name']}!",
        "confirmation_number": confirmation_number,
        "details": {
            "Patient ID": user_id, "Doctor": assigned["name"], "Doctor ID": doctor_id,
            "Date": date, "Time": time, "Specialty": specialty,
            "Reason": reason or "General checkup", "Status": "Confirmed",
        },
        "instructions": [
            "📝 Arrive 15 minutes early",
            "🪪 Bring insurance card and ID",
            "📞 Cancel at least 24 hours in advance",
        ],
    }


def get_appointment(confirmation_number: str) -> dict:
    db = get_db()
    try:
        res = db.client.table("appointments").select("*, doctors(*)").eq(
            "confirmation_number", confirmation_number).single().execute()
        if not res.data:
            return {"error": True, "message": f"Appointment not found: {confirmation_number}"}
        a = res.data
        return {
            "message": "Appointment found",
            "appointment": {
                "confirmation_number": a["confirmation_number"],
                "status": a["status"],
                "patient_id": a["patient_id"],
                "date": a["appointment_date"],
                "time": a["appointment_time"],
                "specialty": a["specialty"],
                "reason": a.get("reason", "Not specified"),
                "doctor": {
                    "name": a.get("doctors", {}).get("name", "Unknown"),
                    "specialty": a.get("doctors", {}).get("specialty", "Unknown"),
                },
            },
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to retrieve appointment: {e}"}


def cancel_appointment(confirmation_number: str, reason: Optional[str] = None) -> dict:
    db = get_db()
    try:
        res = db.client.table("appointments").select("confirmation_number").eq(
            "confirmation_number", confirmation_number).single().execute()
        if not res.data:
            return {"error": True, "message": f"Appointment not found: {confirmation_number}"}
        db.client.table("appointments").update(
            {"status": "cancelled", "notes": reason or "Cancelled by patient"}
        ).eq("confirmation_number", confirmation_number).execute()
        logger.info(f"Appointment cancelled: {confirmation_number}")
        return {"message": "Appointment cancelled.", "confirmation_number": confirmation_number}
    except Exception as e:
        return {"error": True, "message": f"Failed to cancel: {e}"}
