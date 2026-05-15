"""Vardiya planı ve personel uygunluk sorguları."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src import database as db
from src.json_utils import id_listesi
from src.time_utils import saat_cakisiyor, saat_dakika, vardiya_suresi_dakika


def vardiya_plani_kontrol(gemi_id: int, makine_tipi_id: int, tarih: date) -> int | None:
    row = db.sql_one(
        "SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
        (gemi_id, makine_tipi_id, tarih.isoformat()),
    )
    return int(row["personel_id"]) if row else None


def saat_cakismasi_var(personel_id: int, tarih: date, bas_saat: str, bit_saat: str) -> bool:
    rows = db.sql_all(
        "SELECT baslangic_saat, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih=?",
        (personel_id, tarih.isoformat()),
    )
    return any(saat_cakisiyor(bas_saat, bit_saat, r["baslangic_saat"], r["bitis_saat"]) for r in rows)


def sertifika_gecerli_mi(personel_id: int, makine_tipi_id: int, kontrol_tarih: date) -> bool:
    return bool(
        db.sql_one(
            """
            SELECT id FROM personel_sertifika
            WHERE personel_id=? AND makine_tipi_id=?
              AND (gecerlilik_tarihi IS NULL OR gecerlilik_tarihi >= ?)
            """,
            (personel_id, makine_tipi_id, kontrol_tarih.isoformat()),
        )
    )


def iki_gun_ust_uste_mi(personel_id: int, tarih: date) -> bool:
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(db.sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND tarih=?", (personel_id, dun)))


def ayni_gemi_pespese(personel_id: int, tarih: date, gemi_id: int) -> bool:
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(
        db.sql_one(
            "SELECT id FROM vardiya_plan WHERE personel_id=? AND gemi_id=? AND tarih=?",
            (personel_id, gemi_id, dun),
        )
    )


def bugun_izinli_ids(bugun: date | None = None) -> set[int]:
    b = (bugun or date.today()).isoformat()
    return {int(r["personel_id"]) for r in db.sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (b,))}


def dinlenme_suresi_kontrol(personel_id: int, tarih: date, bas_saat: str, min_saat: int) -> bool:
    son = db.sql_one(
        """
        SELECT tarih, bitis_saat FROM vardiya_plan
        WHERE personel_id=? AND tarih < ?
        ORDER BY tarih DESC, bitis_saat DESC LIMIT 1
        """,
        (personel_id, tarih.isoformat()),
    )
    if not son:
        return True
    son_tarih = date.fromisoformat(str(son["tarih"]))
    bit_dk = saat_dakika(str(son["bitis_saat"]))
    bas_dk = saat_dakika(bas_saat)
    if son_tarih == tarih:
        if bas_dk < bit_dk:
            bas_dk += 1440
        fark = (bas_dk - bit_dk) / 60.0
    else:
        fark = ((tarih - son_tarih).days * 1440 + (bas_dk - bit_dk)) / 60.0
    return fark >= float(min_saat)


def haftalik_calisma_saati(personel_id: int, bitis_tarihi: date) -> float:
    hafta_basi = bitis_tarihi - timedelta(days=bitis_tarihi.weekday())
    hafta_sonu = hafta_basi + timedelta(days=6)
    rows = db.sql_all(
        "SELECT baslangic_saat, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih BETWEEN ? AND ?",
        (personel_id, hafta_basi.isoformat(), hafta_sonu.isoformat()),
    )
    toplam = 0
    for r in rows:
        toplam += vardiya_suresi_dakika(str(r["baslangic_saat"]), str(r["bitis_saat"]))
    return toplam / 60.0


def bugun_plani_olustur(bugun: date | None = None) -> list[dict[str, str]]:
    d = (bugun or date.today()).isoformat()
    atananlar = db.sql_all(
        """
        SELECT g.ad AS gemi, m.ad AS makine, p.ad || ' ' || p.soyad AS personel
        FROM vardiya_plan v
        JOIN gemi g ON v.gemi_id = g.id
        JOIN makine_tipi m ON v.makine_tipi_id = m.id
        JOIN personel p ON v.personel_id = p.id
        WHERE v.tarih = ?
        """,
        (d,),
    )
    tum_pozisyonlar = db.sql_all(
        """
        SELECT g.ad AS gemi, m.ad AS makine
        FROM gemi_makine gm
        JOIN gemi g ON gm.gemi_id = g.id
        JOIN makine_tipi m ON gm.makine_tipi_id = m.id
        ORDER BY g.ad, m.ad
        """
    )
    atanan_map = {(r["gemi"], r["makine"]): r["personel"] for r in atananlar}
    plan: list[dict[str, str]] = []
    for poz in tum_pozisyonlar:
        key = (poz["gemi"], poz["makine"])
        plan.append({"Gemi": poz["gemi"], "Makine": poz["makine"], "Personel": atanan_map.get(key, "⚠️ BOŞ")})
    return plan


def tum_atamalar_by_tarih(hedef_tarih: date) -> dict[int, list[dict[str, Any]]]:
    tum = db.sql_all(
        "SELECT personel_id, baslangic_saat, bitis_saat FROM vardiya_plan WHERE tarih=?",
        (hedef_tarih.isoformat(),),
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for a in tum:
        pid = int(a["personel_id"])
        out.setdefault(pid, []).append(dict(a))
    return out


def gemi_konumu(gemi_id: int) -> str | None:
    row = db.sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,))
    return str(row["konum"]) if row and row["konum"] is not None else None
