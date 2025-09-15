# backend/main.py
# FastAPI backend for Invoice AI MVP (frontend-compatible fields)
# - Uses store.py for persistence (Firestore or in-memory)
# - OCR (PDF/Image) via Tesseract
# - Simple extraction + language + type + fraud + VAT guess
# - Endpoints: /upload_invoice, /invoices, /users/sync, /users/logins, /chat

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import io, os, re, uuid, tempfile

from PIL import Image, UnidentifiedImageError
import pytesseract
from pdf2image import convert_from_path

# Optional language detection
try:
    from langdetect import detect as lang_detect
except Exception:
    lang_detect = None

# Use the single persistence layer from store.py
from store import (
    DB as STORE_DB,
    FIREBASE_READY as STORE_FIREBASE_READY,
    MEM_STORE as STORE_MEM,
    save_invoice,
    get_invoice,
    list_invoices_for_user,
    coerce_legacy,
)

# Optional: chat router (LLM + local Q&A)
from chat import router as chat_router

# ------------------------------------------------------------------------------
# App / CORS
# ------------------------------------------------------------------------------
app = FastAPI(title="Invoice AI MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",                         # Local dev için
        "http://127.0.0.1:3000",                         # Local dev için
        "https://invoice-ai-mvp-pf77.vercel.app",        # Senin canlı frontend domainin
        "https://*.vercel.app"                           # Opsiyonel: tüm vercel.app domainleri
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# Models (match frontend)
# ------------------------------------------------------------------------------
class InvoiceOut(BaseModel):
    id: str
    userId: str
    filename: str
    ocr_text: List[str]
    vendor: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    vat: Optional[float] = None
    fraud_score: Optional[float] = None
    createdAt: Optional[str] = None
    language: Optional[str] = None   # ISO-639-1 (e.g. 'en')
    docType: Optional[str] = None    # 'recurring' | 'service' | 'product' | 'other'

class UserIn(BaseModel):
    userId: str
    email: Optional[str] = None
    displayName: Optional[str] = None

class LoginEvent(BaseModel):
    userId: str
    ts: str
    userAgent: Optional[str] = None
    type: Optional[str] = "login"

# ------------------------------------------------------------------------------
# OCR helpers
# ------------------------------------------------------------------------------
def _open_image_resilient(content: bytes) -> Image.Image:
    """Open image from bytes; fallback to temp file; normalize mode."""
    try:
        img = Image.open(io.BytesIO(content))
    except UnidentifiedImageError:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            img = Image.open(tmp_path)
        finally:
            os.unlink(tmp_path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img

def ocr_bytes_to_texts(data: bytes, filename: Optional[str] = None) -> list[str]:
    """
    Bytes içeriği (PDF/PNG/JPG) OCR eder.
    PDF ise geçici dosyaya yazıp convert_from_path ile sayfalara çevirir.
    Görsellerde direkt pytesseract uygulanır.
    """
    texts: list[str] = []
    name = (filename or "").lower()

    try:
        if name.endswith(".pdf"):
            # PDF → temp dosya → sayfa resimleri
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tf:
                tf.write(data)
                tf.flush()
                pages = convert_from_path(tf.name, 300)  # poppler-utils gerekir
            for img in pages:
                txt = pytesseract.image_to_string(img)
                if txt:
                    texts.append(txt)
        else:
            # PNG/JPG → direkt
            img = _open_image_resilient(data)
            txt = pytesseract.image_to_string(img)
            if txt:
                texts.append(txt)
    except UnidentifiedImageError:
        # görüntü tanınmadı
        pass

    return texts

# ------------------------------------------------------------------------------
# AI helpers (lang, type, parsers, fraud, VAT)
# ------------------------------------------------------------------------------
def detect_language(text: str) -> Optional[str]:
    """Detect language of the text and return ISO-639-1 code."""
    if not text:
        return None
    try:
        if lang_detect:
            return lang_detect(text)
    except Exception:
        pass
    return None

def classify_doc_type(text: str) -> str:
    """Simple invoice classifier."""
    t = text.lower()
    if any(w in t for w in ["subscription", "monthly", "recurring"]):
        return "recurring"
    if any(w in t for w in ["consulting", "service", "maintenance"]):
        return "service"
    if any(w in t for w in ["item", "product", "goods", "pcs", "sku", "unit price"]):
        return "product"
    return "other"

CURRENCY_SIGNS = {"€": "EUR", "£": "GBP", "$": "USD"}
DATE_PAT = re.compile(r"(\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b)")
AMOUNT_PAT = re.compile(r"(?<!\w)(?:USD|EUR|GBP|\$|€|£)?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)")

def detect_currency(text: str) -> Optional[str]:
    for sign, cur in CURRENCY_SIGNS.items():
        if sign in text:
            return cur
    for cur in ("EUR", "USD", "GBP", "TRY"):
        if cur in text:
            return cur
    return None

def parse_amount(text: str) -> Optional[float]:
    candidates = []
    compact = text.replace(" ", "")
    for m in AMOUNT_PAT.finditer(compact):
        raw = m.group(1)
        # normalize 1.234,56 vs 1,234.56
        if raw.count(",") > 0 and raw.count(".") > 0:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
        try:
            candidates.append(float(raw))
        except:
            pass
    return max(candidates) if candidates else None

def pick_vendor(text: str) -> Optional[str]:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(w in line.lower() for w in ["ltd", "limited", "inc", "gmbh", "company", "co."]):
            return line
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None

def fraud_score(text: str, amount: Optional[float]) -> float:
    score = 0.0
    red_flags = ["pay by gift card", "urgent", "wire immediately", "overdue fee 50%"]
    score += sum(1 for f in red_flags if f in text.lower()) * 0.2
    if amount is not None and amount > 10000:
        score += 0.3
    return round(min(score, 1.0), 2)

def vat_guess(currency: Optional[str], text: str, amount: Optional[float]) -> Optional[float]:
    """Return VAT amount (not rate) for MVP."""
    rate = None
    t = text.lower()
    if "vat" in t or "tax" in t or currency == "EUR":
        m = re.search(r"(\d{1,2}(?:\.\d)?)\s*%", t)
        rate = (float(m.group(1)) / 100.0) if m else 0.20
    if amount is not None and rate is not None:
        return round(amount * rate, 2)
    return None

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Hello Invoice AI MVP!"}

# Accept both with and without trailing slash
@app.post("/upload_invoice", response_model=InvoiceOut)
@app.post("/upload_invoice/", response_model=InvoiceOut)
async def upload_invoice_ep(
    file: UploadFile = File(...),
    userId: Optional[str] = Form(None),
    userId_q: Optional[str] = Query(None, alias="userId"),
):
    """Upload PDF/PNG/JPG, run OCR + simple AI pipeline, store structured result."""
    try:
        uid = userId or userId_q or "anonymous"

        # UploadFile içeriğini *async* okuyalım (Render/uvicorn ile daha stabil)
        data = await file.read()
        if not data:
            raise ValueError("Boş dosya alındı.")
        await file.seek(0)  # ileride tekrar okunursa sorun çıkmasın

        # OCR
        texts = ocr_bytes_to_texts(data, filename=file.filename)
        if not texts:
            raise ValueError("OCR içerik çıkaramadı (format/bağımlılık?).")

        merged = "\n".join(texts)

        currency = detect_currency(merged)
        amount = parse_amount(merged)
        vendor = pick_vendor(merged)
        date_val = None
        m = DATE_PAT.search(merged)
        if m:
            date_val = m.group(1)

        fscore = fraud_score(merged, amount)
        vat_amount = vat_guess(currency, merged, amount)
        language = detect_language(merged)
        doc_type = classify_doc_type(merged)

        doc_id = uuid.uuid4().hex
        created_iso = datetime.utcnow().isoformat() + "Z"

        doc = {
            "id": doc_id,
            "userId": uid,
            "filename": file.filename or "upload",
            "ocr_text": texts,
            "vendor": vendor,
            "date": date_val,
            "amount": amount,
            "currency": currency,
            "vat": vat_amount,
            "fraud_score": fscore,
            "createdAt": created_iso,
            "language": language,
            "docType": doc_type,
        }

        save_invoice(doc)
        return InvoiceOut(**doc)

    except Exception as e:
        # Render loglarında net görünsün:
        import traceback
        print("[/upload_invoice] ERROR:", repr(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"OCR/parse failed: {e}")
        
@app.get("/invoices", response_model=List[InvoiceOut])
def list_invoices_ep(userId: Optional[str] = Query(None, alias="userId")):
    """List invoices (optionally filtered by userId)."""
    try:
        docs = list_invoices_for_user(userId)
        coerced = [coerce_legacy(d) for d in docs]
        return [InvoiceOut(**d) for d in coerced]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"List failed: {e}")

@app.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice_by_id(invoice_id: str):
    doc = get_invoice(invoice_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return InvoiceOut(**coerce_legacy(doc))

# --- Users: profile upsert + login events -------------------------------------
@app.post("/users/sync")
def sync_user(u: UserIn):
    """Upsert user profile to Firestore/users/{uid} (or memory fallback)."""
    try:
        doc = {
            "email": u.email,
            "displayName": u.displayName,
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
        if STORE_FIREBASE_READY and STORE_DB is not None:
            STORE_DB.collection("users").document(u.userId).set(doc, merge=True)
        else:
            STORE_MEM[f"user::{u.userId}"] = doc
        return {"ok": True}
    except Exception as e:
        print("[/users/sync] error:", repr(e))
        raise HTTPException(status_code=500, detail=f"user sync failed: {e}")

@app.post("/users/logins")
def log_login(ev: LoginEvent):
    """Append a login/logout event to users/{uid}/logins (or memory fallback)."""
    try:
        if STORE_FIREBASE_READY and STORE_DB is not None:
            STORE_DB.collection("users").document(ev.userId)\
                .collection("logins").add({
                    "ts": ev.ts,
                    "userAgent": ev.userAgent,
                    "type": ev.type or "login",
                    "createdAt": datetime.utcnow().isoformat() + "Z",
                })
        else:
            STORE_MEM.setdefault(f"log::{ev.userId}", []).append(ev.dict())
        return {"ok": True}
    except Exception as e:
        print("[/users/logins] error:", repr(e))
        raise HTTPException(status_code=500, detail=f"logins failed: {e}")

# --- Chat router ---------------------------------------------------------------
app.include_router(chat_router)  # exposes POST /chat
