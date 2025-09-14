# backend/chat.py
"""
Chat router for Invoice AI MVP (English-only).
- Answers analytics-like questions on a user's invoices
- Optional LLM support via OpenRouter (OPENROUTER_API_KEY)
- Exposes: POST /chat
"""

from __future__ import annotations

import os
import re
import json
import base64
import calendar
from io import StringIO
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from store import list_invoices_for_user, coerce_legacy

router = APIRouter()

# ---------------- Pydantic models ----------------
class InvoiceOut(BaseModel):
    id: str
    userId: str
    filename: str
    ocr_text: List[str] = []
    vendor: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    vat: Optional[float] = None
    fraud_score: Optional[float] = None
    createdAt: Optional[str] = None
    language: Optional[str] = None
    docType: Optional[str] = None


class ChatRequest(BaseModel):
    userId: str
    question: str


class ChatResponse(BaseModel):
    answer: str
    invoices: Optional[List[InvoiceOut]] = None
    csv_base64: Optional[str] = None


# ---------------- Month parsing helpers (EN only) ----------------
MONTHS_MAP_EN = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
ABBR_MAP_EN   = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

def parse_month(query: str) -> Optional[Tuple[int, int]]:
    """Extract (year, month) from English query: “this/last month”, “Aug 2025”, “August”"""
    q = query.lower()
    now = datetime.utcnow()

    if "this month" in q:
        return (now.year, now.month)
    if "last month" in q:
        prev = (now.replace(day=1) - timedelta(days=1))
        return (prev.year, prev.month)

    for name, mi in MONTHS_MAP_EN.items():
        if name in q:
            m = re.search(rf"{name}\s+(\d{{4}})", q)
            return (int(m.group(1)) if m else now.year, mi)

    for name, mi in ABBR_MAP_EN.items():
        if name and name in q:
            m = re.search(rf"{name}\s+(\d{{4}})", q)
            return (int(m.group(1)) if m else now.year, mi)

    return None


def filter_by_month(invs: List[Dict[str, Any]], y: int, m: int) -> List[Dict[str, Any]]:
    """Filter invoices by month using 'date' (dd.mm.yyyy, etc.) or 'createdAt' ISO."""
    out: List[Dict[str, Any]] = []
    for d in invs:
        dt = d.get("date")
        try:
            if dt and re.match(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", dt):
                dd, mm, yy = re.split(r"[./-]", dt)[:3]
                if len(yy) == 2:
                    yy = "20" + yy
                if int(yy) == y and int(mm) == m:
                    out.append(d)
                    continue
        except Exception:
            pass

        ca = d.get("createdAt")
        try:
            if ca and int(ca[0:4]) == y and int(ca[5:7]) == m:
                out.append(d)
        except Exception:
            pass
    return out


def sum_amount(invs: List[Dict[str, Any]]) -> float:
    return round(sum((d.get("amount") or 0) for d in invs), 2)


def sum_vat(invs: List[Dict[str, Any]]) -> float:
    return round(sum((d.get("vat") or 0) for d in invs), 2)


def risky(invs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [d for d in invs if (d.get("fraud_score") or 0) >= 0.7]


def build_tax_csv(invs: List[Dict[str, Any]]) -> str:
    """Build a simple CSV for tax export (no quoting to keep it lightweight)."""
    buf = StringIO()
    buf.write("date,vendor,currency,amount,vat,filename\n")
    for d in invs:
        vendor = (d.get("vendor") or "").replace(",", " ")
        buf.write(
            f"{d.get('date') or ''},{vendor},{d.get('currency') or ''},"
            f"{d.get('amount') or ''},{d.get('vat') or ''},{d.get('filename') or ''}\n"
        )
    return buf.getvalue()


# ---------------- Optional LLM via OpenRouter ----------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_SITE = os.environ.get("OPENROUTER_SITE", "http://localhost:3000")
OPENROUTER_TITLE = os.environ.get("OPENROUTER_TITLE", "Invoice AI MVP")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Choose a model available on OpenRouter; gpt-4o-mini via OpenRouter alias:
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

def llm_answer(question: str, context: Dict[str, Any]) -> Optional[str]:
    """Ask an LLM via OpenRouter using only provided context; return text or None."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": OPENROUTER_SITE,
                "X-Title": OPENROUTER_TITLE,
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an assistant for an invoice dashboard. Answer concisely using only the provided JSON context.",
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nContext JSON:\n{json.dumps(context)[:4000]}",
                    },
                ],
                "temperature": 0.2,
            },
            timeout=30,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("[llm error]", e)
        return None


# ---------------- Route ----------------
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """
    Answers queries like:
      - "What invoices are risky this month?"
      - "Total spent in August 2025"
      - "Export my tax summary"
    """
    q = req.question.strip()
    docs = [coerce_legacy(d) for d in list_invoices_for_user(req.userId)]

    ctx = {
        "count": len(docs),
        "total_amount": sum_amount(docs),
        "total_vat": sum_vat(docs),
        "risky_count": len(risky(docs)),
        "sample": [
            {k: d.get(k) for k in ("id", "filename", "vendor", "date", "amount", "currency", "vat", "fraud_score")}
            for d in docs[:20]
        ],
    }

    ql = q.lower()

    # Risky invoices this month
    if "risky" in ql and "month" in ql:
        y, m = parse_month(q) or (datetime.utcnow().year, datetime.utcnow().month)
        sub = filter_by_month(docs, y, m)
        rsk = risky(sub)
        ans = f"{calendar.month_name[m]} {y} risky invoices: {len(rsk)}"
        return ChatResponse(answer=ans, invoices=[InvoiceOut(**d) for d in rsk])

    # Total spent in <Month>
    if "total" in ql and ("spent" in ql or "amount" in ql):
        ym = parse_month(q)
        if ym:
            y, m = ym
            sub = filter_by_month(docs, y, m)
            ans = f"Total spent in {calendar.month_name[m]} {y}: ${sum_amount(sub):,.2f}"
            return ChatResponse(answer=ans)
        return ChatResponse(answer=f"All-time total: ${ctx['total_amount']:,.2f}")

    # Export tax summary (CSV)
    if "export" in ql or "csv" in ql or "tax" in ql or "vat" in ql or "summary" in ql or "report" in ql:
        ym = parse_month(q)
        sub, label = (docs, "all-time")
        if ym:
            y, m = ym
            sub = filter_by_month(docs, y, m)
            label = f"{calendar.month_name[m]} {y}"
        csv_text = build_tax_csv(sub)
        b64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii")
        return ChatResponse(answer=f"Generated tax CSV for {label}.", csv_base64=b64)

    # Fallback to LLM (if configured)
    llm = llm_answer(q, ctx)
    if llm:
        return ChatResponse(answer=llm)

    # Final fallback
    return ChatResponse(
        answer="I can answer: 'What invoices are risky this month', 'Total spent in <Month>', or 'Export my tax summary'."
    )