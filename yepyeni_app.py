"""
Ordino Yağcı Planlaması — v8.5
İyileştirmeler:
 - IZINCI puan dengesi (80 + 120 = 200 toplam)
 - "Saat çakışmasını yoksay" isimlendirme
 - Test verisi işlemleri (silerek / silmeden ekleme)
 - Tüm vardiya_plan INSERT'lerinde ON CONFLICT DO NOTHING (INSERT OR IGNORE)
"""
from __future__ import annotations

import json, sqlite3, calendar as _cal, shutil
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Tuple, Dict

import pandas as pd
import streamlit as st
from fpdf import FPDF

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# ---------- SABİTLER ----------
DB_PATH = Path(__file__).parent / "ordino.db"
YEDEK_DIR = Path(__file__).parent / "yedekler"
LOG_DIR = Path(__file__).parent / "logs"

VARDIYA_SAATLERI = {
    "SABIT":   ("08:00", "08:00"),
    "GRUPCU":  ("08:00", "08:00"),
    "IZINCI":  ("08:00", "08:00"),
    "TERSANE": ("08:00", "17:00"),
    "8_5":     ("08:00", "17:00"),
    "GECE":    ("20:00", "08:00"),
}
GUNLER_TR    = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
AY_ADLARI   = ["","Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
VARDIYA_TIPLERI = ["SABIT","GRUPCU","IZINCI","TERSANE","8_5","GECE"]
GEMI_KONUMLARI  = ["Tersane","Dışarıda","Gecede","Belirtilmedi"]
PERSONEL_DURUM  = ["Gemide","İskelede","Raporlu"]
VARDIYA_RENKLERI = {
    "SABIT":"#3498db","GRUPCU":"#2ecc71","IZINCI":"#f39c12",
    "TERSANE":"#e74c3c","8_5":"#9b59b6","GECE":"#1abc9c"
}
VARDIYA_KONUM_ESLESME = {"TERSANE":"Tersane","8_5":"Dışarıda"}
DEFAULT_AYARLAR = {
    "min_dinlenme_suresi_saat": 11,
    "max_haftalik_saat": 45,
    "yillik_izin_hakki": 14,
}

OLUMLU_KELIMELER = ["iyi","çalışkan","başarılı","güvenilir","hızlı","dikkatli","özenli",
                    "disiplinli","yardımsever","titiz","profesyonel","mükemmel","harika",
                    "süper","efsane","gayretli","istekli","düzenli","sorumlu","kooperatif"]
OLUMSUZ_KELIMELER = ["kötü","berbat","yetersiz","tembel","sorunlu","problemli","geç kalıyor",
                     "işe yaramaz","ilgisiz","dikkatsiz","başarısız","yavaş","isteksiz",
                     "uyumsuz","şikayet","kavga","saygısız","sorumsuz","eksik","hatalı",
                     "verimsiz","güvenilmez","disiplinsiz","özensiz"]
AGIR_OLUMSUZ_KELIMELER = ["berbat","işe yaramaz","güvenilmez","disiplinsiz","kovulmalı","kesinlikle çalışmaz"]

# ---------- VERİTABANI ----------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def sql_one(query, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], row)) if row else None

def sql_all(query, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

def sql_run(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()

def audit_log(kullanici: str, islem: str, detay: str):
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / "audit.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {kullanici} | {islem} | {detay}\n")

# ---------- YARDIMCI ----------
def btn(label, key, caption="", help_text="", **kwargs):
    if "type" not in kwargs:
        kwargs["type"] = "primary"
    clicked = st.button(label, key=key, help=help_text, **kwargs)
    if caption:
        st.caption(caption)
    return clicked

def saat_dakika(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m

def saat_cakisiyor(bas1, bit1, bas2, bit2) -> bool:
    b1, e1 = saat_dakika(bas1), saat_dakika(bit1)
    b2, e2 = saat_dakika(bas2), saat_dakika(bit2)
    if e1 <= b1: e1 += 1440
    if e2 <= b2: e2 += 1440
    return b1 < e2 and b2 < e1

def saat_cakismasi_var(pid, tarih, bas_saat, bit_saat):
    rows = sql_all(
        "SELECT baslangic_saat,bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih=?",
        (pid, tarih.isoformat()),
    )
    return any(saat_cakisiyor(bas_saat, bit_saat, r["baslangic_saat"], r["bitis_saat"]) for r in rows)

def yillik_izin_hesapla(pid: int, yil: int) -> Tuple[int, int]:
    p = sql_one("SELECT yillik_izin_hakki FROM personel WHERE id=?", (pid,))
    hak = p["yillik_izin_hakki"] if p and p["yillik_izin_hakki"] else DEFAULT_AYARLAR["yillik_izin_hakki"]
    rows = sql_all(
        "SELECT gun_sayisi FROM izin WHERE personel_id=? AND baslangic>=? AND bitis<=?",
        (pid, f"{yil}-01-01", f"{yil}-12-31"),
    )
    kullanilan = sum(r["gun_sayisi"] for r in rows) if rows else 0
    return kullanilan, hak

def nlp_skor(metin: str) -> float:
    if not metin: return 0.0
    m = metin.lower()
    olumlu   = sum(1 for k in OLUMLU_KELIMELER if k in m)
    olumsuz  = sum(1 for k in OLUMSUZ_KELIMELER if k in m)
    agir     = sum(1 for k in AGIR_OLUMSUZ_KELIMELER if k in m)
    top_ol   = olumsuz + agir * 2
    if olumlu + top_ol == 0: return 0.0
    return (olumlu - top_ol) / max(olumlu + top_ol, 5)

def _id_listesi(v):
    if not v: return []
    try:
        p = json.loads(v)
        return [int(x) for x in p] if isinstance(p, list) else [int(p)]
    except:
        return []

def _makine_id_json(lst): return json.dumps(lst)
def _gemi_id_json(lst):   return json.dumps(lst)
def gun_sayisi(bas, bit):  return (bit - bas).days + 1

def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    row = sql_one(
        "SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
        (gemi_id, makine_tipi_id, tarih.isoformat()),
    )
    return row["personel_id"] if row else None

def sertifika_gecerli_mi(pid, makine_tipi_id, kontrol_tarih):
    return bool(sql_one(
        "SELECT id FROM personel_sertifika WHERE personel_id=? AND makine_tipi_id=? AND (gecerlilik_tarihi IS NULL OR gecerlilik_tarihi >= ?)",
        (pid, makine_tipi_id, kontrol_tarih.isoformat()),
    ))

def iki_gun_ust_uste_mi(pid, tarih):
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND tarih=?", (pid, dun)))

def ayni_gemi_pespese(pid, tarih, gemi_id):
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND gemi_id=? AND tarih=?", (pid, gemi_id, dun)))

def bugun_izinli_ids():
    bugun = date.today().isoformat()
    return {r["personel_id"] for r in sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (bugun,))}

def sertifika_uyarilari_al():
    bugun = date.today()
    return sql_all(
        """SELECT p.ad, p.soyad, m.ad AS makine, s.sertifika_adi, s.gecerlilik_tarihi
           FROM personel_sertifika s
           JOIN personel p ON s.personel_id=p.id
           JOIN makine_tipi m ON s.makine_tipi_id=m.id
           WHERE s.gecerlilik_tarihi IS NOT NULL
             AND s.gecerlilik_tarihi >= ? AND s.gecerlilik_tarihi <= ?""",
        (bugun.isoformat(), (bugun + timedelta(days=30)).isoformat()),
    )

# ── N+1 düzeltmesi: tek JOIN sorgusuyla bugünün planı ──────────────────────
def bugun_plani_olustur():
    bugun = date.today().isoformat()
    atananlar = sql_all(
        """SELECT g.ad AS gemi, m.ad AS makine, p.ad||' '||p.soyad AS personel
           FROM vardiya_plan v
           JOIN gemi g ON v.gemi_id=g.id
           JOIN makine_tipi m ON v.makine_tipi_id=m.id
           JOIN personel p ON v.personel_id=p.id
           WHERE v.tarih=?""",
        (bugun,),
    )
    tum_pozisyonlar = sql_all(
        """SELECT g.ad AS gemi, m.ad AS makine
           FROM gemi_makine gm
           JOIN gemi g ON gm.gemi_id=g.id
           JOIN makine_tipi m ON gm.makine_tipi_id=m.id
           ORDER BY g.ad, m.ad"""
    )
    atanan_map = {(r["gemi"], r["makine"]): r["personel"] for r in atananlar}
    plan = []
    for poz in tum_pozisyonlar:
        key = (poz["gemi"], poz["makine"])
        plan.append({
            "Gemi": poz["gemi"],
            "Makine": poz["makine"],
            "Personel": atanan_map.get(key, "⚠️ BOŞ"),
        })
    return plan

def veritabani_yedekle():
    YEDEK_DIR.mkdir(exist_ok=True)
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_yolu = YEDEK_DIR / f"ordino_yedek_{zaman}.db"
    shutil.copy2(DB_PATH, yedek_yolu)
    return yedek_yolu

def _takvim_html(yil, ay, isaretli, koyu=True):
    son_gun = _cal.monthrange(yil, ay)[1]
    ilk = date(yil, ay, 1).weekday()
    bugun = date.today()
    bg = "#2b2b2b" if koyu else "#fff"
    tc = "#f0f0f0" if koyu else "#1a1a1a"
    css = (
        f"<style>.cal{{font-family:system-ui;max-width:400px;margin:0 auto;"
        f"background:{bg};border-radius:16px;padding:16px;}}"
        f".cal-title{{text-align:center;font-size:18px;font-weight:600;color:{tc};margin-bottom:12px;}}"
        f".cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}}"
        f".cal-hdr{{text-align:center;font-size:12px;font-weight:600;color:#aaa;padding:6px 0;}}"
        f".cal-cell{{text-align:center;padding:10px 2px;border-radius:10px;font-size:14px;font-weight:500;}}"
        f".cal-empty{{background:transparent;}}.cal-normal{{background:#3a3a3a;color:#ddd;}}"
        f".cal-izin{{background:#f3831f;color:#fff;font-weight:600;}}"
        f".cal-bugun{{background:#2b2b2b;color:#f3831f;border:2px solid #f3831f;font-weight:700;}}</style>"
    )
    html = css + f'<div class="cal"><div class="cal-title">{AY_ADLARI[ay]} {yil}</div><div class="cal-grid">'
    for g in ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]:
        html += f'<div class="cal-hdr">{g}</div>'
    for _ in range(ilk):
        html += '<div class="cal-cell cal-empty"></div>'
    for n in range(1, son_gun + 1):
        d = date(yil, ay, n)
        cls = "cal-izin" if d in isaretli else "cal-normal"
        if d == bugun: cls += " cal-bugun"
        html += f'<div class="cal-cell {cls}">{n}</div>'
    html += "</div></div>"
    return html

def _json_gunleri_metne(v):
    if not v: return "-"
    try:
        idx = json.loads(v)
        if not isinstance(idx, list): return "-"
        return ", ".join(GUNLER_TR[int(i)] for i in idx if 0 <= int(i) < 7) or "-"
    except:
        return "-"

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list"))
        makine_str = ", ".join(tum_mak.get(m, str(m)) for m in mids) if mids else "Tüm Makineler"
        rows.append({
            "id": o["id"],
            "ad_soyad": f"{o['ad']} {o['soyad']}",
            "vardiya": o.get("vardiya_tipi", "-"),
            "makine": makine_str,
            "puan": o["puan"],
            "zaten_atanmis": o.get("zaten_atanmis", False),
        })
    return rows

# ---------- ÖNERİ MOTORU (cache'li + toplu N+1 çözümü) ----------
@st.cache_data(ttl=60, show_spinner=False)
def _tum_aktif_personel_cache():
    return sql_all(
        "SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))"
    )

def _toplu_haftalik_calisma_saatleri(hedef_tarih: date) -> Dict[int, float]:
    hafta_basi = hedef_tarih - timedelta(days=hedef_tarih.weekday())
    hafta_sonu = hafta_basi + timedelta(days=6)
    rows = sql_all(
        """SELECT personel_id,
                  SUM(
                    CASE
                      WHEN CAST(SUBSTR(bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(bitis_saat,4,2) AS INTEGER)
                         > CAST(SUBSTR(baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(baslangic_saat,4,2) AS INTEGER)
                      THEN (CAST(SUBSTR(bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(bitis_saat,4,2) AS INTEGER))
                         - (CAST(SUBSTR(baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(baslangic_saat,4,2) AS INTEGER))
                      ELSE (CAST(SUBSTR(bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(bitis_saat,4,2) AS INTEGER))
                         - (CAST(SUBSTR(baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(baslangic_saat,4,2) AS INTEGER)) + 1440
                    END
                  ) AS toplam_dakika
           FROM vardiya_plan
           WHERE tarih BETWEEN ? AND ?
           GROUP BY personel_id""",
        (hafta_basi.isoformat(), hafta_sonu.isoformat()),
    )
    return {r["personel_id"]: r["toplam_dakika"] / 60.0 if r["toplam_dakika"] else 0.0 for r in rows}

def _toplu_son_vardiya_bitisleri(hedef_tarih: date) -> Dict[int, Tuple[date, int]]:
    rows = sql_all(
        """SELECT personel_id, tarih, bitis_saat
           FROM vardiya_plan v1
           WHERE tarih < ?
             AND (personel_id, tarih) IN (
                 SELECT personel_id, MAX(tarih)
                 FROM vardiya_plan
                 WHERE tarih < ?
                 GROUP BY personel_id
             )
           ORDER BY personel_id""",
        (hedef_tarih.isoformat(), hedef_tarih.isoformat()),
    )
    sonuc = {}
    for r in rows:
        son_tarih = date.fromisoformat(r["tarih"])
        bit_dk = saat_dakika(r["bitis_saat"])
        sonuc[r["personel_id"]] = (son_tarih, bit_dk)
    return sonuc

def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
    mevcut = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut:
        p = sql_one("SELECT id,ad,soyad,vardiya_tipi,is_kalitesi FROM personel WHERE id=?", (mevcut,))
        if p:
            return [{**p, "puan": 999, "uyari_8_5": p.get("vardiya_tipi") == "8_5", "zaten_atanmis": True}]

    tum = _tum_aktif_personel_cache()
    gemi_konum = (sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,)) or {}).get("konum")
    hedef_gun  = hedef_tarih.weekday()

    izinli_ids = {
        r["personel_id"]
        for r in sql_all(
            "SELECT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis",
            (hedef_tarih.isoformat(),),
        )
    }
    tum_atamalar = sql_all(
        "SELECT personel_id,baslangic_saat,bitis_saat FROM vardiya_plan WHERE tarih=?",
        (hedef_tarih.isoformat(),),
    )
    atama_dict: Dict[int, list] = {}
    for a in tum_atamalar:
        atama_dict.setdefault(a["personel_id"], []).append(a)

    haftalik_saatler = _toplu_haftalik_calisma_saatleri(hedef_tarih)
    son_vardiya_map = _toplu_son_vardiya_bitisleri(hedef_tarih)

    ayar    = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
    max_saat = ayar.get("max_haftalik_saat", 45)
    min_dinlenme_saat = ayar.get("min_dinlenme_suresi_saat", 11)
    sonuclar = []

    for p in tum:
        if cikan_id and p["id"] == cikan_id:            continue
        if p["id"] in izinli_ids:                        continue

        vardiya = p.get("vardiya_tipi", "")
        bas_saat, bit_saat = VARDIYA_SAATLERI.get(vardiya, ("08:00", "08:00"))
        bas_dk, bit_dk = saat_dakika(bas_saat), saat_dakika(bit_saat)
        if bit_dk <= bas_dk: bit_dk += 1440

        if p["id"] in atama_dict:
            cakisma = False
            for a in atama_dict[p["id"]]:
                a_bas, a_bit = saat_dakika(a["baslangic_saat"]), saat_dakika(a["bitis_saat"])
                if a_bit <= a_bas: a_bit += 1440
                if bas_dk < a_bit and a_bas < bit_dk:
                    cakisma = True
                    break
            if cakisma and not esnek_cakisma:
                continue

        if vardiya == "GECE" and gemi_konum != "Gecede":               continue
        if vardiya in VARDIYA_KONUM_ESLESME and gemi_konum != VARDIYA_KONUM_ESLESME[vardiya]: continue

        if vardiya != "IZINCI":
            gunler_json = p.get("vardiya_gunleri")
            if gunler_json:
                try:
                    izin_gunler = json.loads(gunler_json)
                    if isinstance(izin_gunler, list) and izin_gunler and hedef_gun not in izin_gunler:
                        continue
                except:
                    pass

        mids = _id_listesi(p.get("makine_tipi_id_list"))
        if mids and makine_tipi_id not in mids:                           continue
        if mids and not sertifika_gecerli_mi(p["id"], makine_tipi_id, hedef_tarih): continue

        gids = _id_listesi(p.get("gemi_id_list"))
        if p.get("gemi_id") and p["gemi_id"] not in gids:
            gids.append(p["gemi_id"])
        if gids and gemi_id not in gids:                                  continue
        if p.get("carkci_ile_sorun"):                                     continue

        son = son_vardiya_map.get(p["id"])
        if son:
            son_tarih, son_bit_dk = son
            if son_tarih == hedef_tarih:
                if bas_dk < son_bit_dk:
                    bas_dk_compare = bas_dk + 1440
                else:
                    bas_dk_compare = bas_dk
                fark = (bas_dk_compare - son_bit_dk) / 60.0
            else:
                fark = ((hedef_tarih - son_tarih).days * 1440 + (bas_dk - son_bit_dk)) / 60.0
            if fark < min_dinlenme_saat:
                continue

        mevcut_haftalik = haftalik_saatler.get(p["id"], 0.0)
        yeni_vardiya_saati = (bit_dk - bas_dk) / 60.0
        if mevcut_haftalik + yeni_vardiya_saati > max_saat:
            continue

        nlp_puan   = nlp_skor(p.get("performans_notu") or "") + nlp_skor(p.get("carkci_sorun_notu") or "")
        nlp_etki   = nlp_puan * 25
        kalite     = p.get("is_kalitesi") or 3
        kalite_puan = {1: -30, 2: -20, 3: 0, 4: 10, 5: 20}.get(kalite, 0)
        ust_uste_ceza = -20 if iki_gun_ust_uste_mi(p["id"], hedef_tarih) else 0
        pespese_ceza  = -15 if ayni_gemi_pespese(p["id"], hedef_tarih, gemi_id) else 0
        # IZINCI: vardiya puanı 80, bonus 120 → toplam 200 (önceki 300 yerine dengeli)
        vardiya_puan  = {"IZINCI": 80,"TERSANE": 95,"GECE": 105,"GRUPCU": 80,"SABIT": 60,"8_5": 40}.get(vardiya, 50)
        toplam_puan   = vardiya_puan + kalite_puan + nlp_etki + pespese_ceza + ust_uste_ceza
        if vardiya == "IZINCI": toplam_puan += 120

        sonuclar.append({
            **p,
            "puan": toplam_puan,
            "uyari_8_5": vardiya == "8_5",
            "zaten_atanmis": False,
            "bas_saat": bas_saat,
            "bit_saat": bit_saat,
        })

    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

