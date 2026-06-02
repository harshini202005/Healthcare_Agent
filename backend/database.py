import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        self.client: Client = create_client(url, key)

    # ── Doctors ───────────────────────────────────────────────────────────────

    def get_doctors(self, specialty: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.client.table("doctors").select("*")
        if specialty:
            query = query.eq("specialty", specialty.lower())
        return query.execute().data or []

    def get_doctor_by_id(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        res = self.client.table("doctors").select("*").eq("id", doctor_id).single().execute()
        return res.data if hasattr(res, "data") else None

    def get_doctor_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        normalized = name.lower().replace("dr.", "").replace("dr ", "").strip()
        res = self.client.table("doctors").select("*").ilike("name", f"%{normalized}%").execute()
        return res.data[0] if res.data else None

    def search_doctors(self, search_term: str) -> List[Dict[str, Any]]:
        if search_term.startswith("doc_"):
            doc = self.get_doctor_by_id(search_term)
            return [doc] if doc else []
        normalized = search_term.lower().replace("dr.", "").replace("dr ", "").strip()
        res = self.client.table("doctors").select("*").ilike("name", f"%{normalized}%").execute()
        if res.data:
            return res.data
        res = self.client.table("doctors").select("*").ilike("specialty", f"%{normalized}%").execute()
        return res.data or []

    # ── Schedules ─────────────────────────────────────────────────────────────

    def get_doctor_schedule(self, doctor_id: str) -> List[Dict[str, Any]]:
        return (
            self.client.table("doctor_schedules")
            .select("*")
            .eq("doctor_id", doctor_id)
            .order("day_of_week")
            .execute()
            .data or []
        )

    # ── Appointments ──────────────────────────────────────────────────────────

    def get_appointments(self, doctor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.client.table("appointments").select("*")
        if doctor_id:
            query = query.eq("doctor_id", doctor_id)
        if date:
            query = query.eq("appointment_date", date)
        return query.order("appointment_time").execute().data or []

    def check_doctor_conflict(self, doctor_id: str, date: str, time: str) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.client.table("appointments")
                .select("confirmation_number")
                .eq("doctor_id", doctor_id)
                .eq("appointment_date", date)
                .eq("appointment_time", time)
                .neq("status", "cancelled")
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    def create_appointment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        res = self.client.table("appointments").insert(data).execute()
        return res.data[0] if res.data else data

    def get_available_doctors(self, specialty: str, date: str, time: str) -> List[Dict[str, Any]]:
        doctors = self.get_doctors(specialty)
        if not doctors:
            return []
        weekday = datetime.strptime(date, "%Y-%m-%d").weekday()
        available = []
        for doc in doctors:
            if self.check_doctor_conflict(doc["id"], date, time):
                continue
            schedules = (
                self.client.table("doctor_schedules")
                .select("start_time,end_time")
                .eq("doctor_id", doc["id"])
                .eq("day_of_week", weekday)
                .eq("is_available", True)
                .execute()
                .data or []
            )
            if any(s["start_time"] <= time <= s["end_time"] for s in schedules):
                available.append(doc)
        return available


def get_db() -> Database:
    return Database()
