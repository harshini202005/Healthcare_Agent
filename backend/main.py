
from contextlib import asynccontextmanager
from fastapi import FastAPI, Body, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from backend.mcp import call_tool, get_available_tools
from backend.auth import (
    hash_password, verify_password, create_token,
    get_current_user, require_admin, require_doctor_or_admin,
)
from typing import Dict, Any, Optional
import logging
import json
import os
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.workflows import scheduler
    _seed_default_workflows()
    scheduler.start()
    yield
    scheduler.stop()


def _seed_default_workflows():
    """Insert built-in workflows if they don't already exist (idempotent)."""
    DEFAULTS = [
        {
            "name": "Smart Follow-Up",
            "description": "AI reviews the appointment reason and specialty, decides the optimal next visit, and books it automatically.",
            "trigger_type": "appointment_completed",
            "delay_hours": 0,
            "is_active": True,
            "is_agentic": True,
            "conditions": [],
            "actions": [
                {
                    "type": "run_agent",
                    "config": {
                        "prompt": (
                            "You are a healthcare follow-up coordinator. A patient just completed an appointment.\n\n"
                            "Details:\n"
                            "- Patient ID: {{patient_id}}\n"
                            "- Specialty / Department: {{specialty}}\n"
                            "- Reason for visit: {{reason}}\n"
                            "- Attending doctor: {{doctor_id}}\n\n"
                            "Your tasks:\n"
                            "1. Based on the specialty and reason, decide whether a follow-up is needed and how soon "
                            "(e.g. 3 days for acute issues, 1–2 weeks for routine, 4–6 weeks for chronic management, "
                            "none for one-off procedures).\n"
                            "2. If a follow-up IS needed, book an appointment using the book_appointment tool — "
                            "choose an appropriate morning slot (09:00–12:00), the same specialty, "
                            "and reason 'Follow-up: {{reason}}'.\n"
                            "3. Send the patient a warm, personalised message explaining: what was decided, why, "
                            "what to watch for, and the new appointment details if booked.\n"
                            "4. If no follow-up is needed, send a brief positive discharge message instead.\n\n"
                            "Be specific to the patient's situation. Do not use generic templates."
                        )
                    },
                }
            ],
        }
    ]
    try:
        from backend.database import get_db
        db = get_db()
        for wf in DEFAULTS:
            exists = (
                db.client.table("workflows")
                .select("id")
                .eq("name", wf["name"])
                .limit(1)
                .execute()
            )
            if not exists.data:
                db.client.table("workflows").insert(wf).execute()
                logger.info(f"Seeded default workflow: {wf['name']}")
            else:
                # Keep the definition up to date (preserves is_active set by user)
                db.client.table("workflows").update({
                    "description": wf["description"],
                    "delay_hours": wf["delay_hours"],
                    "actions": wf["actions"],
                    "is_agentic": wf["is_agentic"],
                    "conditions": wf["conditions"],
                }).eq("name", wf["name"]).execute()
    except Exception as e:
        logger.warning(f"Could not seed default workflows: {e}")


