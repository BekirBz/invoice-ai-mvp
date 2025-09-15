# backend/store.py
"""
Persistence layer for Invoice AI MVP
- Initializes Firestore if a service account JSON is present (guarded: no double init)
- Falls back to an in-memory store (userId -> [docs]) so uploads append instead of overwrite
- Exposes: save_invoice, get_invoice, list_invoices_for_user, coerce_legacy
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
FIREBASE_READY = False
DB = None  # Firestore client or None

# In-memory fallback:
# - MEM_LIST: userId -> [docs] (append; newest first)
# - MEM_BY_ID: id -> doc (fast lookup)
MEM_LIST: Dict[str, List[Dict[str, Any]]] = {}
MEM_BY_ID: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Detect new Firestore filtering API (FieldFilter)
# ---------------------------------------------------------------------------
try:
    from google.cloud.firestore_v1 import FieldFilter  # new API
    HAS_FIELD_FILTER = True
except Exception:
    HAS_FIELD_FILTER = False

# ---------------------------------------------------------------------------
# Firebase init (guarded for uvicorn --reload)
# ---------------------------------------------------------------------------
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = os.environ.get("FIREBASE_CRED")
    if not cred_path:
        # Best-effort: look for a likely service account JSON in CWD
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def coerce_legacy(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize loose/legacy documents to the schema expected by frontend.
    Ensures keys exist and types are sane.
    """
    d = dict(doc)

    # id & userId
    d.setdefault("id", d.get("id") or uuid.uuid4().hex)
    d.setdefault("userId", d.get("userId") or "anonymous")

    # ocr_text (from rawText if necessary)
    if "ocr_text" not in d:
        rt = d.get("rawText")
        if isinstance(rt, str):
            d["ocr_text"] = [rt]
        elif isinstance(rt, list):
            d["ocr_text"] = rt
        else:
            d["ocr_text"] = []

    # filename
    d.setdefault("filename", d.get("sourceName") or "upload")

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
    d.setdefault("createdAt", _iso_now())

    # optional numeric/text fields
    d.setdefault("vendor", None)
    d.setdefault("date", None)
    d.setdefault("amount", None)
    d.setdefault("currency", None)
    d.setdefault("vat", None)
    d.setdefault("fraud_score", None)
    d.setdefault("language", None)
    d.setdefault("docType", None)

    return d

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_invoice(doc: Dict[str, Any]) -> str:
    """
    Create/append invoice document.
    Always coerces the input to the expected schema.
    """
    d = coerce_legacy(doc)
    uid = d.get("userId") or "anonymous"
    inv_id = d["id"]

    if FIREBASE_READY and DB is not None:
        DB.collection("invoices").document(inv_id).set(d)
        return inv_id

    # In-memory: append to the user's list + index by id
    MEM_BY_ID[inv_id] = d
    MEM_LIST.setdefault(uid, []).append(d)
    # newest first
    MEM_LIST[uid].sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)
    print(f"[store.mem] saved id={inv_id} for user={uid}; count={len(MEM_LIST[uid])}")
    return inv_id


def get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single invoice by id."""
    if FIREBASE_READY and DB is not None:
        snap = DB.collection("invoices").document(invoice_id).get()
        return snap.to_dict() if snap.exists else None
    return MEM_BY_ID.get(invoice_id)


def list_invoices_for_user(user_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    List invoices, optionally filtered by userId, newest first.
    """
    if FIREBASE_READY and DB is not None:
        q = DB.collection("invoices")
        if user_id:
            # New API preferred (no warnings); fallback to legacy where()
            if HAS_FIELD_FILTER:
                q = q.where(filter=FieldFilter("userId", "==", user_id))
            else:
                q = q.where("userId", "==", user_id)
        docs = [{**d.to_dict(), "id": d.id} for d in q.stream()]
        docs.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)
        return docs

    # In-memory
    if user_id:
        return list(MEM_LIST.get(user_id, []))

    # userId verilmediyse herkesin hepsi (flatten)
    all_docs: List[Dict[str, Any]] = []
    for arr in MEM_LIST.values():
        all_docs.extend(arr)
    all_docs.sort(key=lambda x: str(x.get("createdAt") or ""), reverse=True)
    return all_docs
