"""
İş kuralları (özet):
- 8/5: aynı gün 08:00–17:00 (takvim günü).
- SABIT/GRUPCU: vardiya Pazartesi 08:00 başlar Salı 08:00 biter vb.; vardiya çıkışı sonrası gün 'off'.
- İzin vardiya gününde başlıyorsa 3 gün (Pzt→Pzt-Sal-Çar) takvime işlenir — arayüzde kullanıcı onaylar.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Iterable


def gun_sayisi(bas: date, bit: date) -> int:
    if bit < bas:
        return 0
    return (bit - bas).days + 1


def haftanin_gunu(d: date) -> int:
    """0=Pazartesi … 6=Pazar."""
    return (d.weekday()) % 7


def vardiya_calisma_gunu_mu(d: date, vardiya_gunleri_json: str | None) -> bool:
    if not vardiya_gunleri_json:
        return False
    try:
        gunler = json.loads(vardiya_gunleri_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(gunler, list):
        return False
    return haftanin_gunu(d) in gunler


def vardiya_cikisi_ertesi_off(d: date, vardiya_tipi: str, vardiya_gunleri_json: str | None) -> bool:
    """d günü, bir önceki takvim gününde bittiği vardiya çıkışı sonrası 'off' mu? (basit: dün çalışma günüydü ve gece vardiyası bitti)."""
    if vardiya_tipi == "8_5":
        return False
    dun = d - timedelta(days=1)
    return vardiya_calisma_gunu_mu(dun, vardiya_gunleri_json)


def izin_cakisiyor_mu(bas: date, bit: date, kontrol: date) -> bool:
    return bas <= kontrol <= bit


def izin_pzt_3gun(baslangic: date) -> tuple[date, date]:
    """Pazartesi vardiya günü izin örneği: Pzt–Sal–Çar."""
    return baslangic, baslangic + timedelta(days=2)
