import logging
from typing import Optional, Dict, Any
from datetime import datetime
from backend.database import get_db

logger = logging.getLogger(__name__)


def get_doctors(specialty: Optional[str] = None) -> Dict[str, Any]:
    """Get available doctors, optionally filtered by specialty."""
    logger.info(f"get_doctors: specialty={specialty or 'all'}")
    db = get_db()

    try:
        doctors = db.get_doctors(specialty)

        if not doctors:
            return {
                "message": f"No doctors found{f' for specialty: {specialty}' if specialty else ''}",
                "doctors": [],
                "suggestion": "Try searching for a different specialty",
            }

        specialties_found = set()
        formatted = []
        for doc in doctors:
            specialties_found.add(doc.get("specialty", "").title())
            formatted.append({
                "id": doc["id"],
                "name": doc["name"],
                "specialty": doc["specialty"].title(),
                "experience": f"{doc.get('years_experience', 'N/A')} years",
                "email": doc.get("email", "N/A"),
            })

        logger.info(f"Found {len(formatted)} doctors")
        return {
            "message": f"Found {len(formatted)} doctor(s)",
            "specialties_available": list(specialties_found),
            "doctors": formatted,
            "instruction": "Use get_available_slots to check when these doctors are available",
        }

    except Exception as e:
        logger.error(f"get_doctors error: {e}")
        return {"error": True, "message": f"Failed to fetch doctors: {e}", "doctors": []}


def get_available_slots(specialty: str, date: str, doctor_id: Optional[str] = None) -> Dict[str, Any]:
    """Get available appointment time slots for a given specialty and date."""
    logger.info(f"get_available_slots: specialty={specialty}, date={date}, doctor_id={doctor_id}")

    try:
        check_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.now().date()
        if check_date < today:
            return {"error": True, "message": f"Cannot check availability for past date: {date}", "suggestion": "Provide a future date"}
        if check_date.weekday() >= 5:
            return {"message": "Clinic is closed on weekends", "available_slots": [], "suggestion": "Choose a weekday (Monday–Friday)"}
    except ValueError:
        return {"error": True, "message": f"Invalid date format: {date}", "suggestion": "Use YYYY-MM-DD"}

    db = get_db()

    try:
        if doctor_id:
            doctor = db.get_doctor_by_id(doctor_id)
            if not doctor:
                return {"error": True, "message": f"Doctor not found: {doctor_id}", "suggestion": "Use get_doctors to find valid IDs"}
            if doctor["specialty"].lower() != specialty.lower():
                return {"error": True, "message": f"Doctor {doctor['name']} specialises in {doctor['specialty']}, not {specialty}"}
            target_doctors = [doctor]
        else:
            target_doctors = db.get_doctors(specialty)

        if not target_doctors:
            return {"message": f"No doctors available for {specialty}", "available_slots": [], "suggestion": "Try a different specialty or date"}

        slot_times = [
            f"{h:02d}:{m:02d}"
            for h in range(9, 17)
            for m in [0, 15, 30, 45]
        ]

        slots_by_time: Dict[str, list] = {}
        for slot_time in slot_times:
            for doctor in target_doctors:
                if not db.check_doctor_conflict(doctor["id"], date, slot_time):
                    slots_by_time.setdefault(slot_time, []).append({
                        "doctor_id": doctor["id"],
                        "doctor_name": doctor["name"],
                    })

        if not slots_by_time:
            return {"message": f"No available slots for {specialty} on {date}", "available_slots": [], "suggestion": "Try a different date"}

        logger.info(f"Found {len(slots_by_time)} available time slots")
        return {
            "message": f"Found {len(slots_by_time)} available time slots for {specialty}",
            "date": date,
            "specialty": specialty.title(),
            "available_slots": slots_by_time,
            "instruction": "Use book_appointment with doctor_id to book a specific slot",
        }

    except Exception as e:
        logger.error(f"get_available_slots error: {e}")
        return {"error": True, "message": f"Failed to get available slots: {e}", "available_slots": []}


def get_doctor_schedule(doctor_identifier: str) -> Dict[str, Any]:
    """Get the weekly schedule for a doctor by ID or name."""
    logger.info(f"get_doctor_schedule: {doctor_identifier!r}")
    db = get_db()

    try:
        doctor = None
        if doctor_identifier.startswith("doc_"):
            doctor = db.get_doctor_by_id(doctor_identifier)

        if not doctor:
            results = db.search_doctors(doctor_identifier)
            if results:
                doctor = results[0]

        if not doctor:
            return {
                "error": True,
                "message": f"Doctor not found: '{doctor_identifier}'",
                "suggestion": "Use get_doctors to see all available doctors, or provide the doctor ID or full name",
            }

        schedules = db.get_doctor_schedule(doctor["id"])
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        formatted_schedule = [
            {"day": days[s.get("day_of_week", 0)], "hours": f"{s['start_time']} - {s['end_time']}"}
            for s in schedules
            if s.get("is_available")
        ]

        return {
            "message": f"Weekly schedule for {doctor['name']}",
            "doctor": {"id": doctor["id"], "name": doctor["name"], "specialty": doctor["specialty"].title()},
            "schedule": formatted_schedule,
        }

    except Exception as e:
        logger.error(f"get_doctor_schedule error: {e}")
        return {"error": True, "message": f"Failed to get schedule: {e}"}
