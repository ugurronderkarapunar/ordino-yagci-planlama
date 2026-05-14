"""Sabitler ve sözlükler — UI ve backend tarafından paylaşılır."""

from __future__ import annotations

VARDIYA_SAATLERI: dict[str, tuple[str, str]] = {
    "SABIT": ("08:00", "08:00"),
    "GRUPCU": ("08:00", "08:00"),
    "IZINCI": ("08:00", "08:00"),
    "TERSANE": ("08:00", "17:00"),
    "8_5": ("08:00", "17:00"),
    "GECE": ("20:00", "08:00"),
}

GUNLER_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AY_ADLARI = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

VARDIYA_TIPLERI = ["SABIT", "GRUPCU", "IZINCI", "TERSANE", "8_5", "GECE"]
GEMI_KONUMLARI = ["Tersane", "Dışarıda", "Gecede", "Belirtilmedi"]
PERSONEL_DURUM = ["Gemide", "İskelede", "Raporlu"]

VARDIYA_RENKLERI = {
    "SABIT": "#3498db",
    "GRUPCU": "#2ecc71",
    "IZINCI": "#f39c12",
    "TERSANE": "#e74c3c",
    "8_5": "#9b59b6",
    "GECE": "#1abc9c",
}

VARDIYA_KONUM_ESLESME = {"TERSANE": "Tersane", "8_5": "Dışarıda"}

DEFAULT_AYARLAR: dict[str, int] = {
    "min_dinlenme_suresi_saat": 11,
    "max_haftalik_saat": 45,
    "yillik_izin_hakki": 14,
}

OLUMLU_KELIMELER = [
    "iyi",
    "çalışkan",
    "başarılı",
    "güvenilir",
    "hızlı",
    "dikkatli",
    "özenli",
    "disiplinli",
    "yardımsever",
    "titiz",
    "profesyonel",
    "mükemmel",
    "harika",
    "süper",
    "efsane",
    "gayretli",
    "istekli",
    "düzenli",
    "sorumlu",
    "kooperatif",
]

OLUMSUZ_KELIMELER = [
    "kötü",
    "berbat",
    "yetersiz",
    "tembel",
    "sorunlu",
    "problemli",
    "geç kalıyor",
    "işe yaramaz",
    "ilgisiz",
    "dikkatsiz",
    "başarısız",
    "yavaş",
    "isteksiz",
    "uyumsuz",
    "şikayet",
    "kavga",
    "saygısız",
    "sorumsuz",
    "eksik",
    "hatalı",
    "verimsiz",
    "güvenilmez",
    "disiplinsiz",
    "özensiz",
]

AGIR_OLUMSUZ_KELIMELER = ["berbat", "işe yaramaz", "güvenilmez", "disiplinsiz", "kovulmalı", "kesinlikle çalışmaz"]
