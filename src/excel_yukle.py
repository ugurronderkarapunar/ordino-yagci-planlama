"""Excel şablonu sen gönderince kolon eşlemesi burada genişletilir."""
from __future__ import annotations

import io
import pandas as pd

from src import database as db


def yukle_gemiler_ve_makineler(uploaded: io.BytesIO | None) -> tuple[int, int]:
    """Şimdilik: 'Gemi' sayfası GemiAdi, 'Makine' sayfası MakineAdi kolonlarını bekler."""
    if uploaded is None:
        return 0, 0
    xls = pd.ExcelFile(uploaded)
    g, m = 0, 0
    if "Gemi" in xls.sheet_names:
        df = pd.read_excel(xls, "Gemi")
        col = next((c for c in df.columns if str(c).lower().replace("ı", "i") in ("gemiadi", "gemi_adi", "ad")), df.columns[0])
        for v in df[col].dropna().astype(str).unique():
            db.sql_run("INSERT OR IGNORE INTO gemi(ad, kod) VALUES (?, ?)", (v, v[:12]))
            g += 1
    if "Makine" in xls.sheet_names:
        df = pd.read_excel(xls, "Makine")
        col = next((c for c in df.columns if "makine" in str(c).lower() or "tip" in str(c).lower()), df.columns[0])
        for v in df[col].dropna().astype(str).unique():
            db.sql_run("INSERT OR IGNORE INTO makine_tipi(ad) VALUES (?)", (v,))
            m += 1
    return g, m


def ornek_sablon() -> bytes:
    """Boş şablon indirmek için."""
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        pd.DataFrame({"GemiAdi": ["ORNEK-1", "ORNEK-2"]}).to_excel(w, sheet_name="Gemi", index=False)
        pd.DataFrame({"MakineAdi": ["TIP-A", "TIP-B"]}).to_excel(w, sheet_name="Makine", index=False)
    return bio.getvalue()