app = FastAPI(
    title="Healthcare MCP API",
    description="Model Context Protocol API for Healthcare Management",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Existing MCP endpoints ────────────────────────────────────────────────

@app.get("/api")
def api_info():
    return {
        "message": "Healthcare MCP API v2",
        "endpoints": {
            "chat": "/api/chat",
            "tools": "/mcp/tools",
            "call": "/mcp/call",
            "workflows": "/api/workflows",
            "notifications": "/api/notifications/{patient_id}",
            "docs": "/docs",
        },
    }


@app.get("/mcp/tools")
def list_tools():
    return {"tools": get_available_tools()}


@app.post("/mcp/call")
def mcp_call(payload: Dict[str, Any] = Body(...)):
    name = payload.get("name")
    args = payload.get("args", {})

    if not name:
        return {"error": "Missing 'name' field in request"}

    logger.info("=" * 60)
    logger.info(f"🔧 TOOL CALL: {name}")
    result = call_tool(name, args)
    if "error" in result:
        logger.error(f"❌ {result.get('error')}")
    else:
        logger.info(f"✅ SUCCESS")
    logger.info("=" * 60)

    return result


# ── Auth endpoints ───────────────────────────────────────────────────────────

def _db_table_missing(e) -> bool:
    msg = str(e)
    return "schema cache" in msg or "PGRST205" in msg or "does not exist" in msg


@app.post("/api/auth/signup")
def signup(payload: Dict[str, Any] = Body(...)):
    """Register a new user. role: admin | doctor | patient."""
    from backend.database import get_db
    try:
        db = get_db()

        username  = (payload.get("username") or "").strip()
        email     = (payload.get("email") or "").strip().lower()
        password  = payload.get("password") or ""
        role      = payload.get("role", "patient")
        linked_id = (payload.get("linked_id") or "").strip()

        if not username or not email or not password:
            raise HTTPException(400, "username, email and password are required")
        if role not in ("admin", "doctor", "patient"):
            raise HTTPException(400, "role must be admin, doctor, or patient")
        if len(password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")

        existing = db.client.table("users").select("id").eq("username", username).execute()
        if existing.data:
            raise HTTPException(409, "Username already taken")
        existing_email = db.client.table("users").select("id").eq("email", email).execute()
        if existing_email.data:
            raise HTTPException(409, "Email already registered")

        if role == "doctor" and linked_id:
            doc = db.client.table("doctors").select("id").eq("id", linked_id).execute()
            if not doc.data:
                raise HTTPException(400, f"Doctor ID '{linked_id}' not found")

        pw_hash = hash_password(password)
        res = db.client.table("users").insert({
            "username": username, "email": email, "password_hash": pw_hash,
            "role": role, "linked_id": linked_id or None,
        }).execute()

        user = res.data[0]
        token = create_token(user["id"], user["role"], user.get("linked_id") or "", user["username"])
        return {
            "token": token,
            "user": {
                "id": user["id"], "username": user["username"], "email": user["email"],
                "role": user["role"], "linked_id": user.get("linked_id"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        if _db_table_missing(e):
            raise HTTPException(503, "Database not set up yet — run supabase_iam_schema.sql in your Supabase SQL Editor first")
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(500, f"Server error: {e}")


@app.post("/api/auth/login")
def login(payload: Dict[str, Any] = Body(...)):
    """Login with username + password. Returns JWT token."""
    from backend.database import get_db
    try:
        db = get_db()

        username = (payload.get("username") or "").strip()
        password  = payload.get("password") or ""

        if not username or not password:
            raise HTTPException(400, "username and password required")

        res = db.client.table("users").select("*").eq("username", username).execute()
        if not res.data:
            raise HTTPException(401, "Invalid username or password")

        user = res.data[0]
        if not user.get("is_active", True):
            raise HTTPException(403, "Account is disabled")
        if not verify_password(password, user["password_hash"]):
            raise HTTPException(401, "Invalid username or password")

        token = create_token(user["id"], user["role"], user.get("linked_id") or "", user["username"])
        return {
            "token": token,
            "user": {
                "id": user["id"], "username": user["username"], "email": user["email"],
                "role": user["role"], "linked_id": user.get("linked_id"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        if _db_table_missing(e):
            raise HTTPException(503, "Database not set up yet — run supabase_iam_schema.sql in your Supabase SQL Editor first")
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(500, f"Server error: {e}")


@app.get("/api/auth/me")
def get_me(authorization: Optional[str] = Header(None)):
    """Returns current user info from token."""
    from backend.database import get_db
    try:
        user_payload = get_current_user(authorization)
        db = get_db()
        res = db.client.table("users").select("id,username,email,role,linked_id,created_at").eq("id", user_payload["sub"]).execute()
        if not res.data:
            raise HTTPException(404, "User not found")
        return {"user": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        if _db_table_missing(e):
            raise HTTPException(503, "Database not set up yet")
        raise HTTPException(500, str(e))


@app.get("/api/auth/doctors-list")
def list_doctors_for_signup():
    """Returns doctors list for signup dropdown (public — no auth needed)."""
    from backend.database import get_db
    db = get_db()
    res = db.client.table("doctors").select("id,name,specialty").order("name").execute()
    return {"doctors": res.data or []}


# ── Doctor dashboard endpoints ────────────────────────────────────────────────

@app.get("/api/doctor/patients")
def get_doctor_patients(
    date: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """
    Returns today's (or given date's) appointments for the logged-in doctor.
    Includes treatment_status for each appointment.
    """
    from backend.database import get_db
    user = require_doctor_or_admin(authorization)
    db   = get_db()

    target_date = date or datetime.utcnow().strftime("%Y-%m-%d")
    doctor_id   = user["linked_id"] if user["role"] == "doctor" else None

    query = (
        db.client.table("appointments")
        .select("*")
        .eq("appointment_date", target_date)
        .order("appointment_time")
    )
    if doctor_id:
        query = query.eq("doctor_id", doctor_id)

    res = query.execute()
    appointments = res.data or []

    # Count by treatment_status
    summary = {"scheduled": 0, "waiting": 0, "in_treatment": 0, "completed": 0, "no_show": 0}
    for appt in appointments:
        s = appt.get("treatment_status", "scheduled") or "scheduled"
        summary[s] = summary.get(s, 0) + 1

    return {"appointments": appointments, "summary": summary, "date": target_date}


@app.put("/api/appointments/{confirmation_number}/treatment-status")
def update_treatment_status(
    confirmation_number: str,
    payload: Dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(None),
):
    """
    Doctor updates a patient's treatment status.
    Valid values: scheduled | waiting | in_treatment | completed | no_show
    """
    from backend.database import get_db
    user = require_doctor_or_admin(authorization)
    db   = get_db()

    new_status = payload.get("treatment_status")
    valid = ("scheduled", "waiting", "in_treatment", "completed", "no_show")
    if new_status not in valid:
        raise HTTPException(400, f"treatment_status must be one of: {valid}")

    res = db.client.table("appointments").select("*").eq("confirmation_number", confirmation_number).execute()
    if not res.data:
        raise HTTPException(404, "Appointment not found")

    appt = res.data[0]
    # Doctors can only update their own patients
    if user["role"] == "doctor" and appt.get("doctor_id") != user["linked_id"]:
        raise HTTPException(403, "You can only update your own patients")

    db.client.table("appointments").update({"treatment_status": new_status}).eq(
        "confirmation_number", confirmation_number
    ).execute()

    # If marked no_show, fire workflow
    if new_status == "no_show":
        from backend.workflows.engine import trigger_workflow
        trigger_workflow("patient_no_show", {
            "patient_id":    appt.get("patient_id", ""),
            "doctor_id":     appt.get("doctor_id", ""),
            "specialty":     appt.get("specialty", ""),
            "confirmation_number": confirmation_number,
        })

    return {"status": "updated", "confirmation_number": confirmation_number, "treatment_status": new_status}


@app.get("/api/admin/users")
def list_users(authorization: Optional[str] = Header(None)):
    """Admin only: list all users."""
    from backend.database import get_db
    require_admin(authorization)
    db = get_db()
    res = db.client.table("users").select("id,username,email,role,linked_id,is_active,created_at").order("created_at", desc=True).execute()
    return {"users": res.data or []}


@app.put("/api/admin/users/{user_id}/toggle")
def toggle_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Admin only: enable/disable a user."""
    from backend.database import get_db
    require_admin(authorization)
    db = get_db()
    res = db.client.table("users").select("is_active").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(404, "User not found")
    new_state = not res.data[0]["is_active"]
    db.client.table("users").update({"is_active": new_state}).eq("id", user_id).execute()
    return {"is_active": new_state}


# ── Agentic Chat endpoint ─────────────────────────────────────────────────

@app.post("/api/chat")
async def agent_chat(payload: Dict[str, Any] = Body(...)):
    """
    Agentic chat endpoint. Streams SSE events:
      {"type": "tool_use", "tool": "...", "label": "..."}
      {"type": "final", "content": "..."}
      {"type": "error", "message": "..."}
    """
    message = payload.get("message", "").strip()
    session_id = payload.get("session_id", "default")
    patient_id = (payload.get("patient_id") or "").strip()

    if not message:
        async def _err():
            yield 'data: {"type": "error", "message": "Empty message"}\n\n'
        return StreamingResponse(_err(), media_type="text/event-stream")

    # Inject the logged-in patient's ID so the agent always books under the right patient
    if patient_id:
        message = (
            f"{message}"
            f"\n\n[System: The current user's patient ID is '{patient_id}'. "
            f"Always use this exact patient ID for bookings and appointment lookups unless the user asks about someone else.]"
        )

    from backend.agent.orchestrator import run as agent_run

    return StreamingResponse(
        agent_run(session_id, message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Workflow CRUD endpoints ───────────────────────────────────────────────

@app.get("/api/workflows")
def list_workflows():
    from backend.database import get_db
    db = get_db()
    response = db.client.table("workflows").select("*").order("created_at", desc=True).execute()
    return {"workflows": response.data or []}


@app.post("/api/workflows")
def create_workflow(payload: Dict[str, Any] = Body(...)):
    from backend.database import get_db
    db = get_db()

    required = ["name", "trigger_type", "actions"]
    for field in required:
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    record = {
        "name": payload["name"],
        "description": payload.get("description", ""),
        "trigger_type": payload["trigger_type"],
        "trigger_config": payload.get("trigger_config", {}),
        "conditions": payload.get("conditions", []),
        "actions": payload["actions"],
        "delay_hours": payload.get("delay_hours", 0),
        "is_active": payload.get("is_active", True),
        "is_agentic": payload.get("is_agentic", False),
    }

    response = db.client.table("workflows").insert(record).execute()
    return {"workflow": response.data[0] if response.data else record}


@app.put("/api/workflows/{workflow_id}")
def update_workflow(workflow_id: str, payload: Dict[str, Any] = Body(...)):
    from backend.database import get_db
    db = get_db()

    allowed = ["name", "description", "trigger_type", "trigger_config",
               "conditions", "actions", "delay_hours", "is_active", "is_agentic"]
    update = {k: v for k, v in payload.items() if k in allowed}
    update["updated_at"] = datetime.utcnow().isoformat()

    response = db.client.table("workflows").update(update).eq("id", workflow_id).execute()
    return {"workflow": response.data[0] if response.data else {}}


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    from backend.database import get_db
    db = get_db()
    db.client.table("workflows").delete().eq("id", workflow_id).execute()
    return {"deleted": workflow_id}


@app.get("/api/workflows/{workflow_id}/runs")
def get_workflow_runs(workflow_id: str):
    from backend.database import get_db
    db = get_db()
    response = (
        db.client.table("workflow_runs")
        .select("*")
        .eq("workflow_id", workflow_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"runs": response.data or []}


@app.post("/api/workflows/trigger")
def manual_trigger(payload: Dict[str, Any] = Body(...)):
    """Manually fire a workflow trigger (for testing)."""
    trigger_type = payload.get("trigger_type")
    trigger_data = payload.get("trigger_data", {})

    if not trigger_type:
        raise HTTPException(status_code=400, detail="trigger_type required")

    from backend.workflows.engine import trigger_workflow
    trigger_workflow(trigger_type, trigger_data)
    return {"status": "triggered", "trigger_type": trigger_type}


@app.post("/api/workflows/run-now")
def run_pending_now(payload: Dict[str, Any] = Body(default={})):
    """
    Force-execute pending runs immediately.
    force=true  → ignore scheduled_for (used by Test button, bypasses delay_hours).
    force=false → only run overdue ones (same as normal scheduler).
    Returns how many runs were processed and their results.
    """
    from backend.workflows.engine import execute_pending_runs
    force = payload.get("force", False)
    workflow_id = payload.get("workflow_id")  # optional: scope to one workflow (Test button)
    result = execute_pending_runs(force=force, workflow_id=workflow_id)
    return {"status": "ok", **result}


# ── Patient appointments summary ─────────────────────────────────────────

@app.get("/api/patients/{patient_id}/appointments")
def get_patient_appointments(patient_id: str):
    """Return last completed and next upcoming appointments for a patient."""
    from backend.database import get_db
    db = get_db()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    last_resp = (
        db.client.table("appointments")
        .select("*, doctors(name, specialty)")
        .eq("patient_id", patient_id)
        .lt("appointment_date", today_str)
        .order("appointment_date", desc=True)
        .limit(1)
        .execute()
    )

    next_resp = (
        db.client.table("appointments")
        .select("*, doctors(name, specialty)")
        .eq("patient_id", patient_id)
        .gte("appointment_date", today_str)
        .eq("status", "confirmed")
        .order("appointment_date")
        .limit(1)
        .execute()
    )

    return {
        "last_appointment": last_resp.data[0] if last_resp.data else None,
        "next_appointment": next_resp.data[0] if next_resp.data else None,
    }


# ── Notifications endpoint ────────────────────────────────────────────────

@app.get("/api/notifications/recent")
def get_recent_notifications(limit: int = 30, authorization: Optional[str] = Header(None)):
    """Return the most recent notifications across all patients/doctors. Admin only."""
    require_admin(authorization)
    from backend.database import get_db
    db = get_db()
    response = (
        db.client.table("notifications")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"notifications": response.data or []}


@app.get("/api/notifications/{patient_id}")
def get_notifications(patient_id: str, unread_only: bool = False, authorization: Optional[str] = Header(None)):
    from backend.database import get_db
    user = get_current_user(authorization)
    if user["role"] != "admin":
        # Build the set of valid IDs for this user (linked_id or username fallback)
        if user["role"] == "doctor":
            valid = {f"doctor:{user['linked_id']}", f"doctor:{user['username']}"} if user.get("linked_id") else {f"doctor:{user['username']}"}
        else:
            valid = {user.get("linked_id"), user["username"]} - {None, ""}
        if patient_id not in valid:
            raise HTTPException(403, "You can only view your own notifications")
    db = get_db()

    query = (
        db.client.table("notifications")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .limit(50)
    )
    if unread_only:
        query = query.eq("is_read", False)

    response = query.execute()
    return {"notifications": response.data or []}


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    from backend.database import get_db
    db = get_db()
    db.client.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    return {"status": "ok"}


# ── Appointment status update (triggers workflows) ────────────────────────

@app.post("/api/appointments/{confirmation_number}/complete")
def complete_appointment(confirmation_number: str, payload: Dict[str, Any] = Body(default={})):
    from backend.database import get_db
    from backend.workflows.engine import trigger_workflow

    db = get_db()
    response = (
        db.client.table("appointments")
        .select("*")
        .eq("confirmation_number", confirmation_number)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appt = response.data
    db.client.table("appointments").update({"status": "completed"}).eq(
        "confirmation_number", confirmation_number
    ).execute()

    trigger_workflow(
        "appointment_completed",
        {
            "patient_id": appt["patient_id"],
            "doctor_id": appt.get("doctor_id", ""),
            "specialty": appt.get("specialty", ""),
            "date": appt.get("appointment_date", ""),
            "confirmation_number": confirmation_number,
        },
    )

    return {"status": "completed", "confirmation_number": confirmation_number}


# ── Serve Frontend ────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
)


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="frontend-assets")
