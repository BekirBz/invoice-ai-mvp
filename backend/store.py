# backend/store.py
"""
Persistence layer for Invoice AI MVP
- Initializes Firestore if service account exists (guarded: no double init)
- Falls back to in-memory store
- Exposes: save_invoice, get_invoice, list_invoices_for_user, coerce_legacy
"""

from __future__ import annotations
import os, uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

FIREBASE_READY = False
DB = None

# Detect new Firestore filtering API (FieldFilter)
try:
    from google.cloud.firestore_v1 import FieldFilter  # new API
    HAS_FIELD_FILTER = True
except Exception:
    HAS_FIELD_FILTER = False

# --- Firebase init (guarded for uvicorn --reload) ---
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = os.environ.get("FIREBASE_CRED")
    if not cred_path:
        for name in os.listdir("."):
            if name.endswith(".json") and ("firebase" in name or "admin" in name):
                cred_path = os.path.abspath(name)
                break

    if cred_path and os.path.exists(cred_path):
        # Prevent "default app already exists" on reload
        if not getattr(firebase_admin, "_apps", {}):
            firebase_admin.initialize_app(credentials.Certificate(cred_path))
        DB = firestore.client()
        FIREBASE_READY = True
        print(f"[store] Firestore ready: {cred_path}")
    else:
        print("[store] No service account JSON; using in-memory store.")
except Exception as e:
    print(f"[store] Firestore disabled ({e}); using in-memory store.")

# --- In-memory fallback ---
MEM_STORE: Dict[str, Dict[str, Any]] = {}

def coerce_legacy(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy Firestore docs to current schema expected by frontend."""
    d = dict(doc)

    # rawText -> ocr_text
    if "ocr_text" not in d:
        rt = d.get("rawText")
        if isinstance(rt, str):
            d["ocr_text"] = [rt]
        elif isinstance(rt, list):
            d["ocr_text"] = rt
        else:
            d["ocr_text"] = []

    # filename normalization
    if "filename" not in d:
        d["filename"] = d.get("sourceName") or "upload"

    # createdAt -> ISO string
    created = d.get("createdAt")
    try:
        if hasattr(created, "timestamp"):  # Firestore Timestamp
            d["createdAt"] = datetime.utcfromtimestamp(created.timestamp()).isoformat() + "Z"
        elif isinstance(created, datetime):
            d["createdAt"] = created.isoformat() + "Z"
        elif isinstance(created, (int, float)):
            d["createdAt"] = datetime.utcfromtimestamp(float(created)).isoformat() + "Z"
    except Exception:
        pass

    # ensure optional fields
    d.setdefault("vendor", None)
    d.setdefault("date", None)
    d.setdefault("amount", None)
    d.setdefault("currency", None)
    d.setdefault("vat", None)
    d.setdefault("fraud_score", None)
    d.setdefault("userId", "anonymous")
    d.setdefault("id", doc.get("id") or uuid.uuid4().hex)
    return d

def save_invoice(doc: Dict[str, Any]) -> str:
    """Create/overwrite invoice document."""
    if FIREBASE_READY and DB is not None:
        DB.collection("invoices").document(doc["id"]).set(doc)
        return doc["id"]
    MEM_STORE[doc["id"]] = doc
    return doc["id"]

def get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single invoice by id."""
    if FIREBASE_READY and DB is not None:
        snap = DB.collection("invoices").document(invoice_id).get()
        return snap.to_dict() if snap.exists else None
    return MEM_STORE.get(invoice_id)

def list_invoices_for_user(user_id: Optional[str]) -> List[Dict[str, Any]]:
    """List invoices, optionally filtered by userId, newest first."""
    if FIREBASE_READY and DB is not None:
        q = DB.collection("invoices")
        if user_id:
            # New API preferred (no warnings); fallback to legacy where()
            if HAS_FIELD_FILTER:
                q = q.where(filter=FieldFilter("userId", "==", user_id))
            else:
                q = q.where("userId", "==", user_id)
        docs = [{**d.to_dict(), "id": d.id} for d in q.stream()]
        docs.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
        return docs

    # In-memory path
    docs = [d for d in MEM_STORE.values() if (not user_id or d.get("userId") == user_id)]
    docs.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
    return docs