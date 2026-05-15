from datetime import date
import json
from . import database as db

def onerileri_hesapla(gemi_id: int, makine_tipi_id: int, hedef_tarih: date, cikan_yagci_id=None, limit=5) -> list:
    rows = db.sql_all("""
        SELECT p.*, g.ad as gemi_ad, m.ad as makine_ad
        FROM personel p
        JOIN gemi g ON g.id = p.gemi_id
        JOIN makine_tipi m ON m.id = p.makine_tipi_id
        WHERE p.aktif = 1 AND p.gemiden_cekilme = 0 AND p.carkci_ile_sorun = 0
    """)
    adaylar = [dict(r) for r in rows]

    for aday in adaylar:
        izin_kayit = db.sql_one("""
            SELECT COUNT(*) as cnt FROM izin
            WHERE personel_id = ? AND baslangic <= ? AND bitis >= ?
        """, (aday["id"], hedef_tarih.isoformat(), hedef_tarih.isoformat()))
        if izin_kayit and izin_kayit["cnt"] > 0:
            aday["uygun"] = False
            continue
        else:
            aday["uygun"] = True

        skor = 3.0
        skor += (aday.get("is_kalitesi", 3) - 3) * 0.5
        tutum_map = {"Mükemmel": 1.5, "İyi": 0.5, "Orta": 0, "Gelişmeli": -0.5}
        skor += tutum_map.get(aday.get("gemi_tutumu", "Orta"), 0)

        if aday.get("izin_tercih_gunleri"):
            try:
                tercih_gunler = json.loads(aday["izin_tercih_gunleri"])
                if isinstance(tercih_gunler, list) and hedef_tarih.weekday() in tercih_gunler:
                    skor += 1.0
            except Exception:
                pass

        if aday.get("durum_tipi") == "izinci":
            skor += 1.5

        if aday.get("vardiya_tipi") == "8_5":
            aday["uyari_8_5"] = True
        else:
            aday["uyari_8_5"] = False

        if aday.get("makine_tipi_id") == makine_tipi_id:
            skor += 0.5

        aday["skor"] = round(min(skor, 5.0), 2)

    uygunlar = [a for a in adaylar if a.get("uygun", False)]
    uygunlar.sort(key=lambda x: x["skor"], reverse=True)
    return uygunlar[:limit]

def to_dict_rows(oneri_list):
    out = []
    for o in oneri_list:
        out.append({
            "ad_soyad": f"{o['ad']} {o['soyad']}",
            "skor": o["skor"],
            "gemi": o.get("gemi_ad", ""),
            "makine": o.get("makine_ad", ""),
            "vardiya_tipi": o.get("vardiya_tipi", ""),
            "uyari_8_5": o.get("uyari_8_5", False)
        })
    return out