# ---------- PDF ----------
class PDFRapor(FPDF):
    def header(self):
        self.set_font("Arial","B",12)
        self.cell(0,10,"Ordino Yagci Planlamasi - Rapor",0,1,"C")
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial","I",8)
        self.cell(0,10,f"Sayfa {self.page_no()}/{{nb}}",0,0,"C")

def pdf_rapor_olustur(tip="aylik_ozet", ay=None, yil=None, baslangic=None, bitis=None):
    pdf = PDFRapor()
    pdf.alias_nb_pages()
    pdf.add_page()
    def tr_en(t): return t.translate(str.maketrans("ığüşöçİĞÜŞÖÇ","igusocIGUSOC"))
    if tip == "aylik_ozet":
        if not ay:  ay  = date.today().month
        if not yil: yil = date.today().year
        bas = date(yil, ay, 1); son = date(yil, ay, _cal.monthrange(yil, ay)[1])
        pdf.set_font("Arial","B",14)
        pdf.cell(0,10,tr_en(f"Aylik Personel Ozeti - {AY_ADLARI[ay]} {yil}"),0,1,"C")
        pdf.ln(5)
        for p in sql_all("SELECT * FROM personel ORDER BY ad"):
            izin_gun = sum(
                max(0,(min(date.fromisoformat(i["bitis"]),son)-max(date.fromisoformat(i["baslangic"]),bas)).days+1)
                for i in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=? AND baslangic<=? AND bitis>=?",
                                 (p["id"],son.isoformat(),bas.isoformat()))
            )
            c = sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih BETWEEN ? AND ?",
                        (p["id"],bas.isoformat(),son.isoformat()))["c"]
            pdf.set_font("Arial","",10)
            pdf.cell(50,7,tr_en(f"{p['ad']} {p['soyad']}"),1)
            pdf.cell(30,7,str(c),1); pdf.cell(30,7,str(izin_gun),1); pdf.cell(30,7,str(c+izin_gun),1); pdf.ln()
    else:
        pdf.set_font("Arial","B",14); pdf.cell(0,10,"Vardiya Plani",0,1,"C"); pdf.ln(5)
        rows = sql_all(
            """SELECT v.tarih, g.ad AS gemi, m.ad AS makine, p.ad||' '||p.soyad AS personel
               FROM vardiya_plan v
               JOIN gemi g ON v.gemi_id=g.id
               JOIN makine_tipi m ON v.makine_tipi_id=m.id
               JOIN personel p ON v.personel_id=p.id
               WHERE v.tarih BETWEEN ? AND ? ORDER BY v.tarih DESC""",
            (baslangic.isoformat(), bitis.isoformat()),
        )
        pdf.set_font("Arial","",9)
        for r in rows:
            pdf.cell(35,7,r["tarih"],1); pdf.cell(45,7,tr_en(r["gemi"]),1)
            pdf.cell(40,7,tr_en(r["makine"]),1); pdf.cell(40,7,tr_en(r["personel"]),1); pdf.ln()
    path = Path(__file__).parent / f"rapor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(str(path))
    return path

