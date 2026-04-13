"""
Yağcı öneri kuralları (puan 5 en iyi, 1 en kötü ölçeğinde skor).
Excel ile gemi/makine/personel senkronu sonraya bırakılabilir; tablolar SQLite'ta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src import database as db
from src.vardiya_kurallari import vardiya_cikisi_ertesi_off, vardiya_calisma_gunu_mu, izin_cakisiyor_mu


@dataclass
class OneriSatir:
    personel_id: int
    ad_soyad: str
    skor: int
    aciklama: str
    uyari_8_5: bool


def _izinli_mi(pid: int, d: date) -> bool:
    rows = db.sql_all(
        "SELECT baslangic, bitis FROM izin WHERE personel_id = ?",
        (pid,),
    )
    for r in rows:
        bas = date.fromisoformat(r["baslangic"])
        bit = date.fromisoformat(r["bitis"])
        if izin_cakisiyor_mu(bas, bit, d):
            return True
    return False


def onerileri_hesapla(
    gemi_id: int,
    makine_tipi_id: int,
    hedef_tarih: date,
    cikan_personel_id: int | None,
    limit: int = 5,
) -> list[OneriSatir]:
    q = """
        SELECT p.id, p.ad, p.soyad, p.vardiya_tipi, p.vardiya_gunleri, p.gemi_id,
               p.gemiden_cekilme, p.carkci_ile_sorun, m.ad AS makine_ad
        FROM personel p
        JOIN makine_tipi m ON m.id = p.makine_tipi_id
        WHERE p.aktif = 1
          AND p.makine_tipi_id = ?
          AND (p.id != ? OR ? IS NULL)
    """
    rows = db.sql_all(q, (makine_tipi_id, cikan_personel_id, cikan_personel_id))
    sonuc: list[OneriSatir] = []

    for r in rows:
        pid = int(r["id"])
        if int(r["gemiden_cekilme"]) == 1 or int(r["carkci_ile_sorun"]) == 1:
            continue
        if r["gemi_id"] is not None and int(r["gemi_id"]) != gemi_id:
            continue
        if _izinli_mi(pid, hedef_tarih):
            continue
        vt = str(r["vardiya_tipi"])
        vg = r["vardiya_gunleri"]
        if vt != "8_5":
            if vardiya_cikisi_ertesi_off(hedef_tarih, vt, vg):
                continue
            if not vardiya_calisma_gunu_mu(hedef_tarih, vg):
                continue
        # 8/5: aynı gün mesai; gece vardiya/off filtresi uygulanmaz (izin kontrolü yeterli)

        skor = 5
        aciklama: list[str] = []

        if vt == "8_5":
            aciklama.append("8/5 vardiya — gemi pratiğinde ek kontrol önerilir (uyarı).")

        if r["gemi_id"] is None:
            skor = min(skor, 4)
            aciklama.append("Henüz bu gemiye atanmamış; uyum kontrolü yapın.")

        if _izinli_mi(pid, hedef_tarih - timedelta(days=1)):
            skor = min(skor, 3)
            aciklama.append("Önceki gün izin bitişi yakın.")

        uyari_8_5 = vt == "8_5"
        sonuc.append(
            OneriSatir(
                personel_id=pid,
                ad_soyad=f"{r['ad']} {r['soyad']}",
                skor=max(1, skor),
                aciklama=" ".join(aciklama) if aciklama else "Kurallara uygun aday.",
                uyari_8_5=uyari_8_5,
            )
        )

    sonuc.sort(key=lambda x: -x.skor)
    return sonuc[:limit]


def to_dict_rows(items: list[OneriSatir]) -> list[dict[str, Any]]:
    return [
        {
            "personel_id": o.personel_id,
            "ad_soyad": o.ad_soyad,
            "skor": o.skor,
            "aciklama": o.aciklama,
            "uyari_8_5": o.uyari_8_5,
        }
        for o in items
    ]
