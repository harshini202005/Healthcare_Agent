"""
Workflow engine: evaluates triggers, checks conditions, creates pending runs.
Called by tool handlers (e.g., booking.py) when events occur.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Supported trigger types
TRIGGER_TYPES = [
    "appointment_booked",
    "appointment_cancelled",
    "appointment_completed",
    "patient_no_show",
    "new_patient",
    "scheduled",
]


def trigger_workflow(trigger_type: str, trigger_data: dict):
    """
    Called when an event occurs. Finds matching active workflows,
    evaluates conditions, and schedules workflow runs.
    """
    try:
        from backend.database import get_db
        db = get_db()

        # Fetch all active workflows matching this trigger
        response = (
            db.client.table("workflows")
            .select("*")
            .eq("trigger_type", trigger_type)
            .eq("is_active", True)
            .execute()
        )

        workflows = response.data if response.data else []
        logger.info(f"Trigger '{trigger_type}': found {len(workflows)} matching workflow(s)")

        for workflow in workflows:
            if _evaluate_conditions(workflow.get("conditions", []), trigger_data):
                _schedule_run(workflow, trigger_data, db)

    except Exception as e:
        logger.error(f"Workflow trigger error: {e}", exc_info=True)


def _evaluate_conditions(conditions: list, trigger_data: dict) -> bool:
    """All conditions must pass (AND logic)."""
    for cond in conditions:
        field = cond.get("field", "")
        operator = cond.get("operator", "equals")
        expected = cond.get("value", "")

        actual = str(trigger_data.get(field, "")).lower()
        expected_str = str(expected).lower()

        if operator == "equals" and actual != expected_str:
            return False
        elif operator == "not_equals" and actual == expected_str:
            return False
        elif operator == "contains" and expected_str not in actual:
            return False
        elif operator == "not_contains" and expected_str in actual:
            return False

    return True


def _now_utc() -> str:
    """ISO 8601 UTC timestamp with timezone suffix — compatible with Supabase TIMESTAMPTZ."""
    return datetime.now(timezone.utc).isoformat()


def _schedule_run(workflow: dict, trigger_data: dict, db):
    delay_hours = workflow.get("delay_hours", 0)
    scheduled_for = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

    run_record = {
        "workflow_id": workflow["id"],
        "trigger_data": trigger_data,
        "status": "pending",
        "scheduled_for": scheduled_for.isoformat(),
        "actions_taken": [],
    }

    db.client.table("workflow_runs").insert(run_record).execute()
    logger.info(
        f"Scheduled run for workflow '{workflow['name']}' at {scheduled_for.isoformat()}"
    )


def execute_pending_runs(force: bool = False) -> dict:
    """
    Pick up pending runs and execute their actions.
    force=True: ignore scheduled_for (used by Test button — bypasses delay).
    Returns a summary dict for the API response.
    """
    from backend.database import get_db
    from backend.workflows.actions import execute_action

    db = get_db()
    now = _now_utc()
    logger.info(f"Scheduler checking pending runs (now={now}, force={force})")

    try:
        query = (
            db.client.table("workflow_runs")
            .select("*, workflows(*)")
            .eq("status", "pending")
        )
        if not force:
            query = query.lte("scheduled_for", now)

        response = query.limit(20).execute()
        runs = response.data if response.data else []
        logger.info(f"Found {len(runs)} pending run(s) {'(force mode)' if force else ''}")

        results = []
        for run in runs:
            _execute_run(run, db, execute_action)
            results.append({"run_id": run["id"], "workflow": run.get("workflows", {}).get("name", "?")})

        return {"processed": len(runs), "runs": results}

    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)
        return {"processed": 0, "error": str(e)}


def _execute_run(run: dict, db, execute_action_fn):
    run_id = run["id"]
    workflow = run.get("workflows", {})
    trigger_data = run.get("trigger_data", {})
    actions = workflow.get("actions", [])

    # Mark as running
    db.client.table("workflow_runs").update(
        {"status": "running", "started_at": _now_utc()}
    ).eq("id", run_id).execute()

    actions_taken = []
    all_success = True
    error_msg = None

    try:
        for action in actions:
            result = execute_action_fn(action, trigger_data, run_id)
            actions_taken.append({"action": action.get("type"), "result": result})
            if result.get("status") == "failed":
                all_success = False
                error_msg = result.get("error", "Action failed")
    except Exception as e:
        all_success = False
        error_msg = str(e)
        logger.error(f"Run {run_id} action error: {e}", exc_info=True)

    final_status = "completed" if all_success else "failed"
    update = {
        "status": final_status,
        "completed_at": _now_utc(),
        "actions_taken": actions_taken,
    }
    if error_msg:
        update["error_message"] = error_msg

    db.client.table("workflow_runs").update(update).eq("id", run_id).execute()
    logger.info(f"Workflow run {run_id} → {final_status} ({len(actions_taken)} actions)")
