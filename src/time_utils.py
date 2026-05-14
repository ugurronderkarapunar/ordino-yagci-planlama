"""Saat aralığı ve çakışma hesapları (saf Python, test edilebilir)."""

from __future__ import annotations


def saat_dakika(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def saat_cakisiyor(bas1: str, bit1: str, bas2: str, bit2: str) -> bool:
    b1, e1 = saat_dakika(bas1), saat_dakika(bit1)
    b2, e2 = saat_dakika(bas2), saat_dakika(bit2)
    if e1 <= b1:
        e1 += 1440
    if e2 <= b2:
        e2 += 1440
    return b1 < e2 and b2 < e1


def vardiya_suresi_dakika(bas_saat: str, bit_saat: str) -> int:
    b, e = saat_dakika(bas_saat), saat_dakika(bit_saat)
    if e <= b:
        e += 1440
    return e - b
