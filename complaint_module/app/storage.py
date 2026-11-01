import json
import os
import shutil
import tempfile
import threading
import uuid
from typing import List, Dict, Any, Optional
from . import pg_store
from .models import Complaint, AuthorityModel, CitizenModel, WorkerModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")  # read-only reference data shipped with the code
# Mutable state (complaints + uploaded photos) can live on a mounted volume in production.
STATE_DIR = os.getenv("COMPLAINT_STATE_DIR", DATA_DIR)
UPLOADS_DIR = os.path.join(STATE_DIR, "uploads")
AUTHORITIES_FILE = os.path.join(DATA_DIR, "authorities.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
WORKERS_FILE = os.path.join(DATA_DIR, "workers.json")
COMPLAINTS_FILE = os.path.join(STATE_DIR, "complaints.json")

os.makedirs(UPLOADS_DIR, exist_ok=True)
if STATE_DIR != DATA_DIR:
    # Seed sample evidence photos into the volume so default photo URLs resolve.
    for _name in os.listdir(os.path.join(DATA_DIR, "uploads")):
        _target = os.path.join(UPLOADS_DIR, _name)
        if not os.path.exists(_target):
            shutil.copy2(os.path.join(DATA_DIR, "uploads", _name), _target)

# The auto-escalation worker and API requests both write complaints.json.
_WRITE_LOCK = threading.RLock()


class DataStore:
    def __init__(self):
        self._ensure_files()
        if pg_store.enabled():
            # Shared CitySense database (schema civic_flow); first start imports the JSON data.
            notices_file = os.path.join(STATE_DIR, "notices.json")
            seed_notices = json.load(open(notices_file, encoding="utf-8")) if os.path.exists(notices_file) else []
            pg_store.init([c.model_dump() for c in self._load_json()], seed_notices)
            print("[Storage] complaints and notices stored in Postgres (civic_flow)")

    def _ensure_files(self):
        if not os.path.exists(COMPLAINTS_FILE):
            with open(COMPLAINTS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def load_authorities(self) -> List[AuthorityModel]:
        with open(AUTHORITIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [AuthorityModel(**a) for a in data]

    def load_user(self) -> CitizenModel:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return CitizenModel(
                user_id=data.get("user_id", "CIT-2026-8921"),
                name=data.get("full_name", "Aditya Sharma"),
                email=data.get("email", "aditya.sharma@city.gov.in"),
                phone=data.get("phone", "+91 98765 43210"),
                ward=data.get("ward", "Ward 14 - Rajpur Road")
            )

    def load_user_raw(self) -> Dict[str, Any]:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_workers(self) -> List[Dict[str, Any]]:
        with open(WORKERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_complaints(self) -> List[Complaint]:
        if pg_store.enabled():
            return [Complaint(**d) for d in pg_store.list_complaints()]
        return self._load_json()

    def _load_json(self) -> List[Complaint]:
        if not os.path.exists(COMPLAINTS_FILE):
            return []
        try:
            with open(COMPLAINTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Complaint(**c) for c in data]
        except Exception:
            return []

    def save_complaints(self, complaints: List[Complaint]):
        if pg_store.enabled():
            pg_store.replace_complaints([c.model_dump() for c in complaints])
            return
        # Atomic replace so a crash mid-write never leaves a truncated JSON file.
        with _WRITE_LOCK:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(COMPLAINTS_FILE), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump([c.model_dump() for c in complaints], f, indent=2)
            os.replace(tmp, COMPLAINTS_FILE)

    def get_complaint(self, tracking_id: str) -> Optional[Complaint]:
        if pg_store.enabled():
            found = pg_store.get_complaint(tracking_id)
            return Complaint(**found) if found else None
        for c in self.load_complaints():
            if c.tracking_id.lower() == tracking_id.lower():
                return c
        return None

    def upsert_complaint(self, complaint: Complaint):
        if pg_store.enabled():
            pg_store.upsert_complaint(complaint.model_dump())
            return
        with _WRITE_LOCK:
            self._upsert(complaint)

    def _upsert(self, complaint: Complaint):
        complaints = self.load_complaints()
        found = False
        for idx, item in enumerate(complaints):
            if item.tracking_id == complaint.tracking_id:
                complaints[idx] = complaint
                found = True
                break
        if not found:
            complaints.insert(0, complaint)
        self.save_complaints(complaints)

    def reset_complaints(self):
        self.save_complaints([])


store = DataStore()
