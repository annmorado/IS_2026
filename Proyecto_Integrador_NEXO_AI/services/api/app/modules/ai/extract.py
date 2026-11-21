"""Grounded deterministic extraction baseline, *not* a trained model.

Every field carries an exact source substring or is marked pending. The model
reuses the company's catalog only; nothing inferred becomes a confirmed order.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

VERSION = "extract_rules_es_1.0"
FIELDS = ("product", "quantity", "unit_price_mxn", "requested_date", "notes")
NUMBER = r"(?:\d{1,8}(?:[.,]\d{1,3})?)"
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
QTY_RE = re.compile(r"(?i)\b(?:cantidad|pedir|necesito|quiero|ordenar|preparar|pedido\s+de)\s*[:=]?\s*(?P<num>" + NUMBER + r")\b")
QTY_UNIT_RE = re.compile(r"(?i)\b(?P<num>"+NUMBER+r")\s*(?:piezas?|unidades?|uds?|cajas?|pasteles?|playeras?)\b")
PRICE_RE = re.compile(r"(?i)\b(?:precio\s+(?:unitario\s+)?|a\s+|por\s+)\$?\s*(?P<num>"+NUMBER+r")\s*(?:mxn|pesos)?\b")
PRICE_DOLLAR_RE = re.compile(r"(?i)\$\s*(?P<num>"+NUMBER+r")\s*(?:mxn|pesos)?\b")
NOTE_RE = re.compile(r"(?i)\b(?:nota|notas|observaci[oó]n(?:es)?|detalle(?:s)?)\s*:\s*(?P<note>[^\n.;]{2,240})")


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def field(value=None, *, source=None, start=None, end=None, confidence=None):
    if value is None:
        return {"value": None, "origin": "pending", "source_fragment": None,
                "span": None, "confidence": None}
    return {"value": value, "origin": "indicated", "source_fragment": source,
            "span": [start, end], "confidence": confidence}


def _number(m, *, quantity=False):
    raw = m.group("num").replace(",", ".")
    try:
        x = Decimal(raw)
    except InvalidOperation:
        return None
    if not x.is_finite() or x < 0 or (quantity and x == 0):
        return None
    return format(x, "f")


def extract_fields(text: str, catalog: list[dict]) -> dict:
    if not text or not text.strip() or len(text)>5000:
        raise ValueError("Texto de 1 a 5000 caracteres requerido")
    result={k:field() for k in FIELDS}
    # A named catalog item must appear verbatim modulo accents/case; ambiguous
    # matches remain pending, not a silent arbitrary SKU guess.
    simplified=normalize(text)
    found=[]
    for item in catalog:
        for needle in (item.get("name", ""), item.get("sku", "")):
            if not needle or len(needle)<3:continue
            token=normalize(needle)
            match=re.search(r"(?<!\w)"+re.escape(token)+r"(?!\w)",simplified)
            if match:
                found.append((len(token),match.start(),match.end(),item))
    if found:
        found.sort(key=lambda x:(-x[0],x[1]))
        best=found[0]
        if not any(x[0]==best[0] and x[3]["id"]!=best[3]["id"] for x in found):
            result["product"]=field({"id":str(best[3]["id"]),"name":best[3]["name"]},
                                   source=text[best[1]:best[2]],start=best[1],end=best[2],confidence=None)
    m=QTY_RE.search(text) or QTY_UNIT_RE.search(text)
    if m:
        val=_number(m, quantity=True)
        if val is not None:
            a,b=m.span("num");result["quantity"]=field(val,source=text[a:b],start=a,end=b)
    m=PRICE_RE.search(text) or PRICE_DOLLAR_RE.search(text)
    if m:
        val=_number(m)
        if val is not None:
            a,b=m.span("num");result["unit_price_mxn"]=field(val,source=text[a:b],start=a,end=b)
    for m in DATE_RE.finditer(text):
        try:
            parsed=date.fromisoformat(m.group(0))
        except ValueError:continue
        result["requested_date"]=field(parsed.isoformat(),source=m.group(0),start=m.start(),end=m.end())
        break
    m=NOTE_RE.search(text)
    if m:
        a,b=m.span("note");v=text[a:b].strip();result["notes"]=field(v,source=text[a:b],start=a,end=b)
    return {"engine_version":VERSION,"engine_kind":"deterministic_baseline_not_trained",
            "review_required":True,"fields":result,
            "pending_fields":[k for k,v in result.items() if v["origin"]=="pending"]}