# ---------- DB INIT ----------
def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS gemi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL, kod TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS makine_tipi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS gemi_makine (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gemi_id INTEGER NOT NULL, makine_tipi_id INTEGER NOT NULL,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE,
        UNIQUE(gemi_id,makine_tipi_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS personel (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL, soyad TEXT NOT NULL,
        gemi_id INTEGER, gemi_id_list TEXT, makine_tipi_id INTEGER, makine_tipi_id_list TEXT,
        vardiya_tipi TEXT, vardiya_gunleri TEXT, gemiden_cekilme INTEGER DEFAULT 0,
        carkci_ile_sorun INTEGER DEFAULT 0, carkci_sorun_notu TEXT,
        gemi_tutumu TEXT, izin_tercih_gunleri TEXT, izin_saat_araligi TEXT,
        is_kalitesi INTEGER, performans_notu TEXT, aktif INTEGER DEFAULT 1,
        durum TEXT DEFAULT 'Gemide', yillik_izin_hakki INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS izin (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        baslangic TEXT, bitis TEXT, gun_sayisi INTEGER, notlar TEXT, gunler_json TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS carkci (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT, soyad TEXT, gemi_id INTEGER,
        problemli_yagci_id INTEGER, sorun_metni TEXT, vardiya_notu TEXT,
        carkci_vardiya TEXT, vardiya_gunleri TEXT, puan_kirma INTEGER DEFAULT 0,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE SET NULL,
        FOREIGN KEY(problemli_yagci_id) REFERENCES personel(id) ON DELETE SET NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS vardiya_plan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        gemi_id INTEGER NOT NULL, makine_tipi_id INTEGER NOT NULL, tarih TEXT NOT NULL,
        baslangic_saat TEXT DEFAULT '08:00', bitis_saat TEXT DEFAULT '08:00',
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE,
        UNIQUE(personel_id,gemi_id,makine_tipi_id,tarih))""")
    c.execute("""CREATE TABLE IF NOT EXISTS personel_sertifika (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL, sertifika_adi TEXT, gecerlilik_tarihi TEXT, notlar TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS performans_gecmis (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        tarih TEXT NOT NULL, puan INTEGER NOT NULL, kaynak TEXT DEFAULT 'manuel',
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS vardiya_takas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        talep_eden_id INTEGER NOT NULL,
        karsi_personel_id INTEGER NOT NULL,
        talep_eden_tarih TEXT NOT NULL,
        karsi_tarih TEXT NOT NULL,
        durum TEXT DEFAULT 'Beklemede',
        notlar TEXT,
        olusturma_tarihi TEXT NOT NULL,
        FOREIGN KEY(talep_eden_id) REFERENCES personel(id),
        FOREIGN KEY(karsi_personel_id) REFERENCES personel(id))""")

    migration_map = {
        "gemi": {"konum": "TEXT"},
        "personel": {
            "durum": "TEXT DEFAULT 'Gemide'",
            "yillik_izin_hakki": "INTEGER",
            "performans_notu": "TEXT",
            "aktif": "INTEGER DEFAULT 1",
            "is_kalitesi": "INTEGER",
            "gemiden_cekilme": "INTEGER DEFAULT 0",
            "carkci_ile_sorun": "INTEGER DEFAULT 0",
            "carkci_sorun_notu": "TEXT",
            "gemi_tutumu": "TEXT",
            "izin_tercih_gunleri": "TEXT",
            "izin_saat_araligi": "TEXT",
        }
    }
    for table, columns in migration_map.items():
        cur = c.execute(f"PRAGMA table_info({table})")
        existing_cols = {row[1] for row in cur.fetchall()}
        for col, col_def in columns.items():
            if col not in existing_cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
    conn.commit()
    conn.close()

def test_verisi_olustur(sil=False):
    """Test verisi ekler. sil=True ise önce tüm tabloları temizler."""
    if sil:
        for t in ["vardiya_plan","personel_sertifika","performans_gecmis","carkci",
                  "izin","personel","gemi_makine","makine_tipi","gemi","vardiya_takas"]:
            sql_run(f"DELETE FROM {t}")
    gemiler = [
        ("KABATEPE","G101","Tersane"),("M/T ATLANTIC","G202","Gecede"),
        ("M/V BOGAZICI","G303","Dışarıda"),("T/S CINAR","G404","Tersane"),
        ("M/V DENIZ YILDIZI","G505","Gecede"),
    ]
    for ad,kod,konum in gemiler:
        try:
            sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(ad,kod,konum))
        except sqlite3.IntegrityError:
            pass  # already exists
    gemi_ids = [r["id"] for r in sql_all("SELECT id FROM gemi")]
    for m in ["Dizel Motor","Kompresor","Pompa","Jenerator"]:
        try:
            sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(m,))
        except sqlite3.IntegrityError:
            pass
    makine_ids = [r["id"] for r in sql_all("SELECT id FROM makine_tipi")]
    for gid,mids in [
        (gemi_ids[0],[makine_ids[0],makine_ids[1]]),
        (gemi_ids[1],[makine_ids[1],makine_ids[2],makine_ids[3]]),
        (gemi_ids[2],[makine_ids[0],makine_ids[2]]),
        (gemi_ids[3],[makine_ids[3]]),
        (gemi_ids[4],[makine_ids[0],makine_ids[1],makine_ids[2],makine_ids[3]]),
    ]:
        for mid in mids:
            try:
                sql_run("INSERT OR IGNORE INTO gemi_makine(gemi_id,makine_tipi_id) VALUES(?,?)",(gid,mid))
            except:
                pass
    personeller = [
        ("Ahmet","YILMAZ",[gemi_ids[0]],[makine_ids[0],makine_ids[1]],"SABIT",[0,2,4],4,"Gemide","çalışkan ve dikkatli"),
        ("Mehmet","DEMIR",[gemi_ids[1]],[makine_ids[1],makine_ids[2]],"GRUPCU",[1,3,5],3,"Gemide",""),
        ("Ali","KAYA",[],[],"IZINCI",[],5,"İskelede","yedek personel"),
        ("Veli","SAHIN",[gemi_ids[0]],[makine_ids[0]],"TERSANE",[0,2,4],2,"Gemide","biraz yavaş"),
        ("Ayse","CELIK",[gemi_ids[2]],[makine_ids[2]],"8_5",[0,1,2,3,4],4,"Gemide",""),
        ("Fatma","AYDIN",[gemi_ids[3]],[makine_ids[0],makine_ids[1]],"GECE",[0,1,2,3,4,5],3,"Gemide",""),
        ("Hasan","OZTURK",[gemi_ids[1]],[makine_ids[1]],"SABIT",[1,3,5],4,"Gemide","güvenilir"),
        ("Huseyin","ARSLAN",[gemi_ids[2]],[makine_ids[0],makine_ids[1],makine_ids[2]],"GRUPCU",[0,2,4],5,"Gemide","mükemmel"),
        ("YEDEK1","KISI",[],[],"IZINCI",[],3,"İskelede","evrensel yedek"),
        ("YEDEK2","KISI",[],[],"IZINCI",[],4,"İskelede","evrensel yedek"),
    ]
    for ad,soyad,gemi_list,makine_list,vardiya,gunler,kalite,durum,p_not in personeller:
        sql_run("INSERT OR IGNORE INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ad,soyad,gemi_list[0] if gemi_list else None,_gemi_id_json(gemi_list),
                 makine_list[0] if makine_list else None,_makine_id_json(makine_list),
                 vardiya,json.dumps(gunler),kalite,durum,p_not))
    p_map = {f"{p['ad']} {p['soyad']}": p["id"] for p in sql_all("SELECT id,ad,soyad FROM personel")}
    bugun = date.today()
    sql_run("INSERT OR IGNORE INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
            (p_map["Ahmet YILMAZ"],bugun.isoformat(),(bugun+timedelta(days=6)).isoformat(),7,"haftalık izin"))
    sql_run("INSERT OR IGNORE INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
            (p_map["Veli SAHIN"],(bugun-timedelta(days=1)).isoformat(),bugun.isoformat(),2,"kısa izin"))
    sql_run("INSERT OR IGNORE INTO personel_sertifika(personel_id,makine_tipi_id,sertifika_adi,gecerlilik_tarihi) VALUES(?,?,?,?)",
            (p_map["Mehmet DEMIR"],makine_ids[2],"Kompresor Yetkisi",(bugun+timedelta(days=30)).isoformat()))
    for pid in list(p_map.values())[:6]:
        for delta in range(14):
            d = bugun - timedelta(days=delta)
            sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                    (pid, gemi_ids[0], makine_ids[0], d.isoformat(), "08:00", "17:00"))
    st.success("Test verisi " + ("oluşturuldu (mevcut veriler korundu)." if not sil else "oluşturuldu (tüm veriler silindi)."))

# ---------- AYARLAR ----------
def ayarlar_sayfasi():
    st.subheader("⚙️ Ayarlar")
    ayar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
    min_din   = st.number_input("Minimum Dinlenme (saat)", value=ayar["min_dinlenme_suresi_saat"])
    max_hafta = st.number_input("Maks. Haftalık Çalışma (saat)", value=ayar["max_haftalik_saat"])
    izin_hakki = st.number_input("Yıllık İzin Hakkı (gün)", value=ayar["yillik_izin_hakki"])
    if btn("Kaydet", key="ayar_kaydet", caption="Ayarları günceller"):
        st.session_state.ayarlar = {
            "min_dinlenme_suresi_saat": min_din,
            "max_haftalik_saat": max_hafta,
            "yillik_izin_hakki": izin_hakki,
        }
        st.success("Ayarlar güncellendi.")

# ═══════════════════════════════════════════════════════
# SAYFA: YAPBOZ
# ═══════════════════════════════════════════════════════
def _sayfa_yapboz():
    st.subheader("🧩 İnteraktif Yapboz")
    c_tarih, c_btns = st.columns([3,1])
    with c_tarih:
        sec_tarih = st.date_input("Tarih", value=date.today(), key="yapboz_tarih")
    with c_btns:
        st.write("")
        hc1, hc2 = st.columns(2)
        if hc1.button("⬅️ Hafta", key="yapboz_hafta_geri"):
            st.session_state.yapboz_tarih = st.session_state.yapboz_tarih - timedelta(days=7)
            st.rerun()
        if hc2.button("Hafta ➡️", key="yapboz_hafta_ileri"):
            st.session_state.yapboz_tarih = st.session_state.yapboz_tarih + timedelta(days=7)
            st.rerun()

    gemiler    = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    tum_mak    = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not tum_mak:
        st.warning("Gemi ve makine ekleyin.")
        return

    col1, col2 = st.columns(2)
    with col1:
        if btn("🧹 Tüm Atamaları Temizle", key="yapboz_temizle",
               caption="Seçili tarihteki tüm vardiyaları siler",
               help_text="Tarihe ait tüm personel atamalarını kaldırır.", type="secondary"):
            sql_run("DELETE FROM vardiya_plan WHERE tarih=?", (sec_tarih.isoformat(),))
            audit_log("kullanıcı","temizle",f"tarih:{sec_tarih.isoformat()}")
            st.toast("Tüm atamalar temizlendi!", icon="🧹"); st.rerun()
    with col2:
        if btn("🤖 Hepsini Otomatik Doldur", key="yapboz_otomatik",
               caption="Sistemin önerdiği en uygun personelle boşlukları doldurur",
               help_text="Boş pozisyonları öneri motoru ile doldurur."):
            with st.spinner("Otomatik dolduruluyor..."):
                for gemi in gemiler:
                    for gm in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],)):
                        mak_id = gm["makine_tipi_id"]
                        if not vardiya_plani_kontrol(gemi["id"], mak_id, sec_tarih):
                            oneri = onerileri_hesapla(gemi["id"], mak_id, sec_tarih, limit=1)
                            if oneri and not oneri[0].get("zaten_atanmis"):
                                b, e = VARDIYA_SAATLERI.get(oneri[0]["vardiya_tipi"], ("08:00","08:00"))
                                sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                        (oneri[0]["id"],gemi["id"],mak_id,sec_tarih.isoformat(),b,e))
            st.toast("Tüm boş pozisyonlar dolduruldu!", icon="🤖"); st.rerun()

    izinli = bugun_izinli_ids()
    tum_personel_cache = _tum_aktif_personel_cache()

    for gemi in gemiler:
        gemi_mak = sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],))
        if not gemi_mak:
            continue
        g_mak_ids = {r["makine_tipi_id"] for r in gemi_mak}
        g_makineler = [m for m in tum_mak if m["id"] in g_mak_ids]

        atanan_count = sql_one(
            "SELECT COUNT(*) AS c FROM vardiya_plan WHERE gemi_id=? AND tarih=?",
            (gemi["id"], sec_tarih.isoformat()),
        )["c"]
        toplam_poz = len(g_makineler)
        doluluk_emoji = "✅" if atanan_count == toplam_poz else ("🟡" if atanan_count > 0 else "🔴")

        with st.expander(
            f"{doluluk_emoji} {gemi['ad']} — {atanan_count}/{toplam_poz} dolu",
            expanded=(atanan_count < toplam_poz),
        ):
            max_kolon = 4
            for satir_idx in range(0, len(g_makineler), max_kolon):
                satir_makineler = g_makineler[satir_idx:satir_idx+max_kolon]
                cols = st.columns(len(satir_makineler))
                for i, mak in enumerate(satir_makineler):
                    with cols[i]:
                        mevcut = vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih)
                        st.markdown(f"**{mak['ad']}**")
                        if mevcut:
                            p = sql_one("SELECT id,ad,soyad,vardiya_tipi,durum,is_kalitesi FROM personel WHERE id=?", (mevcut,))
                            if p:
                                renk    = VARDIYA_RENKLERI.get(p["vardiya_tipi"],"#3a3a4e")
                                opacity = {1:0.5,2:0.6,3:0.75,4:0.9,5:1.0}.get(p["is_kalitesi"] or 3, 0.8)
                                st.markdown(
                                    f"<div style='background:{renk};padding:8px;border-radius:8px;"
                                    f"color:white;text-align:center;font-weight:bold;opacity:{opacity}'>"
                                    f"{p['ad']} {p['soyad']}<br>({p['vardiya_tipi']}) {p.get('durum','')}"
                                    f"<br>⭐{p['is_kalitesi']}</div>",
                                    unsafe_allow_html=True,
                                )
                            cx, cd = st.columns(2)
                            with cx:
                                if btn("❌ Çıkar", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}",
                                       caption="", help_text="Bu personeli vardiyadan çıkarır"):
                                    sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
                                            (gemi["id"],mak["id"],sec_tarih.isoformat()))
                                    st.toast("Personel çıkarıldı",icon="❌"); st.rerun()
                            with cd:
                                if btn("🔄 Değiştir", key=f"deg_{gemi['id']}_{mak['id']}_{sec_tarih}",
                                       caption="", help_text="Çıkarıp yeni öneri getirir"):
                                    sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",
                                            (gemi["id"],mak["id"],sec_tarih.isoformat()))
                                    st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = \
                                        onerileri_hesapla(gemi["id"],mak["id"],sec_tarih,limit=5)
                                    st.rerun()
                        else:
                            st.warning("⚠️ Boş")
                            hedef_gun = sec_tarih.weekday()
                            uygun = ["Seçiniz..."]
                            for p in tum_personel_cache:
                                if p["id"] in izinli: continue
                                if p["vardiya_tipi"] != "IZINCI":
                                    gj = p.get("vardiya_gunleri")
                                    if gj:
                                        try:
                                            il = json.loads(gj)
                                            if isinstance(il,list) and il and hedef_gun not in il: continue
                                        except: pass
                                mids = _id_listesi(p.get("makine_tipi_id_list"))
                                if mids and mak["id"] not in mids: continue
                                if mids and not sertifika_gecerli_mi(p["id"],mak["id"],sec_tarih): continue
                                gids = _id_listesi(p.get("gemi_id_list"))
                                if p.get("gemi_id"): gids.append(p["gemi_id"])
                                if gids and gemi["id"] not in gids: continue
                                if p.get("carkci_ile_sorun"): continue
                                uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum','')})")

                            if len(uygun) > 1:
                                sec = st.selectbox("Manuel Seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                                if sec != "Seçiniz...":
                                    pid_row = sql_one("SELECT id,vardiya_tipi FROM personel WHERE ad||' '||soyad=?",
                                                      (sec.split(" (")[0],))
                                    if pid_row:
                                        b, e = VARDIYA_SAATLERI.get(pid_row["vardiya_tipi"],("08:00","08:00"))
                                        if iki_gun_ust_uste_mi(pid_row["id"],sec_tarih):
                                            st.warning("⚠️ Bu personel dün de çalıştı.")
                                        sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                (pid_row["id"],gemi["id"],mak["id"],sec_tarih.isoformat(),b,e))
                                        st.toast("Personel atandı!"); st.rerun()
                            else:
                                st.caption("Uygun personel yok.")

                            if btn("🔍 Öneri Al (5)", key=f"onerbtn_{gemi['id']}_{mak['id']}_{sec_tarih}",
                                   caption="En uygun 5 personeli listeler",
                                   help_text="Öneri motoru ile en uygun 5 kişi"):
                                st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = \
                                    onerileri_hesapla(gemi["id"],mak["id"],sec_tarih,limit=5)
                                st.rerun()

                            key_on = f"oneriler_{gemi['id']}_{mak['id']}"
                            if key_on in st.session_state and st.session_state[key_on]:
                                st.markdown("**Önerilen:**")
                                for o in st.session_state[key_on]:
                                    co1, co2 = st.columns([4,1])
                                    with co1:
                                        st.write(f"{o['ad']} {o['soyad']} ({o['vardiya_tipi']}) — {o['puan']}")
                                    with co2:
                                        if btn("✅ Ata", key=f"ata_{gemi['id']}_{mak['id']}_{o['id']}",
                                               caption="", help_text="Bu kişiyi vardiyaya ata"):
                                            if o.get("zaten_atanmis"):
                                                st.error("Zaten atanmış!")
                                            else:
                                                b, e = VARDIYA_SAATLERI.get(o["vardiya_tipi"],("08:00","08:00"))
                                                sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                        (o["id"],gemi["id"],mak["id"],sec_tarih.isoformat(),b,e))
                                                del st.session_state[key_on]
                                                st.toast(f"{o['ad']} {o['soyad']} atandı!"); st.rerun()

# ═══════════════════════════════════════════════════════
# SAYFA: HAFTALIK / AYLIK TAKVİM
# ═══════════════════════════════════════════════════════
def _sayfa_takvim():
    st.subheader("📅 Haftalık / Aylık Takvim")
    goruntu = st.radio("Görünüm", ["Haftalık","Aylık"], horizontal=True, key="takvim_goruntu")
    if goruntu == "Haftalık":
        bugun = date.today()
        hafta_baslangici = st.date_input("Haftanın başlangıcı (Pazartesi)", value=bugun - timedelta(days=bugun.weekday()), key="takvim_hafta_bas")
        hafta_bitis = hafta_baslangici + timedelta(days=6)
        st.caption(f"{hafta_baslangici.strftime('%d %b')} – {hafta_bitis.strftime('%d %b %Y')}")
        hafta_verileri = sql_all(
            """SELECT v.tarih, v.baslangic_saat, v.bitis_saat,
                      p.ad||' '||p.soyad AS personel, p.vardiya_tipi,
                      g.ad AS gemi, m.ad AS makine
               FROM vardiya_plan v
               JOIN personel p ON v.personel_id=p.id
               JOIN gemi g ON v.gemi_id=g.id
               JOIN makine_tipi m ON v.makine_tipi_id=m.id
               WHERE v.tarih BETWEEN ? AND ?
               ORDER BY g.ad, m.ad, v.tarih""",
            (hafta_baslangici.isoformat(), hafta_bitis.isoformat()),
        )
        if not hafta_verileri:
            st.info("Bu haftaya ait vardiya planı bulunamadı.")
            return
        gun_listesi = [hafta_baslangici + timedelta(days=i) for i in range(7)]
        gun_basliklar = [f"{GUNLER_TR[g.weekday()]}\n{g.strftime('%d/%m')}" for g in gun_listesi]
        gemi_mak_set = {}
        for row in hafta_verileri:
            key = f"{row['gemi']} — {row['makine']}"
            if key not in gemi_mak_set:
                gemi_mak_set[key] = {d.isoformat(): [] for d in gun_listesi}
            gemi_mak_set[key][row["tarih"]].append(row)
        for gm_key, gunler in gemi_mak_set.items():
            st.markdown(f"#### 🚢 {gm_key}")
            cols = st.columns(7)
            for idx, gun in enumerate(gun_listesi):
                with cols[idx]:
                    st.markdown(f"<div style='text-align:center;font-size:11px;color:#aaa'>{gun_basliklar[idx]}</div>", unsafe_allow_html=True)
                    atamalar = gunler.get(gun.isoformat(), [])
                    if atamalar:
                        for a in atamalar:
                            renk = VARDIYA_RENKLERI.get(a["vardiya_tipi"],"#444")
                            st.markdown(f"<div style='background:{renk};border-radius:6px;padding:5px 4px;color:white;font-size:11px;text-align:center;margin-bottom:3px'>{a['personel']}<br>{a['baslangic_saat']}-{a['bitis_saat']}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<div style='background:#2a2a2a;border-radius:6px;padding:5px;color:#666;font-size:11px;text-align:center'>—</div>", unsafe_allow_html=True)
            st.divider()
    else:
        bugun = date.today()
        col_ay, col_yil = st.columns(2)
        with col_ay:
            ay_sec = st.selectbox("Ay", range(1,13), index=bugun.month-1, format_func=lambda m: AY_ADLARI[m], key="takvim_ay")
        with col_yil:
            yil_sec = st.number_input("Yıl", value=bugun.year, min_value=2020, max_value=2030, key="takvim_yil")
        ay_bas  = date(yil_sec, ay_sec, 1)
        ay_bitis = date(yil_sec, ay_sec, _cal.monthrange(yil_sec, ay_sec)[1])
        ay_verileri = sql_all(
            """SELECT v.tarih, COUNT(*) AS atama_sayisi FROM vardiya_plan v
               WHERE v.tarih BETWEEN ? AND ? GROUP BY v.tarih ORDER BY v.tarih""",
            (ay_bas.isoformat(), ay_bitis.isoformat()),
        )
        atama_by_tarih = {r["tarih"]: r["atama_sayisi"] for r in ay_verileri}
        toplam_poz = sql_one("SELECT COUNT(*) AS c FROM gemi_makine")["c"] or 1
        st.markdown(f"### {AY_ADLARI[ay_sec]} {yil_sec}")
        ilk_gun = ay_bas.weekday()
        cols_header = st.columns(7)
        for i, g in enumerate(["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]):
            cols_header[i].markdown(f"<div style='text-align:center;font-weight:bold;color:#aaa'>{g}</div>", unsafe_allow_html=True)
        satirlar = []
        current_row = [""] * ilk_gun
        gun_sayac = ilk_gun
        for n in range(1, ay_bitis.day + 1):
            d = date(yil_sec, ay_sec, n)
            atama = atama_by_tarih.get(d.isoformat(), 0)
            doluluk_oran = atama / toplam_poz
            if doluluk_oran >= 0.8:   renk = "#2ecc71"
            elif doluluk_oran >= 0.4: renk = "#f39c12"
            elif doluluk_oran > 0:    renk = "#e74c3c"
            else:                      renk = "#2a2a2a"
            bugu_vurgu = "border:2px solid #00d4ff;" if d == bugun else ""
            hucre = f"<div style='background:{renk};{bugu_vurgu}border-radius:8px;padding:8px 2px;text-align:center;color:white;font-size:13px;font-weight:500'>{n}<br><span style='font-size:10px'>{atama} atama</span></div>"
            current_row.append(hucre)
            gun_sayac += 1
            if gun_sayac % 7 == 0:
                satirlar.append(current_row)
                current_row = []
        if current_row:
            while len(current_row) < 7:
                current_row.append("")
            satirlar.append(current_row)
        for satir in satirlar:
            cols = st.columns(7)
            for i, hucre in enumerate(satir):
                if hucre:
                    cols[i].markdown(hucre, unsafe_allow_html=True)
                else:
                    cols[i].markdown("<div style='padding:8px'></div>", unsafe_allow_html=True)
        st.markdown("**Renk:** 🟢 %80+ dolu &nbsp; 🟡 %40–80 &nbsp; 🔴 <%40 &nbsp; ⬛ Atama yok")

# ═══════════════════════════════════════════════════════
# SAYFA: ANALİTİK
# ═══════════════════════════════════════════════════════
def _sayfa_analitik():
    st.subheader("📊 Analitik & Raporlar")
    if not PLOTLY_AVAILABLE:
        st.error("Analitik için `pip install plotly` çalıştırın.")
        return
    bugun = date.today()
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚖️ Personel Yük Dengesi",
        "🚢 Gemi Doluluk Oranı",
        "⏰ Fazla Mesai Takibi",
        "⚠️ Çakışma Raporu",
    ])
    with tab1:
        st.markdown("#### Bu Ay Çalışma Günleri")
        ay_bas  = date(bugun.year, bugun.month, 1)
        ay_bitis = bugun
        yukler = sql_all(
            """SELECT p.ad||' '||p.soyad AS personel, p.vardiya_tipi,
                      COUNT(DISTINCT v.tarih) AS gun_sayisi
               FROM personel p
               LEFT JOIN vardiya_plan v ON v.personel_id=p.id
                   AND v.tarih BETWEEN ? AND ?
               WHERE p.aktif=1
               GROUP BY p.id
               ORDER BY gun_sayisi DESC""",
            (ay_bas.isoformat(), ay_bitis.isoformat()),
        )
        if not yukler:
            st.info("Henüz veri yok.")
        else:
            df_yuk = pd.DataFrame(yukler)
            ort = df_yuk["gun_sayisi"].mean()
            df_yuk["sapma"] = df_yuk["gun_sayisi"] - ort
            df_yuk["renk"]  = df_yuk["sapma"].apply(lambda x: "#e74c3c" if x > 3 else ("#f39c12" if x > 1 else "#2ecc71"))
            fig = go.Figure(go.Bar(x=df_yuk["personel"], y=df_yuk["gun_sayisi"], marker_color=df_yuk["renk"].tolist(), text=df_yuk["gun_sayisi"], textposition="outside"))
            fig.add_hline(y=ort, line_dash="dash", line_color="#aaa", annotation_text=f"Ort: {ort:.1f} gün", annotation_position="top right")
            fig.update_layout(title=f"{AY_ADLARI[bugun.month]} {bugun.year} — Personel Başına Çalışma Günü", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", height=420)
            st.plotly_chart(fig, use_container_width=True)
            df_yuk["durum"] = df_yuk["sapma"].apply(lambda x: "🔴 Aşırı yüklü" if x > 3 else ("🟡 Fazla" if x > 1 else "🟢 Dengeli"))
            st.dataframe(df_yuk[["personel","vardiya_tipi","gun_sayisi","durum"]].rename(columns={"personel":"Ad Soyad","vardiya_tipi":"Vardiya","gun_sayisi":"Gün","durum":"Durum"}), use_container_width=True)
    with tab2:
        st.markdown("#### Son 30 Günlük Gemi Doluluk Oranı")
        bas_30 = bugun - timedelta(days=29)
        poz_sayisi = sql_all("""SELECT g.ad AS gemi, COUNT(gm.makine_tipi_id) AS toplam_poz FROM gemi g LEFT JOIN gemi_makine gm ON gm.gemi_id=g.id GROUP BY g.id""")
        poz_map = {r["gemi"]: r["toplam_poz"] for r in poz_sayisi}
        doluluk_data = sql_all("""SELECT g.ad AS gemi, v.tarih, COUNT(*) AS atama FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id WHERE v.tarih BETWEEN ? AND ? GROUP BY g.id, v.tarih""", (bas_30.isoformat(), bugun.isoformat()))
        if not doluluk_data:
            st.info("Son 30 günde veri yok.")
        else:
            df_dol = pd.DataFrame(doluluk_data)
            df_dol["doluluk_oran"] = df_dol.apply(lambda r: round(r["atama"] / max(poz_map.get(r["gemi"],1),1) * 100, 1), axis=1)
            fig2 = px.line(df_dol, x="tarih", y="doluluk_oran", color="gemi", title="Gemi Bazlı Günlük Doluluk Oranı (%)", markers=True)
            fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", yaxis_range=[0,110], height=400)
            st.plotly_chart(fig2, use_container_width=True)
            ort_dol = df_dol.groupby("gemi")["doluluk_oran"].mean().reset_index()
            ort_dol.columns = ["Gemi","Ort. Doluluk (%)"]
            ort_dol["Ort. Doluluk (%)"] = ort_dol["Ort. Doluluk (%)"].round(1)
            st.dataframe(ort_dol, use_container_width=True)
    with tab3:
        st.markdown("#### Bu Hafta Fazla Mesai Durumu")
        ayar     = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
        max_saat = ayar.get("max_haftalik_saat", 45)
        hafta_basi = bugun - timedelta(days=bugun.weekday())
        hafta_son  = hafta_basi + timedelta(days=6)
        haftalik = sql_all(
            """SELECT p.ad||' '||p.soyad AS personel, p.vardiya_tipi,
                      SUM(CASE WHEN CAST(SUBSTR(v.bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.bitis_saat,4,2) AS INTEGER)
                               > CAST(SUBSTR(v.baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.baslangic_saat,4,2) AS INTEGER)
                             THEN (CAST(SUBSTR(v.bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.bitis_saat,4,2) AS INTEGER))
                                - (CAST(SUBSTR(v.baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.baslangic_saat,4,2) AS INTEGER))
                             ELSE (CAST(SUBSTR(v.bitis_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.bitis_saat,4,2) AS INTEGER))
                                - (CAST(SUBSTR(v.baslangic_saat,1,2) AS INTEGER)*60 + CAST(SUBSTR(v.baslangic_saat,4,2) AS INTEGER)) + 1440
                        END) / 60.0 AS toplam_saat
               FROM personel p
               JOIN vardiya_plan v ON v.personel_id=p.id
               WHERE v.tarih BETWEEN ? AND ? AND p.aktif=1
               GROUP BY p.id
               HAVING toplam_saat > 0
               ORDER BY toplam_saat DESC""",
            (hafta_basi.isoformat(), hafta_son.isoformat()),
        )
        if not haftalik:
            st.info("Bu hafta henüz vardiya verisi yok.")
        else:
            df_mesai = pd.DataFrame(haftalik)
            df_mesai["fazla_mesai"] = (df_mesai["toplam_saat"] - max_saat).clip(lower=0).round(1)
            df_mesai["durum"] = df_mesai["toplam_saat"].apply(lambda s: "🔴 Limit Aşıldı" if s > max_saat else ("🟡 Limite Yakın" if s > max_saat * 0.85 else "🟢 Normal"))
            colors = df_mesai["toplam_saat"].apply(lambda s: "#e74c3c" if s > max_saat else ("#f39c12" if s > max_saat * 0.85 else "#3498db")).tolist()
            fig3 = go.Figure(go.Bar(x=df_mesai["personel"], y=df_mesai["toplam_saat"], marker_color=colors, text=df_mesai["toplam_saat"].round(1), textposition="outside"))
            fig3.add_hline(y=max_saat, line_dash="dash", line_color="#e74c3c", annotation_text=f"Limit: {max_saat}h", annotation_position="top right")
            fig3.update_layout(title=f"Haftalık Çalışma Saati (Limit: {max_saat}h)", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", height=400)
            st.plotly_chart(fig3, use_container_width=True)
            st.dataframe(df_mesai[["personel","vardiya_tipi","toplam_saat","fazla_mesai","durum"]].rename(columns={"personel":"Ad Soyad","vardiya_tipi":"Vardiya","toplam_saat":"Toplam Saat","fazla_mesai":"Fazla Mesai (h)","durum":"Durum"}), use_container_width=True)
            fazla = df_mesai[df_mesai["toplam_saat"] > max_saat]
            if not fazla.empty:
                st.warning(f"⚠️ **{len(fazla)} personel** bu hafta {max_saat} saati aştı!")
    with tab4:
        st.markdown("#### Üst Üste Çalışma & Çakışma Analizi")
        col_a, col_b = st.columns(2)
        with col_a:
            cap_bas = st.date_input("Başlangıç", value=bugun - timedelta(days=14), key="cap_bas")
        with col_b:
            cap_bit = st.date_input("Bitiş", value=bugun, key="cap_bit")
        if btn("🔍 Raporu Oluştur", key="cap_rapor", caption="Seçili aralıkta üst üste çalışanları listeler", help_text="Ardışık günlerde aynı personelin farklı gemilerde çalışmasını tespit eder."):
            ust_uste_data = sql_all(
                """SELECT v1.personel_id, p.ad||' '||p.soyad AS personel, p.vardiya_tipi,
                          v1.tarih AS gun1, v2.tarih AS gun2, g1.ad AS gemi1, g2.ad AS gemi2
                   FROM vardiya_plan v1
                   JOIN vardiya_plan v2 ON v1.personel_id=v2.personel_id AND DATE(v2.tarih) = DATE(v1.tarih, '+1 day')
                   JOIN personel p ON v1.personel_id=p.id
                   JOIN gemi g1 ON v1.gemi_id=g1.id
                   JOIN gemi g2 ON v2.gemi_id=g2.id
                   WHERE v1.tarih BETWEEN ? AND ?
                   ORDER BY v1.personel_id, v1.tarih""",
                (cap_bas.isoformat(), cap_bit.isoformat()),
            )
            if ust_uste_data:
                st.warning(f"**{len(ust_uste_data)} ardışık çalışma** tespit edildi:")
                df_uu = pd.DataFrame(ust_uste_data)[["personel","vardiya_tipi","gun1","gun2","gemi1","gemi2"]]
                df_uu.columns = ["Personel","Vardiya","Gün 1","Gün 2","Gemi 1","Gemi 2"]
                st.dataframe(df_uu, use_container_width=True)
                ozet = df_uu.groupby("Personel").size().reset_index(name="Ardışık Çift Sayısı")
                ozet = ozet.sort_values("Ardışık Çift Sayısı", ascending=False)
                fig4 = px.bar(ozet, x="Personel", y="Ardışık Çift Sayısı", title="Personel Başına Ardışık Çalışma Sayısı", color="Ardışık Çift Sayısı", color_continuous_scale=["#2ecc71","#f39c12","#e74c3c"])
                fig4.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ddd", height=380)
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.success("✅ Seçili aralıkta ardışık çalışma tespit edilmedi.")

# ═══════════════════════════════════════════════════════
# SAYFA: VARDIYA TAKAS
# ═══════════════════════════════════════════════════════
def _sayfa_takas():
    st.subheader("🔁 Vardiya Takas Talebi")
    st.info("İki personel arasında vardiya değişikliği talebi oluşturun. Yönetici onayı gereklidir.")
    personeller = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if len(personeller) < 2:
        st.warning("En az 2 aktif personel gerekli.")
        return
    with st.expander("➕ Yeni Takas Talebi Oluştur", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Talep Eden**")
            talep_eden = st.selectbox("Personel", personeller, format_func=lambda p: f"{p['ad']} {p['soyad']}", key="takas_talep_eden")
            talep_eden_tarih = st.date_input("Kendi vardiya tarihi", value=date.today(), key="takas_talep_eden_tarih")
            te_vardiya = sql_one("""SELECT g.ad AS gemi, m.ad AS makine, v.baslangic_saat, v.bitis_saat FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id WHERE v.personel_id=? AND v.tarih=?""", (talep_eden["id"], talep_eden_tarih.isoformat()))
            if te_vardiya:
                st.success(f"📋 {te_vardiya['gemi']} / {te_vardiya['makine']} ({te_vardiya['baslangic_saat']}–{te_vardiya['bitis_saat']})")
            else:
                st.warning("Bu tarihte vardiyası yok.")
        with c2:
            st.markdown("**Karşı Personel**")
            diger_personeller = [p for p in personeller if p["id"] != talep_eden["id"]]
            karsi = st.selectbox("Personel", diger_personeller, format_func=lambda p: f"{p['ad']} {p['soyad']}", key="takas_karsi")
            karsi_tarih = st.date_input("Karşı vardiya tarihi", value=date.today(), key="takas_karsi_tarih")
            karsi_vardiya = sql_one("""SELECT g.ad AS gemi, m.ad AS makine, v.baslangic_saat, v.bitis_saat FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id WHERE v.personel_id=? AND v.tarih=?""", (karsi["id"], karsi_tarih.isoformat()))
            if karsi_vardiya:
                st.success(f"📋 {karsi_vardiya['gemi']} / {karsi_vardiya['makine']} ({karsi_vardiya['baslangic_saat']}–{karsi_vardiya['bitis_saat']})")
            else:
                st.warning("Bu tarihte vardiyası yok.")
        notlar = st.text_area("Açıklama / Not", key="takas_notlar", height=60)
        if btn("📤 Talep Gönder", key="takas_gonder", caption="Takas talebini oluşturur", help_text="Yöneticinin onaylaması için takas talebi oluşturur."):
            if not te_vardiya:
                st.error("Talep eden personelin seçili tarihte vardiyası yok!")
            elif not karsi_vardiya:
                st.error("Karşı personelin seçili tarihte vardiyası yok!")
            elif talep_eden["id"] == karsi["id"]:
                st.error("Aynı personel seçilemez!")
            else:
                sql_run("INSERT INTO vardiya_takas(talep_eden_id,karsi_personel_id,talep_eden_tarih,karsi_tarih,notlar,olusturma_tarihi) VALUES(?,?,?,?,?,?)",
                        (talep_eden["id"], karsi["id"], talep_eden_tarih.isoformat(), karsi_tarih.isoformat(), notlar or None, datetime.now().isoformat()))
                audit_log("takas","talep",f"{talep_eden['id']}<->{karsi['id']}")
                st.success("✅ Takas talebi oluşturuldu! Yönetici onayı bekleniyor.")
                st.rerun()
    st.divider()
    st.markdown("#### 📋 Bekleyen Takas Talepleri")
    talepler = sql_all("""SELECT t.id, t.durum, t.talep_eden_tarih, t.karsi_tarih, t.notlar, t.olusturma_tarihi, p1.ad||' '||p1.soyad AS talep_eden, p2.ad||' '||p2.soyad AS karsi FROM vardiya_takas t JOIN personel p1 ON t.talep_eden_id=p1.id JOIN personel p2 ON t.karsi_personel_id=p2.id ORDER BY t.olusturma_tarihi DESC LIMIT 50""")
    if not talepler:
        st.info("Henüz takas talebi yok.")
        return
    for t in talepler:
        durum_rengi = {"Beklemede":"🟡","Onaylandı":"🟢","Reddedildi":"🔴"}.get(t["durum"],"⚪")
        with st.expander(f"{durum_rengi} #{t['id']} — {t['talep_eden']} ↔ {t['karsi']} | {t['talep_eden_tarih']} ↔ {t['karsi_tarih']}", expanded=(t["durum"] == "Beklemede")):
            st.write(f"**Durum:** {t['durum']}")
            st.write(f"**Oluşturma:** {t['olusturma_tarihi'][:16]}")
            if t["notlar"]: st.write(f"**Not:** {t['notlar']}")
            if t["durum"] == "Beklemede":
                col_o, col_r, col_s = st.columns(3)
                with col_o:
                    if btn("✅ Onayla", key=f"takas_onayla_{t['id']}", caption="", help_text="Takas talebini onaylar ve vardiyaları değiştirir"):
                        te_v = sql_one("""SELECT v.id FROM vardiya_plan v JOIN vardiya_takas tk ON v.personel_id=tk.talep_eden_id WHERE tk.id=? AND v.tarih=tk.talep_eden_tarih""", (t["id"],))
                        ka_v = sql_one("""SELECT v.id FROM vardiya_plan v JOIN vardiya_takas tk ON v.personel_id=tk.karsi_personel_id WHERE tk.id=? AND v.tarih=tk.karsi_tarih""", (t["id"],))
                        tk_row = sql_one("SELECT * FROM vardiya_takas WHERE id=?", (t["id"],))
                        if te_v and ka_v and tk_row:
                            try:
                                sql_run("UPDATE vardiya_plan SET personel_id=? WHERE id=?", (tk_row["karsi_personel_id"], te_v["id"]))
                                sql_run("UPDATE vardiya_plan SET personel_id=? WHERE id=?", (tk_row["talep_eden_id"], ka_v["id"]))
                                sql_run("UPDATE vardiya_takas SET durum='Onaylandı' WHERE id=?", (t["id"],))
                                audit_log("takas","onayla",f"id:{t['id']}")
                                st.toast("✅ Takas gerçekleştirildi!"); st.rerun()
                            except Exception as e:
                                st.error(f"Hata: {e}")
                        else:
                            st.error("Vardiya bulunamadı, takas yapılamadı.")
                with col_r:
                    if btn("❌ Reddet", key=f"takas_reddet_{t['id']}", caption="", help_text="Talebi reddeder"):
                        sql_run("UPDATE vardiya_takas SET durum='Reddedildi' WHERE id=?", (t["id"],))
                        st.toast("❌ Talep reddedildi."); st.rerun()
                with col_s:
                    if btn("🗑️ Sil", key=f"takas_sil_{t['id']}", caption="", help_text="Talebi tamamen siler", type="secondary"):
                        sql_run("DELETE FROM vardiya_takas WHERE id=?", (t["id"],))
                        st.rerun()

# ═══════════════════════════════════════════════════════
# DİĞER SAYFALAR
# ═══════════════════════════════════════════════════════
def _sayfa_acil():
    st.subheader("⚡ Acil Panel")
    gem = sql_all("SELECT id,ad,konum FROM gemi ORDER BY ad")
    mak = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    bugun = date.today()
    izinli = bugun_izinli_ids()
    with st.expander("📅 Dün Kim Çalıştı?"):
        dun = (bugun - timedelta(days=1)).isoformat()
        cd1, cd2 = st.columns(2)
        with cd1: dun_gemi = st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="dun_gemi")
        with cd2: dun_mak  = st.selectbox("Makine",[m["id"] for m in mak],format_func=lambda i:next(m["ad"] for m in mak if m["id"]==i),key="dun_mak")
        if btn("🔍 Sorgula",key="dun_sorgu",caption="Dünkü pozisyonun sahibini gösterir"):
            row = sql_one("SELECT p.ad||' '||p.soyad AS isim,v.baslangic_saat,v.bitis_saat FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.gemi_id=? AND v.makine_tipi_id=? AND v.tarih=?",(dun_gemi,dun_mak,dun))
            if row: st.success(f"Dün: **{row['isim']}** ({row['baslangic_saat']} - {row['bitis_saat']})")
            else: st.info("Dün bu pozisyonda kimse çalışmamış.")
    with st.expander("🏝️ Personeli İskeleye Çıkar"):
        isk_list = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 AND durum='Gemide' ORDER BY ad")
        if isk_list:
            isk_personel = st.selectbox("Personel Seç",[f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in isk_list],key="iskele_cikar")
            if btn("🔄 İskeleye Çıkar",key="btn_iskele",caption="Personeli 'İskelede' yapar"):
                pid = int(isk_personel.split("ID:")[1].replace(")",""))
                sql_run("UPDATE personel SET durum='İskelede' WHERE id=?",(pid,))
                st.toast("Personel iskeleye çıkarıldı!"); st.rerun()
        else:
            st.info("Gemide personel yok.")
    with st.expander("🚀 İskeledekileri Akıllı Dağıt"):
        if btn("🧠 Akıllı Dağıtım Başlat",key="btn_akilli_dagit",caption="İskelede/İZİNCİ personeli boş yerlere otomatik yerleştirir"):
            with st.spinner("Akıllı dağıtım yapılıyor..."):
                iskeledekiler = sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum='İskelede')")
                atanan = 0
                for p in sorted(iskeledekiler,key=lambda x:0 if x["vardiya_tipi"]=="IZINCI" else 1):
                    gids = _id_listesi(p.get("gemi_id_list")) or []
                    if p.get("gemi_id"): gids.append(p["gemi_id"])
                    mids = _id_listesi(p.get("makine_tipi_id_list"))
                    for gid in (gids if gids else [g["id"] for g in gem]):
                        gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(gid,))]
                        for mid in (mids if mids else gemi_mak):
                            if vardiya_plani_kontrol(gid,mid,bugun): continue
                            oneri_list = onerileri_hesapla(gid,mid,bugun,limit=1)
                            if oneri_list and oneri_list[0]["id"]==p["id"]:
                                b,e = VARDIYA_SAATLERI.get(p["vardiya_tipi"],("08:00","08:00"))
                                sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                        (p["id"],gid,mid,bugun.isoformat(),b,e))
                                sql_run("UPDATE personel SET durum='Gemide' WHERE id=?",(p["id"],))
                                atanan+=1; break
                        if atanan: break
                if atanan>0: st.toast(f"{atanan} personel dağıtıldı!"); st.rerun()
                else: st.warning("Hiçbir personel yerleştirilemedi.")
    st.divider(); st.markdown("### 📞 Anlık İzin Yerine")
    c1,c2 = st.columns(2)
    with c1:
        cik = st.selectbox("İzin İsteyen",[f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")],key="acil_cik")
        cik_id = int(cik.split("ID:")[1].replace(")","")) if cik else None
    with c2:
        hg = st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="acil_gemi")
        gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(hg,))]
        hm_sec = [m for m in mak if m["id"] in gemi_mak]
        if not hm_sec: st.warning("Seçili gemide makine yok"); return
        hm = st.selectbox("Makine",[m["id"] for m in hm_sec],format_func=lambda i:next((m["ad"] for m in hm_sec if m["id"]==i),""),key="acil_mak")
    if btn("🚨 Öner (5)",key="acil_oner",caption="İzin isteyenin yerine en uygun 5 adayı getirir"):
        on = onerileri_hesapla(hg,hm,bugun,cikan_id=cik_id,limit=5)
        if not on: st.warning("Uygun yok")
        else:
            for i,o in enumerate(on):
                st.success(f"{i+1}. {o['ad']} {o['soyad']} ({o['vardiya_tipi']}) - Puan:{o['puan']}")

def _sayfa_excel():
    st.subheader("🚢 Gemiler & Makine")
    with st.form("f_gemi", clear_on_submit=True):
        st.write("##### Yeni Gemi Ekle")
        c1,c2,c3 = st.columns(3)
        gad = c1.text_input("Gemi Adı",key="gemi_adi"); gkd = c2.text_input("Kod (opsiyonel)",key="gemi_kod")
        kon = c3.selectbox("Konum",GEMI_KONUMLARI,index=3,key="gemi_konum")
        makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
        if makineler:
            sec_mak = st.multiselect("Gemideki Makineler",[m["id"] for m in makineler],format_func=lambda i:next((m["ad"] for m in makineler if m["id"]==i),""),key="gm_mak_sec")
        else:
            st.info("Önce makine tipi ekleyin."); sec_mak = []
        if st.form_submit_button("➕ Gemi Ekle"):
            st.caption("Gemi ve makineleri kaydeder")
            if not gad: st.error("Gemi adı zorunludur.")
            else:
                try:
                    sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(gad.strip().upper(),gkd.strip().upper() if gkd else None,None if kon=="Belirtilmedi" else kon))
                    ng = sql_one("SELECT id FROM gemi WHERE ad=?",(gad.strip().upper(),))
                    if ng and sec_mak:
                        for mid in sec_mak:
                            sql_run("INSERT OR IGNORE INTO gemi_makine(gemi_id,makine_tipi_id) VALUES(?,?)",(ng["id"],mid))
                    st.toast("Gemi eklendi!"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")
    with st.expander("➕ Makine Tipi Ekle"):
        with st.form("f_makine", clear_on_submit=True):
            mad_val = st.text_input("Makine Tipi Adı")
            if st.form_submit_button("➕ Makine Ekle"):
                if not mad_val: st.error("Makine adı zorunlu")
                else:
                    try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(mad_val.strip().upper(),))
                    except: st.warning("Bu makine tipi zaten var")
                    else: st.toast("Makine tipi eklendi!"); st.rerun()
    st.divider()
    st.markdown("#### 🚢 Gemi Listesi")
    g_rows = sql_all("SELECT g.id,g.ad,g.kod,g.konum,COUNT(p.id) AS personel FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad")
    if g_rows:
        for gemi in g_rows:
            c1, c2, c3, c4, c5 = st.columns([3,2,2,2,1])
            with c1: st.write(f"**{gemi['ad']}**")
            with c2: st.write(f"Kod: {gemi['kod'] or '-'}")
            with c3: st.write(f"Konum: {gemi['konum'] or '-'}")
            with c4: st.write(f"Personel: {gemi['personel']}")
            with c5:
                if btn("🗑️", key=f"sil_gemi_{gemi['id']}", caption="", help_text="Gemiyi ve bağlı kayıtları siler.", type="secondary"):
                    sql_run("DELETE FROM gemi WHERE id=?", (gemi['id'],))
                    audit_log("kullanıcı","gemi_sil",f"{gemi['ad']} (ID:{gemi['id']})")
                    st.toast(f"🗑️ {gemi['ad']} silindi!"); st.rerun()
        st.caption("Silme işlemi, bağlı tüm gemi-makine eşleşmelerini ve vardiya planlarını da temizler.")
    else:
        st.info("Henüz gemi eklenmemiş.")
    with st.expander("🔗 Gemi-Makine Eşleştirme"):
        gemiler  = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
        makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
        if not gemiler:
            st.info("Önce gemi ekleyin.")
        else:
            sec_gemi = st.selectbox("Gemi",[g["id"] for g in gemiler],format_func=lambda i:next((g["ad"] for g in gemiler if g["id"]==i),""),key="gm_gemi")
            if sec_gemi:
                mevcut_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(sec_gemi,))]
                sec_mak = st.multiselect("Makineler",[m["id"] for m in makineler],default=mevcut_mak,format_func=lambda i:next((m["ad"] for m in makineler if m["id"]==i),""),key="gm_mak")
                if btn("Güncelle",key="gm_guncelle",caption="Gemi-makine eşleştirmesini günceller"):
                    sql_run("DELETE FROM gemi_makine WHERE gemi_id=?",(sec_gemi,))
                    for mid in sec_mak:
                        sql_run("INSERT OR IGNORE INTO gemi_makine(gemi_id,makine_tipi_id) VALUES(?,?)",(sec_gemi,mid))
                    st.toast("Güncellendi!"); st.rerun()

def _sayfa_personel():
    st.subheader("👷 Personel")
    gemiler  = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    arama = st.text_input("🔍 Personel Ara",key="personel_arama")
    c1,c2 = st.columns(2)
    with c1: fv = st.selectbox("Vardiya",["Tümü"]+VARDIYA_TIPLERI,key="fv_select"); fv = None if fv=="Tümü" else fv
    with c2:
        fa = st.radio("Durum",["Tümü","Aktif","Pasif"],key="fa_radio",horizontal=True)
        fa = {"Aktif":1,"Pasif":0}.get(fa)
    q = "SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,p.is_kalitesi,p.performans_notu,p.durum,p.aktif FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id"
    params = ()
    clauses = []
    if fv:       clauses.append("p.vardiya_tipi=?"); params+=(fv,)
    if fa is not None: clauses.append("p.aktif=?");  params+=(fa,)
    if clauses: q += " WHERE " + " AND ".join(clauses)
    rows = sql_all(q + " ORDER BY p.id DESC", params)
    if arama:
        au = arama.upper()
        rows = [r for r in rows if au in f"{r['ad']} {r['soyad']} {r['vardiya_tipi']} {r.get('gemi','')} {r.get('durum','')}".upper()]
    if not gemiler or not makineler: st.warning("Önce gemi/makine ekleyin."); return
    with st.expander("➕ Yeni Personel"):
        c1,c2 = st.columns(2)
        ad = c1.text_input("Ad",key="p_ad"); soyad = c2.text_input("Soyad",key="p_soyad")
        vt = st.selectbox("Vardiya Tipi",VARDIYA_TIPLERI,key="p_vt")
        mak_sec = st.multiselect("Makine",[r["id"] for r in makineler],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="p_mak")
        gem_list = st.multiselect("Gemiler",[r["id"] for r in gemiler],format_func=lambda i:next(r["ad"] for r in gemiler if r["id"]==i),key="p_gem")
        sec = st.multiselect("Vardiya Günleri",GUNLER_TR,default=["Pazartesi","Çarşamba","Cuma"],key="p_vg")
        gun_json = json.dumps([GUNLER_TR.index(x) for x in sec])
        durum = st.selectbox("Durum",PERSONEL_DURUM,key="p_durum"); is_kal = st.slider("İş Kalitesi",1,5,3,key="p_ik")
        pn = st.text_area("Performans Notu",key="p_not")
        if btn("Kaydet",key="btn_pk",caption="Yeni personeli ekler"):
            if not ad or not soyad: st.error("Ad soyad zorunlu")
            else:
                try:
                    sql_run("INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,durum,is_kalitesi,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (ad.strip().upper(),soyad.strip().upper(),gem_list[0] if gem_list else None,_gemi_id_json(gem_list),
                             mak_sec[0] if mak_sec else None,_makine_id_json(mak_sec) if mak_sec else "[]",
                             vt,gun_json,durum,is_kal,pn.strip() or None))
                    st.toast("Personel kaydedildi!"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")
    with st.expander("✏️ Düzenle / Sil & Sertifika"):
        pm = {f"{r['ad']} {r['soyad']} (ID:{r['id']})": r["id"] for r in sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad")}
        if not pm: st.info("Personel yok"); return
        secim = st.selectbox("Personel",list(pm.keys()),key="p_ds"); pid = pm[secim]
        mev = sql_one("SELECT * FROM personel WHERE id=?",(pid,))
        if not mev: return
        yvt = st.selectbox("Vardiya",VARDIYA_TIPLERI,index=VARDIYA_TIPLERI.index(mev["vardiya_tipi"]) if mev.get("vardiya_tipi") in VARDIYA_TIPLERI else 0,key="pd_vt")
        mevcut_gunler_json = mev.get("vardiya_gunleri")
        if mevcut_gunler_json:
            try:
                mevcut_gunler_idx = json.loads(mevcut_gunler_json)
                mevcut_gunler = [GUNLER_TR[i] for i in mevcut_gunler_idx if 0 <= i < 7]
            except:
                mevcut_gunler = []
        else:
            mevcut_gunler = []
        ygunler = st.multiselect("Vardiya Günleri", GUNLER_TR, default=mevcut_gunler, key="pd_vg")
        ygunler_json = json.dumps([GUNLER_TR.index(g) for g in ygunler])
        mids = _id_listesi(mev.get("makine_tipi_id_list"))
        ymak = st.multiselect("Makine",[r["id"] for r in makineler],default=[m for m in mids if m in [r["id"] for r in makineler]],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="pd_mak")
        gids = _id_listesi(mev.get("gemi_id_list")) or ([mev["gemi_id"]] if mev.get("gemi_id") else [])
        ygem = st.multiselect("Gemi",[r["id"] for r in gemiler],default=[g for g in gids if g in [r["id"] for r in gemiler]],format_func=lambda i:next(r["ad"] for r in gemiler if r["id"]==i),key="pd_gem")
        ydurum = st.selectbox("Durum",PERSONEL_DURUM,index=PERSONEL_DURUM.index(mev["durum"]) if mev.get("durum") in PERSONEL_DURUM else 0,key="pd_durum")
        ypn = st.text_area("Performans Notu",value=mev.get("performans_notu") or "",key="pd_pn")
        cu, cs = st.columns(2)
        if cu.button("Güncelle",key="bpgu"):
            st.caption("Bilgileri günceller")
            try:
                sql_run("UPDATE personel SET vardiya_tipi=?,makine_tipi_id_list=?,makine_tipi_id=?,gemi_id=?,gemi_id_list=?,durum=?,performans_notu=?,vardiya_gunleri=? WHERE id=?",
                        (yvt,_makine_id_json(ymak) if ymak else "[]",ymak[0] if ymak else None,ygem[0] if ygem else None,_gemi_id_json(ygem),ydurum,ypn.strip() or None,ygunler_json,pid))
                st.toast("Güncellendi!"); st.rerun()
            except Exception as e: st.error(f"Hata: {e}")
        if cs.button("Sil",key="bps"):
            st.caption("Personeli tamamen siler")
            for t in ["izin","vardiya_plan","personel_sertifika","performans_gecmis"]:
                sql_run(f"DELETE FROM {t} WHERE personel_id=?",(pid,))
            sql_run("DELETE FROM personel WHERE id=?",(pid,))
            st.toast("Silindi!"); st.rerun()
        st.markdown("---\n#### Sertifika")
        sert = sql_all("SELECT * FROM personel_sertifika WHERE personel_id=?",(pid,))
        if sert: st.dataframe(pd.DataFrame(sert),use_container_width=True)
        with st.form("sert_ekle",clear_on_submit=True):
            sm = st.selectbox("Makine",[r["id"] for r in makineler],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="sm")
            sa = st.text_input("Sertifika Adı",key="sa"); sg = st.date_input("Geçerlilik",value=None,key="sg"); sn = st.text_input("Not",key="sn")
            if st.form_submit_button("Ekle"):
                sql_run("INSERT INTO personel_sertifika VALUES(NULL,?,?,?,?,?)",(pid,sm,sa or None,sg.isoformat() if sg else None,sn or None))
                st.toast("Sertifika eklendi!"); st.rerun()
    if rows:
        st.markdown("#### 📋 Personel Listesi")
        st.dataframe(pd.DataFrame(rows)[["ad","soyad","gemi","vardiya_tipi","durum","is_kalitesi"]].rename(
            columns={"ad":"Ad","soyad":"Soyad","gemi":"Gemi","vardiya_tipi":"Vardiya","durum":"Durum","is_kalitesi":"Kalite"}
        ), use_container_width=True)

def _sayfa_izin():
    st.subheader("📅 İzin")
    pl = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not pl: st.info("Personel yok"); return
    cf,cc = st.columns([1,1])
    with cf:
        sec = st.selectbox("Personel",pl,format_func=lambda p:f"{p['ad']} {p['soyad']}",key="izp")
        pid = sec["id"]; bas = st.date_input("Başlangıç",value=date.today(),key="izb")
        bit = st.date_input("Bitiş",value=date.today(),key="izbi")
        if bit >= bas: gun = gun_sayisi(bas,bit); st.info(f"📅 {gun} gün")
        else: st.error("Tarih hatası"); gun = 0
        notlar = st.text_area("Not",key="izn",height=80)
        if btn("✅ Kaydet",key="biz",caption="İzni kaydeder"):
            if gun <= 0: st.error("Geçersiz aralık")
            else:
                cg = sql_all("SELECT DISTINCT v.tarih FROM vardiya_plan v WHERE v.personel_id=? AND v.tarih BETWEEN ? AND ?",(pid,bas.isoformat(),bit.isoformat()))
                if cg: st.warning(f"⚠️ {len(cg)} günde görev çakışması var!")
                sql_run("INSERT INTO izin VALUES(NULL,?,?,?,?,?,?)",(pid,bas.isoformat(),bit.isoformat(),gun,notlar or None,None))
                st.toast("İzin kaydedildi!"); st.rerun()
    with cc:
        bugun = date.today()
        ay_s = st.selectbox("Ay",[f"{AY_ADLARI[m]} {bugun.year}" for m in range(1,13)],index=bugun.month-1,key="izay")
        ay_i = AY_ADLARI.index(ay_s.split()[0]); yil = int(ay_s.split()[1])
        isaret = set()
        for iz in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=?",(pid,)):
            d = date.fromisoformat(iz["baslangic"]); b = date.fromisoformat(iz["bitis"])
            while d <= b:
                if d.year==yil and d.month==ay_i: isaret.add(d)
                d += timedelta(days=1)
        st.markdown(_takvim_html(yil,ay_i,isaret),unsafe_allow_html=True)
    st.divider(); st.markdown("#### Kayıtlı İzinler")
    izinler = sql_all("SELECT i.id,p.ad,p.soyad,i.baslangic,i.bitis,i.gun_sayisi,i.notlar FROM izin i JOIN personel p ON p.id=i.personel_id ORDER BY i.baslangic DESC LIMIT 100")
    for iz in izinler:
        c1,c2,c3 = st.columns([4,2,1])
        c1.markdown(f"**{iz['ad']} {iz['soyad']}**  \n📅 {iz['baslangic']} → {iz['bitis']} · {iz['gun_sayisi']} gün")
        c2.markdown("🟠 Aktif" if iz["baslangic"]<=date.today().isoformat()<=iz["bitis"] else "✅ Tamamlandı")
        if c3.button("🗑️",key=f"izsil_{iz['id']}"):
            sql_run("DELETE FROM izin WHERE id=?",(iz["id"],)); st.rerun()

def _sayfa_oneri():
    st.subheader("✦ Öneri & Plan")
    gem = sql_all("SELECT id,ad FROM gemi ORDER BY ad"); mak = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gem or not mak: st.warning("Gemi/makine yok"); return
    esnek = st.checkbox("Saat çakışmasını yoksay",value=False,key="esnek")
    st.subheader("🗓️ Toplu Planlama (Adil)")
    with st.expander("Ayarlar"):
        sg = st.multiselect("Gemiler",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="tpg")
        if sg:
            gemi_mak_ids = set()
            for gid in sg:
                gemi_mak_ids.update(r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(gid,)))
            mak_sec = [m for m in mak if m["id"] in gemi_mak_ids]
        else: mak_sec = []
        sm = st.multiselect("Makine",[m["id"] for m in mak_sec],format_func=lambda i:next((m["ad"] for m in mak_sec if m["id"]==i),""),key="tpm2") if mak_sec else []
        ba = st.date_input("Başlangıç",date.today(),key="tpb"); bi = st.date_input("Bitiş",date.today()+timedelta(days=7),key="tpi")
        gn = st.multiselect("Günler",GUNLER_TR,default=["Pazartesi","Salı","Çarşamba","Perşembe","Cuma"],key="tpgun")
        gi = [GUNLER_TR.index(g) for g in gn]
        if btn("🚀 Oluştur",key="btp",caption="Tüm boş pozisyonları adilce doldurur"):
            if not sg or not sm: st.error("Seçim yapın")
            else:
                with st.spinner("Toplu planlama..."):
                    kul = {}; top = 0
                    for g in sg:
                        gm_list = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(g,))]
                        for m in ([mid for mid in sm if mid in gm_list]):
                            d = ba
                            while d <= bi:
                                if d.weekday() in gi and not vardiya_plani_kontrol(g,m,d):
                                    on = onerileri_hesapla(g,m,d,limit=10,esnek_cakisma=esnek)
                                    on.sort(key=lambda x:kul.get(x["id"],0))
                                    if on and not on[0].get("zaten_atanmis"):
                                        b,e = VARDIYA_SAATLERI.get(on[0]["vardiya_tipi"],("08:00","08:00"))
                                        sql_run("INSERT OR IGNORE INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                (on[0]["id"],g,m,d.isoformat(),b,e))
                                        kul[on[0]["id"]] = kul.get(on[0]["id"],0)+1; top+=1
                                d += timedelta(days=1)
                st.toast(f"{top} vardiya dağıtıldı!"); st.rerun()
    st.divider(); st.subheader("Tek Seferlik Öneri")
    gid = st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next((g["ad"] for g in gem if g["id"]==i),""),key="ong")
    gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(gid,))]
    mak_sec2 = [m for m in mak if m["id"] in gemi_mak]
    if not mak_sec2: st.warning("Bu gemide makine tanımlı değil!"); return
    mid = st.selectbox("Makine",[m["id"] for m in mak_sec2],format_func=lambda i:next((m["ad"] for m in mak_sec2 if m["id"]==i),""),key="onm")
    ht = st.date_input("Tarih",date.today(),key="onht")
    tum = sql_all("SELECT id,ad,soyad,gemi_id,gemi_id_list FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))")
    izinli = bugun_izinli_ids()
    gemi_p = [p for p in tum if not p["gemi_id"] or p["gemi_id"]==gid or gid in _id_listesi(p.get("gemi_id_list"))]
    cik_opts = [("(Yok)",None)]+[(f"{p['ad']} {p['soyad']}{'  🟠' if p['id'] in izinli else ''}",p["id"]) for p in sorted(gemi_p,key=lambda x:(0 if x["id"] in izinli else 1,x["ad"]))]
    cik_sec = st.selectbox("Çıkan",cik_opts,format_func=lambda x:x[0],key="oncik"); cik_id = cik_sec[1]
    if btn("🔍 Öner",key="bon",caption="En uygun 5 adayı listeler"):
        out = onerileri_hesapla(gid,mid,ht,cik_id,5,esnek); rows = to_dict_rows(out)
        if not rows: st.warning("Uygun yok")
        elif any(r.get("zaten_atanmis") for r in rows): st.success("Zaten atanmış")
        else: st.dataframe(pd.DataFrame(rows),use_container_width=True)

def _sayfa_carkci():
    st.subheader("⚙️ Çarkçı")
    gem = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    yag = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not gem or not yag:
        st.warning("Gemi/personel yok")
        return
    c1, c2 = st.columns(2)
    with c1:
        ad = st.text_input("Ad", key="cka")
        soyad = st.text_input("Soyad", key="cks")
        gid = st.selectbox("Gemi", [r["id"] for r in gem], format_func=lambda i: next(r["ad"] for r in gem if r["id"] == i), key="ckg")
        cvt = st.selectbox("Vardiya", VARDIYA_TIPLERI, key="ckv")
        cg = st.multiselect("Günler", GUNLER_TR, key="ckgun")
    with c2:
        yop = [("(Seçilmedi)", None)] + [(f"{p['ad']} {p['soyad']}", p["id"]) for p in yag]
        ys = st.selectbox("Sorunlu Yağcı", yop, format_func=lambda x: x[0], key="cky")
        sorun = st.text_area("Sorun / Açıklama", key="ckso")
        vn = st.text_input("Vardiya Notu", key="ckvn")
        pk = st.slider("Puan Kırma", 0, 5, 0, key="ckp")
    if btn("Oluştur", key="bck", caption="Çarkçı kaydı oluşturur"):
        if not ad or not soyad:
            st.error("Ad soyad zorunlu")
        else:
            gun_j = json.dumps([GUNLER_TR.index(g) for g in cg]) if cg else "[]"
            pid_p = ys[1]
            try:
                sql_run("INSERT INTO carkci(ad,soyad,gemi_id,problemli_yagci_id,sorun_metni,vardiya_notu,carkci_vardiya,vardiya_gunleri,puan_kirma) VALUES(?,?,?,?,?,?,?,?,?)",
                        (ad.strip().upper(), soyad.strip().upper(), gid, pid_p, sorun, vn, cvt, gun_j, pk))
                if pid_p:
                    mev = sql_one("SELECT is_kalitesi FROM personel WHERE id=?", (pid_p,))
                    if mev:
                        yeni = max(1, (mev["is_kalitesi"] or 3) - pk)
                        sql_run("UPDATE personel SET is_kalitesi=?, carkci_ile_sorun=1, carkci_sorun_notu=? WHERE id=?",
                                (yeni, sorun.strip() or None, pid_p))
                audit_log("kullanici", "carkci_ekle", f"{ad} {soyad}")
                st.toast("Çarkçı kaydı oluşturuldu!")
                st.rerun()
            except Exception as e:
                st.error(f"Çarkçı eklenirken hata oluştu: {e}")
    st.divider()
    cr = sql_all("""SELECT c.id, c.ad, c.soyad, g.ad AS gemi, c.carkci_vardiya, c.vardiya_gunleri, p.ad||' '||p.soyad AS yagci, c.sorun_metni, c.puan_kirma FROM carkci c LEFT JOIN gemi g ON g.id = c.gemi_id LEFT JOIN personel p ON p.id = c.problemli_yagci_id ORDER BY c.id DESC LIMIT 30""")
    if cr:
        for r in cr:
            r["vardiya_gunleri"] = _json_gunleri_metne(r.get("vardiya_gunleri"))
        st.dataframe(pd.DataFrame(cr), use_container_width=True)
    else:
        st.info("Henüz çarkçı kaydı yok.")

def _sayfa_bilgi():
    st.subheader("📊 Bilgi & Rapor")
    c1,c2,c3 = st.columns(3)
    c1.metric("👥 Toplam Personel",sql_one("SELECT COUNT(*) AS c FROM personel WHERE aktif=1")["c"])
    c2.metric("🚢 Toplam Gemi",sql_one("SELECT COUNT(*) AS c FROM gemi")["c"])
    c3.metric("🏝️ Bugün İzinde",len(bugun_izinli_ids()))
    cb1,cb2,cb3 = st.columns(3)
    with cb1:
        if btn("💾 Yedekle",key="byedek",caption="Veritabanı yedeği alır"):
            st.toast(f"Yedek: {veritabani_yedekle().name}",icon="💾")
    with cb2:
        st.markdown("#### Test Verisi")
        onay = st.checkbox("Tüm mevcut verileri silmek istiyorum", key="test_sil_onay")
        if btn("🧪 Test Verisi Oluştur (Silerek)", key="btest_sil", caption="Önce tüm verileri siler, sonra test verisi ekler",
               help_text="Dikkat: Mevcut tüm kayıtlar silinecektir."):
            if not onay:
                st.error("Lütfen silme onayını işaretleyin.")
            else:
                test_verisi_olustur(sil=True)
                st.rerun()
        if btn("🧪 Test Verisi Ekle (Silmeden)", key="btest_ekle", caption="Mevcut verilere test verisi ekler",
               help_text="Mevcut veriler korunur, yeni test kayıtları eklenir."):
            test_verisi_olustur(sil=False)
            st.rerun()
    with cb3:
        st.download_button("📥 DB İndir",open(DB_PATH,"rb"),file_name=f"ordino_{date.today().isoformat()}.db",key="indir_db")
        st.caption("Veritabanını indirir")
    st.divider(); st.subheader("📄 PDF")
    cp1,cp2 = st.columns(2)
    with cp1:
        if btn("Aylık Özet PDF",key="bpdfa",caption="Aylık özet PDF"):
            p = pdf_rapor_olustur("aylik_ozet"); st.download_button("İndir",open(p,"rb"),file_name=p.name,key="indir_aylik")
    with cp2:
        p_bas = cp2.date_input("Başlangıç",date.today(),key="pdf_bas")
        p_bit = cp2.date_input("Bitiş",date.today()+timedelta(days=7),key="pdf_bit")
        if btn("PDF Oluştur",key="pdf_aralik",caption="Vardiya planı PDF"):
            p = pdf_rapor_olustur("vardiya_plani",baslangic=p_bas,bitis=p_bit); st.download_button("İndir",open(p,"rb"),file_name=p.name,key="indir_vardiya")
    st.divider(); st.subheader("📋 Bugünün Planı")
    bugun_plani = bugun_plani_olustur()
    if bugun_plani:
        df_plan = pd.DataFrame(bugun_plani)
        st.dataframe(df_plan,use_container_width=True)
        if btn("⬇ .ics İndir",key="ics_indir",caption="Takvim dosyası"):
            rows = sql_all("SELECT v.tarih,v.baslangic_saat,v.bitis_saat,g.ad AS gemi,m.ad AS makine FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id")
            ics = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Ordino//TR\n"
            for r in rows:
                db = f"{r['tarih'].replace('-','')}T{r['baslangic_saat'].replace(':','')}00"
                de = f"{r['tarih'].replace('-','')}T{r['bitis_saat'].replace(':','')}00"
                ics += f"BEGIN:VEVENT\nDTSTART:{db}\nDTEND:{de}\nSUMMARY:{r['gemi']} - {r['makine']}\nEND:VEVENT\n"
            ics += "END:VCALENDAR"
            st.download_button("İndir .ics",ics,file_name="ordino_plan.ics",key="indir_ics")
    else:
        st.info("Bugün için plan yok.")

# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
def main():
    st.set_page_config(page_title="Ordino", page_icon="⚓", layout="wide")
    if "ayarlar" not in st.session_state:
        st.session_state.ayarlar = DEFAULT_AYARLAR

    init_db()

    st.markdown("""
    <style>
    .stButton > button { width:100%; border-radius:8px; }
    @media (max-width: 640px) {
        .stHorizontalBlock { flex-direction:column !important; }
        .stColumn { width:100% !important; min-width:100% !important; }
        div[data-testid="column"] { width:100% !important; }
    }
    @media (min-width: 641px) and (max-width: 1024px) {
        .stColumn { min-width:140px !important; }
        .stHorizontalBlock { gap: 0.5rem !important; }
    }
    .streamlit-expanderHeader { font-weight:600; }
    div[data-testid="metric-container"] {
        background:#1e2130; border-radius:12px; padding:16px; border:1px solid #2d3250;
    }
    .dataframe { font-size:13px !important; }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.title("⚓ Ordino")
        st.caption("v8.5")
        st.markdown("---")
        uyarilar = sertifika_uyarilari_al()
        if uyarilar:
            st.markdown("**⚠️ Yaklaşan Sertifika:**")
            for u in uyarilar:
                st.warning(f"{u['ad']} {u['soyad']} — {u['sertifika_adi']} ({u['gecerlilik_tarihi']})")
        st.markdown("**📋 Bugün:**")
        for p in bugun_plani_olustur()[:10]:
            emoji = "✅" if "BOŞ" not in p["Personel"] else "🟡"
            st.write(f"{emoji} {p['Gemi']} – {p['Makine']}: **{p['Personel']}**")
        bekleyen_takas = sql_one("SELECT COUNT(*) AS c FROM vardiya_takas WHERE durum='Beklemede'")
        if bekleyen_takas and bekleyen_takas["c"] > 0:
            st.info(f"🔁 {bekleyen_takas['c']} bekleyen takas talebi")

    tabs = st.tabs([
        "🧩 Yapboz",
        "📅 Takvim",
        "⚡ Acil",
        "🚢 Gemiler",
        "👷 Personel",
        "📅 İzin",
        "✦ Öneri",
        "🔁 Takas",
        "📊 Analitik",
        "📋 Bilgi",
        "⚙️ Ayarlar",
    ])
    with tabs[0]: _sayfa_yapboz()
    with tabs[1]: _sayfa_takvim()
    with tabs[2]: _sayfa_acil()
    with tabs[3]: _sayfa_excel()
    with tabs[4]: _sayfa_personel()
    with tabs[5]: _sayfa_izin()
    with tabs[6]: _sayfa_oneri()
    with tabs[7]: _sayfa_takas()
    with tabs[8]: _sayfa_analitik()
    with tabs[9]: _sayfa_bilgi()
    with tabs[10]: ayarlar_sayfasi()

if __name__ == "__main__":
    main()
