"""
Gelişmiş öneri motoru (v8 mantığı, Streamlit bağımlılığı yok).
Ayarlar dict ile min dinlenme / max haftalık saat parametreleri verilir.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src import database as db
from src.constants import (
    AGIR_OLUMSUZ_KELIMELER,
    DEFAULT_AYARLAR,
    OLUMLU_KELIMELER,
    OLUMSUZ_KELIMELER,
    VARDIYA_KONUM_ESLESME,
    VARDIYA_SAATLERI,
)
from src.json_utils import id_listesi
from src.services import planning_service as ps
from src.time_utils import saat_dakika, vardiya_suresi_dakika


def nlp_skor(metin: str) -> float:
    if not metin:
        return 0.0
    m = metin.lower()
    olumlu = sum(1 for k in OLUMLU_KELIMELER if k in m)
    olumsuz = sum(1 for k in OLUMSUZ_KELIMELER if k in m)
    agir = sum(1 for k in AGIR_OLUMSUZ_KELIMELER if k in m)
    top_ol = olumsuz + agir * 2
    if olumlu + top_ol == 0:
        return 0.0
    return (olumlu - top_ol) / max(olumlu + top_ol, 5)


def tum_aktif_personel():
    rows = db.sql_all(
        """
        SELECT * FROM personel
        WHERE aktif = 1
          AND (vardiya_tipi = 'IZINCI' OR IFNULL(durum, 'Gemide') IN ('Gemide', 'İskelede'))
        """
    )
    return rows


def onerileri_hesapla_v8(
    gemi_id: int,
    makine_tipi_id: int,
    hedef_tarih: date,
    cikan_id: int | None = None,
    limit: int = 5,
    esnek_cakisma: bool = False,
    ayarlar: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ayar = {**DEFAULT_AYARLAR, **(ayarlar or {})}
    min_din = int(ayar.get("min_dinlenme_suresi_saat", 11))
    max_saat = int(ayar.get("max_haftalik_saat", 45))

    mevcut = ps.vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut is not None:
        p = db.sql_one("SELECT id, ad, soyad, vardiya_tipi, is_kalitesi FROM personel WHERE id=?", (mevcut,))
        if p:
            return [
                {
                    **dict(p),
                    "puan": 999,
                    "uyari_8_5": p["vardiya_tipi"] == "8_5",
                    "zaten_atanmis": True,
                    "bas_saat": VARDIYA_SAATLERI.get(str(p["vardiya_tipi"]), ("08:00", "08:00"))[0],
                    "bit_saat": VARDIYA_SAATLERI.get(str(p["vardiya_tipi"]), ("08:00", "08:00"))[1],
                }
            ]

    tum = tum_aktif_personel()
    gemi_konum = ps.gemi_konumu(gemi_id)
    hedef_gun = hedef_tarih.weekday()
    izinli_ids = ps.bugun_izinli_ids(hedef_tarih)
    atama_dict = ps.tum_atamalar_by_tarih(hedef_tarih)

    sonuclar: list[dict[str, Any]] = []
    for p in tum:
        prow = dict(p)
        pid = int(prow["id"])
        if cikan_id and pid == cikan_id:
            continue
        if pid in izinli_ids:
            continue
        vardiya = str(prow.get("vardiya_tipi") or "SABIT")
        bas_saat, bit_saat = VARDIYA_SAATLERI.get(vardiya, ("08:00", "08:00"))
        bas_dk, bit_dk = saat_dakika(bas_saat), saat_dakika(bit_saat)
        if bit_dk <= bas_dk:
            bit_dk += 1440
        if pid in atama_dict:
            cakisma = False
            for a in atama_dict[pid]:
                a_bas, a_bit = saat_dakika(str(a["baslangic_saat"])), saat_dakika(str(a["bitis_saat"]))
                if a_bit <= a_bas:
                    a_bit += 1440
                if bas_dk < a_bit and a_bas < bit_dk:
                    cakisma = True
                    break
            if cakisma and not esnek_cakisma:
                continue
        if vardiya == "GECE" and gemi_konum != "Gecede":
            continue
        if vardiya in VARDIYA_KONUM_ESLESME and gemi_konum != VARDIYA_KONUM_ESLESME[vardiya]:
            continue
        if vardiya != "IZINCI":
            gunler_json = prow.get("vardiya_gunleri")
            if gunler_json:
                try:
                    import json

                    izin_gunler = json.loads(str(gunler_json))
                    if isinstance(izin_gunler, list) and izin_gunler and hedef_gun not in izin_gunler:
                        continue
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        mids = id_listesi(prow.get("makine_tipi_id_list"))
        if mids and makine_tipi_id not in mids:
            continue
        if mids and not ps.sertifika_gecerli_mi(pid, makine_tipi_id, hedef_tarih):
            continue
        gids = id_listesi(prow.get("gemi_id_list"))
        if prow.get("gemi_id"):
            gid0 = int(prow["gemi_id"])
            if gid0 not in gids:
                gids.append(gid0)
        if gids and gemi_id not in gids:
            continue
        if int(prow.get("carkci_ile_sorun") or 0):
            continue
        if not ps.dinlenme_suresi_kontrol(pid, hedef_tarih, bas_saat, min_din):
            continue
        ek_dk = vardiya_suresi_dakika(bas_saat, bit_saat)
        if ps.haftalik_calisma_saati(pid, hedef_tarih) + ek_dk / 60.0 > max_saat:
            continue

        nlp_puan = nlp_skor(str(prow.get("performans_notu") or "")) + nlp_skor(str(prow.get("carkci_sorun_notu") or ""))
        nlp_etki = nlp_puan * 25
        kalite = int(prow.get("is_kalitesi") or 3)
        kalite_puan = {1: -30, 2: -20, 3: 0, 4: 10, 5: 20}.get(kalite, 0)
        ust_uste_ceza = -20 if ps.iki_gun_ust_uste_mi(pid, hedef_tarih) else 0
        pespese_ceza = -15 if ps.ayni_gemi_pespese(pid, hedef_tarih, gemi_id) else 0
        vardiya_puan = {"IZINCI": 100, "TERSANE": 95, "GECE": 105, "GRUPCU": 80, "SABIT": 60, "8_5": 40}.get(vardiya, 50)
        toplam_puan = vardiya_puan + kalite_puan + nlp_etki + pespese_ceza + ust_uste_ceza
        if vardiya == "IZINCI":
            toplam_puan += 200
        sonuclar.append(
            {
                **prow,
                "puan": toplam_puan,
                "uyari_8_5": vardiya == "8_5",
                "zaten_atanmis": False,
                "bas_saat": bas_saat,
                "bit_saat": bit_saat,
            }
        )
    sonuclar.sort(key=lambda x: -float(x["puan"]))
    return sonuclar[:limit]


def to_dict_rows_v8(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for o in items:
        out.append(
            {
                "id": o.get("id"),
                "ad_soyad": f"{o.get('ad', '')} {o.get('soyad', '')}".strip(),
                "vardiya_tipi": o.get("vardiya_tipi"),
                "puan": o.get("puan"),
                "zaten_atanmis": o.get("zaten_atanmis", False),
                "uyari_8_5": o.get("uyari_8_5", False),
            }
        )
    return out
