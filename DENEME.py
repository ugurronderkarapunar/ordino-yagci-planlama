"""
Ordino Yağcı Planlaması — Eksiksiz, Çalışan Tam Sürüm (v7.6)
Her butonun altında açıklama, tüm fonksiyonlar mevcut.
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json, sqlite3, calendar as _cal, shutil
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st
from fpdf import FPDF

try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# ---------- SABİTLER ----------
DB_PATH = Path(__file__).parent / "ordino.db"
YEDEK_DIR = Path(__file__).parent / "yedekler"
LOG_DIR = Path(__file__).parent / "logs"

VARDIYA_SAATLERI = {
    "SABIT": ("08:00", "08:00"),
    "GRUPCU": ("08:00", "08:00"),
    "IZINCI": ("08:00", "08:00"),
    "TERSANE": ("08:00", "17:00"),
    "8_5": ("08:00", "17:00"),
    "GECE": ("20:00", "08:00"),
}
GUNLER_TR = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
AY_ADLARI = ["","Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
VARDIYA_TIPLERI = ["SABIT","GRUPCU","IZINCI","TERSANE","8_5","GECE"]
GEMI_KONUMLARI = ["Tersane", "Dışarıda", "Gecede", "Belirtilmedi"]
PERSONEL_DURUM = ["Gemide", "İskelede", "Raporlu"]
VARDIYA_RENKLERI = {"SABIT":"#3498db","GRUPCU":"#2ecc71","IZINCI":"#f39c12","TERSANE":"#e74c3c","8_5":"#9b59b6","GECE":"#1abc9c"}
VARDIYA_KONUM_ESLESME = {"TERSANE":"Tersane", "8_5":"Dışarıda"}
DEFAULT_AYARLAR = {"min_dinlenme_suresi_saat": 11, "max_haftalik_saat": 45, "yillik_izin_hakki": 14}

OLUMLU_KELIMELER = ["iyi", "çalışkan", "başarılı", "güvenilir", "hızlı", "dikkatli", "özenli", "disiplinli", "yardımsever", "titiz", "profesyonel", "mükemmel", "harika", "süper", "efsane", "gayretli", "istekli", "düzenli", "sorumlu", "kooperatif"]
OLUMSUZ_KELIMELER = ["kötü", "berbat", "yetersiz", "tembel", "sorunlu", "problemli", "geç kalıyor", "işe yaramaz", "ilgisiz", "dikkatsiz", "başarısız", "yavaş", "isteksiz", "uyumsuz", "şikayet", "kavga", "saygısız", "sorumsuz", "eksik", "hatalı", "verimsiz", "güvenilmez", "disiplinsiz", "özensiz"]
AGIR_OLUMSUZ_KELIMELER = ["berbat", "işe yaramaz", "güvenilmez", "disiplinsiz", "kovulmalı", "kesinlikle çalışmaz"]

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

# ---------- YARDIMCI FONKSİYONLAR ----------
def btn(label, key, caption, **kwargs):
    if 'type' not in kwargs:
        kwargs['type'] = 'primary'
    clicked = st.button(label, key=key, **kwargs)
    st.caption(caption)
    return clicked

def saat_dakika(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m

def saat_cakisiyor(bas1: str, bit1: str, bas2: str, bit2: str) -> bool:
    b1, e1 = saat_dakika(bas1), saat_dakika(bit1)
    b2, e2 = saat_dakika(bas2), saat_dakika(bit2)
    if e1 <= b1: e1 += 24 * 60
    if e2 <= b2: e2 += 24 * 60
    return b1 < e2 and b2 < e1

def saat_cakismasi_var(pid, tarih, bas_saat, bit_saat):
    rows = sql_all("SELECT baslangic_saat, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih=?", (pid, tarih.isoformat()))
    for r in rows:
        if saat_cakisiyor(bas_saat, bit_saat, r["baslangic_saat"], r["bitis_saat"]):
            return True
    return False

def dinlenme_suresi_kontrol(pid: int, tarih: date, bas_saat: str) -> bool:
    ayar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
    min_saat = ayar.get("min_dinlenme_suresi_saat", 11)
    son = sql_one("SELECT tarih, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih < ? ORDER BY tarih DESC, bitis_saat DESC LIMIT 1",
                  (pid, tarih.isoformat()))
    if not son: return True
    son_tarih = date.fromisoformat(son["tarih"])
    bit_dk = saat_dakika(son["bitis_saat"])
    bas_dk = saat_dakika(bas_saat)
    if son_tarih == tarih:
        if bas_dk < bit_dk: bas_dk += 24 * 60
        fark = (bas_dk - bit_dk) / 60.0
    else:
        fark = ((tarih - son_tarih).days * 24 * 60 + (bas_dk - bit_dk)) / 60.0
    return fark >= min_saat

def haftalik_calisma_saati(pid: int, bitis_tarihi: date) -> float:
    hafta_basi = bitis_tarihi - timedelta(days=bitis_tarihi.weekday())
    hafta_sonu = hafta_basi + timedelta(days=6)
    rows = sql_all("SELECT baslangic_saat, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih BETWEEN ? AND ?",
                   (pid, hafta_basi.isoformat(), hafta_sonu.isoformat()))
    toplam = 0
    for r in rows:
        b, e = saat_dakika(r["baslangic_saat"]), saat_dakika(r["bitis_saat"])
        if e <= b: e += 24 * 60
        toplam += (e - b)
    return toplam / 60.0

def yillik_izin_hesapla(pid: int, yil: int) -> Tuple[int, int]:
    p = sql_one("SELECT yillik_izin_hakki FROM personel WHERE id=?", (pid,))
    hak = p["yillik_izin_hakki"] if p and p["yillik_izin_hakki"] else DEFAULT_AYARLAR["yillik_izin_hakki"]
    bas = date(yil, 1, 1)
    son = date(yil, 12, 31)
    rows = sql_all("SELECT gun_sayisi FROM izin WHERE personel_id=? AND baslangic>=? AND bitis<=?",
                   (pid, bas.isoformat(), son.isoformat()))
    kullanilan = sum(r["gun_sayisi"] for r in rows) if rows else 0
    return kullanilan, hak

def vardiya_talebi_olustur(talep_eden_id, talep_tarih, gemi_id, makine_tipi_id):
    sql_run("""CREATE TABLE IF NOT EXISTS vardiya_talebi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        talep_eden_id INTEGER NOT NULL,
        talep_tarih TEXT NOT NULL,
        gemi_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL,
        durum TEXT DEFAULT 'Beklemede',
        FOREIGN KEY(talep_eden_id) REFERENCES personel(id),
        FOREIGN KEY(gemi_id) REFERENCES gemi(id),
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id))""")
    sql_run("INSERT INTO vardiya_talebi(talep_eden_id,talep_tarih,gemi_id,makine_tipi_id) VALUES(?,?,?,?)",
            (talep_eden_id, talep_tarih.isoformat(), gemi_id, makine_tipi_id))

def nlp_skor(metin: str) -> float:
    if not metin: return 0.0
    metin = metin.lower()
    olumlu = sum(1 for k in OLUMLU_KELIMELER if k in metin)
    olumsuz = sum(1 for k in OLUMSUZ_KELIMELER if k in metin)
    agir = sum(1 for k in AGIR_OLUMSUZ_KELIMELER if k in metin)
    toplam_olumsuz = olumsuz + (agir * 2)
    if olumlu + toplam_olumsuz == 0: return 0.0
    return (olumlu - toplam_olumsuz) / max(olumlu + toplam_olumsuz, 5)

def _id_listesi(v):
    if not v: return []
    try:
        p = json.loads(v)
        return [int(x) for x in p] if isinstance(p, list) else [int(p)]
    except: return []

def _makine_id_json(lst): return json.dumps(lst)
def _gemi_id_json(lst): return json.dumps(lst)
def gun_sayisi(bas, bit): return (bit - bas).days + 1

def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    row = sql_one("SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi_id, makine_tipi_id, tarih.isoformat()))
    return row["personel_id"] if row else None

def sertifika_gecerli_mi(pid, makine_tipi_id, kontrol_tarih):
    return bool(sql_one("SELECT id FROM personel_sertifika WHERE personel_id=? AND makine_tipi_id=? AND (gecerlilik_tarihi IS NULL OR gecerlilik_tarihi >= ?)", (pid, makine_tipi_id, kontrol_tarih.isoformat())))

def iki_gun_ust_uste_mi(pid, tarih):
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND tarih=?", (pid, dun)))

def ayni_gemi_peş_pese(pid, tarih, gemi_id):
    dun = (tarih - timedelta(days=1)).isoformat()
    return bool(sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND gemi_id=? AND tarih=?", (pid, gemi_id, dun)))

def bugun_izinli_ids():
    bugun = date.today().isoformat()
    return {r["personel_id"] for r in sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (bugun,))}

def sertifika_uyarilari_al():
    bugun = date.today()
    return sql_all("""SELECT p.ad, p.soyad, m.ad AS makine, s.sertifika_adi, s.gecerlilik_tarihi
                      FROM personel_sertifika s JOIN personel p ON s.personel_id=p.id
                      JOIN makine_tipi m ON s.makine_tipi_id=m.id
                      WHERE s.gecerlilik_tarihi IS NOT NULL AND s.gecerlilik_tarihi >= ? AND s.gecerlilik_tarihi <= ?""",
                   (bugun.isoformat(), (bugun+timedelta(days=30)).isoformat()))

def bugun_plani_olustur():
    bugun = date.today().isoformat()
    gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    plan = []
    for g in gemiler:
        for gm in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (g["id"],)):
            row = sql_one("SELECT p.ad||' '||p.soyad AS isim FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.gemi_id=? AND v.makine_tipi_id=? AND v.tarih=?",
                         (g["id"], gm["makine_tipi_id"], bugun))
            plan.append({"Gemi": g["ad"], "Makine": sql_one("SELECT ad FROM makine_tipi WHERE id=?", (gm["makine_tipi_id"],))["ad"],
                         "Personel": row["isim"] if row else "⚠️ BOŞ"})
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
    css = f"<style>.cal{{font-family:system-ui;max-width:400px;margin:0 auto;background:{bg};border-radius:16px;padding:16px;}}.cal-title{{text-align:center;font-size:18px;font-weight:600;color:{tc};margin-bottom:12px;}}.cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}}.cal-hdr{{text-align:center;font-size:12px;font-weight:600;color:#aaa;padding:6px 0;}}.cal-cell{{text-align:center;padding:10px 2px;border-radius:10px;font-size:14px;font-weight:500;}}.cal-empty{{background:transparent;}}.cal-normal{{background:#3a3a3a;color:#ddd;}}.cal-izin{{background:#f3831f;color:#fff;font-weight:600;}}.cal-bugun{{background:#2b2b2b;color:#f3831f;border:2px solid #f3831f;font-weight:700;}}</style>"
    html = css + f'<div class="cal"><div class="cal-title">{AY_ADLARI[ay]} {yil}</div><div class="cal-grid">'
    for g in ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]: html += f'<div class="cal-hdr">{g}</div>'
    for _ in range(ilk): html += '<div class="cal-cell cal-empty"></div>'
    for n in range(1, son_gun+1):
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
    except: return "-"

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list"))
        makine_str = ", ".join(tum_mak.get(m, str(m)) for m in mids) if mids else "Tüm Makineler"
        ad = f"{o['ad']} {o['soyad']}"
        rows.append({"id": o["id"], "ad_soyad": ad, "vardiya": o.get("vardiya_tipi","-"),
                     "makine": makine_str, "puan": o["puan"], "zaten_atanmis": o.get("zaten_atanmis",False)})
    return rows

# ---------- ÖNERİ MOTORU ----------
def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
    mevcut = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut:
        p = sql_one("SELECT id,ad,soyad,vardiya_tipi,is_kalitesi FROM personel WHERE id=?", (mevcut,))
        if p: return [{**p, "puan":999, "uyari_8_5":p.get("vardiya_tipi")=="8_5", "zaten_atanmis":True}]
    tum = sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))")
    gemi_konum = sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,))["konum"]
    hedef_gun = hedef_tarih.weekday()
    izinli_ids = {r["personel_id"] for r in sql_all("SELECT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (hedef_tarih.isoformat(),))}
    tum_atamalar = sql_all("SELECT v.personel_id, v.gemi_id, v.makine_tipi_id, v.baslangic_saat, v.bitis_saat FROM vardiya_plan v WHERE v.tarih=?", (hedef_tarih.isoformat(),))
    atama_dict = {}
    for a in tum_atamalar:
        atama_dict.setdefault(a["personel_id"], []).append(a)

    sonuclar = []
    ayar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
    max_saat = ayar.get("max_haftalik_saat", 45)
    for p in tum:
        if cikan_id and p["id"] == cikan_id: continue
        if p["id"] in izinli_ids: continue
        vardiya = p.get("vardiya_tipi","")
        bas_saat, bit_saat = VARDIYA_SAATLERI.get(vardiya, ("08:00","08:00"))
        bas_dk, bit_dk = saat_dakika(bas_saat), saat_dakika(bit_saat)
        if bit_dk <= bas_dk: bit_dk += 24 * 60

        if p["id"] in atama_dict:
            cakisma = False
            for a in atama_dict[p["id"]]:
                a_bas, a_bit = saat_dakika(a["baslangic_saat"]), saat_dakika(a["bitis_saat"])
                if a_bit <= a_bas: a_bit += 24 * 60
                if bas_dk < a_bit and a_bas < bit_dk:
                    cakisma = True
                    break
            if cakisma and not esnek_cakisma: continue

        if vardiya == "GECE" and gemi_konum != "Gecede": continue
        if vardiya in VARDIYA_KONUM_ESLESME and gemi_konum != VARDIYA_KONUM_ESLESME[vardiya]: continue

        if vardiya != "IZINCI":
            gunler_json = p.get("vardiya_gunleri")
            if gunler_json:
                try:
                    izin_gunler = json.loads(gunler_json)
                    if isinstance(izin_gunler, list) and izin_gunler:
                        if hedef_gun not in izin_gunler: continue
                except: pass

        mids = _id_listesi(p.get("makine_tipi_id_list"))
        if mids and makine_tipi_id not in mids: continue
        if mids and not sertifika_gecerli_mi(p["id"], makine_tipi_id, hedef_tarih): continue

        gids = _id_listesi(p.get("gemi_id_list"))
        if p.get("gemi_id") and p["gemi_id"] not in gids: gids.append(p["gemi_id"])
        if gids and gemi_id not in gids: continue
        if p.get("carkci_ile_sorun"): continue

        if not dinlenme_suresi_kontrol(p["id"], hedef_tarih, bas_saat): continue
        if haftalik_calisma_saati(p["id"], hedef_tarih) + (bit_dk - bas_dk)/60.0 > max_saat: continue

        performans_notu_metni = p.get("performans_notu") or ""
        carkci_notu_metni = p.get("carkci_sorun_notu") or ""
        nlp_puan = nlp_skor(performans_notu_metni) + nlp_skor(carkci_notu_metni)
        nlp_etki = nlp_puan * 25
        kalite = p.get("is_kalitesi") or 3
        if kalite <= 2: kalite_puan = -30
        elif kalite == 3: kalite_puan = 0
        elif kalite == 4: kalite_puan = 10
        else: kalite_puan = 20
        ust_uste_ceza = -20 if iki_gun_ust_uste_mi(p["id"], hedef_tarih) else 0
        pespese_cezasi = -15 if ayni_gemi_peş_pese(p["id"], hedef_tarih, gemi_id) else 0
        vardiya_puan = {"IZINCI":100, "TERSANE":95, "GECE":105, "GRUPCU":80, "SABIT":60, "8_5":40}.get(vardiya, 50)
        toplam_puan = vardiya_puan + kalite_puan + nlp_etki + pespese_cezasi + ust_uste_ceza
        if vardiya == "IZINCI": toplam_puan += 200
        sonuclar.append({**p, "puan":toplam_puan, "uyari_8_5":vardiya=="8_5", "zaten_atanmis":False,
                         "bas_saat":bas_saat, "bit_saat":bit_saat})
    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

# ---------- PDF ----------
class PDFRapor(FPDF):
    def header(self):
        self.set_font('Arial','B',12)
        self.cell(0,10,'Ordino Yagci Planlamasi - Rapor',0,1,'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial','I',8)
        self.cell(0,10,f'Sayfa {self.page_no()}/{{nb}}',0,0,'C')

def pdf_rapor_olustur(tip="aylik_ozet", ay=None, yil=None, baslangic=None, bitis=None):
    pdf = PDFRapor()
    pdf.alias_nb_pages()
    pdf.add_page()
    def tr_to_en(t): return t.translate(str.maketrans('ığüşöçİĞÜŞÖÇ','igusocIGUSOC'))
    if tip == "aylik_ozet":
        if not ay: ay = date.today().month
        if not yil: yil = date.today().year
        bas = date(yil, ay, 1)
        son = date(yil, ay, _cal.monthrange(yil, ay)[1])
        pdf.set_font('Arial','B',14)
        pdf.cell(0,10,tr_to_en(f'Aylik Personel Ozeti - {AY_ADLARI[ay]} {yil}'),0,1,'C')
        pdf.ln(5)
        for p in sql_all("SELECT * FROM personel ORDER BY ad"):
            izin_gun = sum(max(0, (min(date.fromisoformat(i["bitis"]),son)-max(date.fromisoformat(i["baslangic"]),bas)).days+1)
                           for i in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=? AND baslangic<=? AND bitis>=?",
                                           (p["id"], son.isoformat(), bas.isoformat())))
            calisma = sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih>=? AND tarih<=?",
                             (p["id"], bas.isoformat(), son.isoformat()))["c"]
            pdf.cell(50,7,tr_to_en(f"{p['ad']} {p['soyad']}"),1)
            pdf.cell(30,7,str(calisma),1); pdf.cell(30,7,str(izin_gun),1); pdf.cell(30,7,str(calisma+izin_gun),1); pdf.ln()
    else:
        pdf.set_font('Arial','B',14); pdf.cell(0,10,'Vardiya Plani',0,1,'C'); pdf.ln(5)
        rows = sql_all("""SELECT v.tarih,g.ad AS gemi,m.ad AS makine,p.ad||' '||p.soyad AS personel
                         FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id
                         JOIN personel p ON v.personel_id=p.id
                         WHERE v.tarih BETWEEN ? AND ? ORDER BY v.tarih DESC""",
                      (baslangic.isoformat(), bitis.isoformat()))
        for r in rows:
            pdf.cell(40,7,r['tarih'],1); pdf.cell(50,7,tr_to_en(r['gemi']),1)
            pdf.cell(40,7,tr_to_en(r['makine']),1); pdf.cell(40,7,tr_to_en(r['personel']),1); pdf.ln()
    path = Path(__file__).parent / f"rapor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(str(path))
    return path

# ---------- INIT DB ----------
def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS gemi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL, kod TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS makine_tipi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS gemi_makine (
        id INTEGER PRIMARY KEY AUTOINCREMENT, gemi_id INTEGER NOT NULL, makine_tipi_id INTEGER NOT NULL,
        FOREIGN KEY(gemi_id) REFERENCES gemi(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE,
        UNIQUE(gemi_id, makine_tipi_id))""")
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
        UNIQUE(personel_id, gemi_id, makine_tipi_id, tarih))""")
    c.execute("""CREATE TABLE IF NOT EXISTS personel_sertifika (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL, sertifika_adi TEXT, gecerlilik_tarihi TEXT, notlar TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS performans_gecmis (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        tarih TEXT NOT NULL, puan INTEGER NOT NULL, kaynak TEXT DEFAULT 'manuel',
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS vardiya_talebi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        talep_eden_id INTEGER NOT NULL,
        talep_tarih TEXT NOT NULL,
        gemi_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL,
        durum TEXT DEFAULT 'Beklemede',
        FOREIGN KEY(talep_eden_id) REFERENCES personel(id),
        FOREIGN KEY(gemi_id) REFERENCES gemi(id),
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id))""")
    try: c.execute("ALTER TABLE personel ADD COLUMN yillik_izin_hakki INTEGER")
    except: pass
    conn.commit()
    conn.close()

def test_verisi_olustur():
    for t in ["vardiya_plan","personel_sertifika","performans_gecmis","carkci","izin","personel","gemi_makine","makine_tipi","gemi"]:
        sql_run(f"DELETE FROM {t}")
    gemiler = [
        ("KABATEPE", "G101", "Tersane"),
        ("M/T ATLANTIC", "G202", "Gecede"),
        ("M/V BOGAZICI", "G303", "Dışarıda"),
        ("T/S CINAR", "G404", "Tersane"),
        ("M/V DENIZ YILDIZI", "G505", "Gecede")
    ]
    for ad, kod, konum in gemiler:
        sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)", (ad, kod, konum))
    gemi_ids = [r["id"] for r in sql_all("SELECT id FROM gemi")]
    for m in ["Dizel Motor", "Kompresor", "Pompa", "Jenerator"]:
        sql_run("INSERT INTO makine_tipi(ad) VALUES(?)", (m,))
    makine_ids = [r["id"] for r in sql_all("SELECT id FROM makine_tipi")]
    eslesmeler = [
        (gemi_ids[0], [makine_ids[0], makine_ids[1]]),
        (gemi_ids[1], [makine_ids[1], makine_ids[2], makine_ids[3]]),
        (gemi_ids[2], [makine_ids[0], makine_ids[2]]),
        (gemi_ids[3], [makine_ids[3]]),
        (gemi_ids[4], [makine_ids[0], makine_ids[1], makine_ids[2], makine_ids[3]])
    ]
    for gid, mids in eslesmeler:
        for mid in mids:
            sql_run("INSERT INTO gemi_makine(gemi_id, makine_tipi_id) VALUES(?,?)", (gid, mid))
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
        ("YEDEK2","KISI",[],[],"IZINCI",[],4,"İskelede","evrensel yedek")
    ]
    for ad,soyad,gemi_list,makine_list,vardiya,gunler,kalite,durum,p_not in personeller:
        gemi_id = gemi_list[0] if gemi_list else None
        mak_id = makine_list[0] if makine_list else None
        sql_run("INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ad,soyad,gemi_id,_gemi_id_json(gemi_list),mak_id,_makine_id_json(makine_list),vardiya,json.dumps(gunler),kalite,durum,p_not))
    personel_rows = sql_all("SELECT id,ad,soyad FROM personel")
    p_map = {f"{p['ad']} {p['soyad']}": p["id"] for p in personel_rows}
    bugun = date.today()
    sql_run("INSERT INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
            (p_map["Ahmet YILMAZ"], bugun.isoformat(), (bugun+timedelta(days=6)).isoformat(),7,"haftalık izin"))
    sql_run("INSERT INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
            (p_map["Veli SAHIN"], (bugun-timedelta(days=1)).isoformat(), bugun.isoformat(),2,"kısa izin"))
    sql_run("INSERT INTO personel_sertifika(personel_id,makine_tipi_id,sertifika_adi,gecerlilik_tarihi) VALUES(?,?,?,?)",
            (p_map["Mehmet DEMIR"], makine_ids[2], "Kompresor Yetkisi", (bugun+timedelta(days=30)).isoformat()))
    st.success("Test verisi oluşturuldu!")
    st.rerun()

# ---------- AYARLAR ----------
def ayarlar_sayfasi():
    st.subheader("⚙️ Ayarlar")
    ayar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
    min_din = st.number_input("Minimum Dinlenme (saat)", value=ayar["min_dinlenme_suresi_saat"])
    max_hafta = st.number_input("Maks. Haftalık Çalışma (saat)", value=ayar["max_haftalik_saat"])
    izin_hakki = st.number_input("Yıllık İzin Hakkı (gün)", value=ayar["yillik_izin_hakki"])
    if btn("Kaydet", key="ayar_kaydet", caption="Ayarları günceller"):
        st.session_state.ayarlar = {"min_dinlenme_suresi_saat": min_din, "max_haftalik_saat": max_hafta, "yillik_izin_hakki": izin_hakki}
        st.success("Ayarlar güncellendi.")

# ---------- SAYFALAR ----------
def _sayfa_yapboz():
    st.subheader("🧩 İnteraktif Yapboz")
    c_tarih, c_btns = st.columns([3, 1])
    with c_tarih:
        sec_tarih = st.date_input("Tarih", value=date.today(), key="yapboz_tarih")
    with c_btns:
        st.write("")
        cols_hafta = st.columns(2)
        if cols_hafta[0].button("⬅️ Hafta", key="yapboz_hafta_geri"):
            st.caption("Önceki haftaya gider")
            st.session_state.yapboz_tarih = st.session_state.yapboz_tarih - timedelta(days=7)
            st.rerun()
        if cols_hafta[1].button("Hafta ➡️", key="yapboz_hafta_ileri"):
            st.caption("Sonraki haftaya gider")
            st.session_state.yapboz_tarih = st.session_state.yapboz_tarih + timedelta(days=7)
            st.rerun()

    gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    tum_makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not tum_makineler:
        st.warning("Gemi ve makine ekleyin.")
        return

    col1, col2 = st.columns(2)
    with col1:
        if btn("🧹 Tüm Atamaları Temizle", key="yapboz_temizle", caption="Seçili tarihteki tüm vardiyaları siler", type="secondary"):
            sql_run("DELETE FROM vardiya_plan WHERE tarih=?", (sec_tarih.isoformat(),))
            audit_log("kullanıcı", "temizle", f"tarih:{sec_tarih.isoformat()}")
            st.toast("Tüm atamalar temizlendi!", icon="🧹"); st.rerun()
    with col2:
        if btn("🤖 Hepsini Otomatik Doldur", key="yapboz_otomatik", caption="Sistemin önerdiği en uygun personelle boşlukları doldurur"):
            with st.spinner("Otomatik dolduruluyor..."):
                for gemi in gemiler:
                    gemi_mak = sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],))
                    for gm in gemi_mak:
                        mak_id = gm["makine_tipi_id"]
                        if not vardiya_plani_kontrol(gemi["id"], mak_id, sec_tarih):
                            oneri = onerileri_hesapla(gemi["id"], mak_id, sec_tarih, limit=1)
                            if oneri and not oneri[0].get("zaten_atanmis"):
                                bas_saat, bit_saat = VARDIYA_SAATLERI.get(oneri[0]["vardiya_tipi"], ("08:00","08:00"))
                                try:
                                    sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                            (oneri[0]["id"], gemi["id"], mak_id, sec_tarih.isoformat(), bas_saat, bit_saat))
                                    audit_log("otomatik", "atama", f"{oneri[0]['id']} -> gemi:{gemi['id']} mak:{mak_id} tarih:{sec_tarih}")
                                except sqlite3.IntegrityError: pass
            st.toast("Tüm boş pozisyonlar dolduruldu!", icon="🤖"); st.rerun()

    izinli = bugun_izinli_ids()
    for gemi in gemiler:
        gemi_mak = sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],))
        if not gemi_mak:
            st.warning(f"{gemi['ad']} için makine atanmamış!")
            continue
        g_makineler = [m for m in tum_makineler if m["id"] in [r["makine_tipi_id"] for r in gemi_mak]]
        st.markdown(f"### 🚢 {gemi['ad']}")
        cols = st.columns(len(g_makineler))
        for i, mak in enumerate(g_makineler):
            with cols[i]:
                mevcut = vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih)
                if mevcut:
                    p = sql_one("SELECT id,ad,soyad,vardiya_tipi,durum,is_kalitesi FROM personel WHERE id=?", (mevcut,))
                    if p:
                        renk = VARDIYA_RENKLERI.get(p['vardiya_tipi'], '#3a3a4e')
                        opacity = {1:0.5,2:0.6,3:0.75,4:0.9,5:1.0}.get(p['is_kalitesi'] or 3, 0.8)
                        st.markdown(f"<div style='background:{renk};padding:8px;border-radius:8px;color:white;text-align:center;font-weight:bold;opacity:{opacity}'>{p['ad']} {p['soyad']}<br>({p['vardiya_tipi']}) {p.get('durum','')}<br>⭐{p['is_kalitesi']}</div>", unsafe_allow_html=True)
                    col_x, col_d = st.columns([1,1])
                    with col_x:
                        if btn("❌ Çıkar", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Bu personeli vardiyadan çıkarır"):
                            sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi["id"], mak["id"], sec_tarih.isoformat()))
                            audit_log("kullanıcı", "çıkar", f"gemi:{gemi['id']} mak:{mak['id']} tarih:{sec_tarih}")
                            st.toast("Personel çıkarıldı", icon="❌"); st.rerun()
                    with col_d:
                        if btn("🔄 Değiştir", key=f"degistir_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Çalışanı çıkarıp hemen yeni öneri getirir"):
                            sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi["id"], mak["id"], sec_tarih.isoformat()))
                            oneriler = onerileri_hesapla(gemi["id"], mak["id"], sec_tarih, limit=5)
                            st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = oneriler
                            st.rerun()
                else:
                    st.warning("Boş")
                    uygun = ["Seçiniz..."]
                    hedef_gun = sec_tarih.weekday()
                    for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))"):
                        if p["id"] in izinli: continue
                        if p["vardiya_tipi"] != "IZINCI":
                            gunler_json = p.get("vardiya_gunleri")
                            if gunler_json:
                                try:
                                    izin_gunler = json.loads(gunler_json)
                                    if isinstance(izin_gunler, list) and izin_gunler and hedef_gun not in izin_gunler:
                                        continue
                                except: pass
                        mids = _id_listesi(p.get("makine_tipi_id_list"))
                        if mids and mak["id"] not in mids: continue
                        if mids and not sertifika_gecerli_mi(p["id"], mak["id"], sec_tarih): continue
                        gids = _id_listesi(p.get("gemi_id_list"))
                        if p.get("gemi_id"): gids.append(p["gemi_id"])
                        if gids and gemi["id"] not in gids: continue
                        if p.get("carkci_ile_sorun"): continue
                        uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum','')})")
                    if len(uygun) == 1:
                        st.caption("Uygun personel yok.")
                    else:
                        sec = st.selectbox("Manuel Seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                        if sec != "Seçiniz...":
                            pid_row = sql_one("SELECT id,vardiya_tipi FROM personel WHERE ad||' '||soyad=?", (sec.split(" (")[0],))
                            if pid_row:
                                bas_saat, bit_saat = VARDIYA_SAATLERI.get(pid_row["vardiya_tipi"], ("08:00","08:00"))
                                if iki_gun_ust_uste_mi(pid_row["id"], sec_tarih):
                                    st.warning("⚠️ Bu personel dün de çalıştı.")
                                try:
                                    sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                            (pid_row["id"], gemi["id"], mak["id"], sec_tarih.isoformat(), bas_saat, bit_saat))
                                    audit_log("manuel", "atama", f"{pid_row['id']} -> gemi:{gemi['id']} mak:{mak['id']} tarih:{sec_tarih}")
                                    st.toast("Personel atandı!"); st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Bu atama zaten mevcut!")

                    if btn("🔍 Öneri Al (5)", key=f"onerbtn_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="En uygun 5 personeli listeler"):
                        oneriler = onerileri_hesapla(gemi["id"], mak["id"], sec_tarih, limit=5)
                        st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = oneriler
                        st.rerun()

                    if f"oneriler_{gemi['id']}_{mak['id']}" in st.session_state and st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"]:
                        oneriler = st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"]
                        st.markdown("**Önerilen Personel:**")
                        for o in oneriler:
                            col_o1, col_o2 = st.columns([4,1])
                            with col_o1:
                                st.write(f"{o['ad']} {o['soyad']} ({o['vardiya_tipi']}) - Puan: {o['puan']}")
                            with col_o2:
                                if btn("✅ Ata", key=f"ata_{gemi['id']}_{mak['id']}_{o['id']}", caption="Bu kişiyi seçili pozisyona atar"):
                                    if o.get("zaten_atanmis"):
                                        st.error("Zaten atanmış!")
                                    else:
                                        if iki_gun_ust_uste_mi(o["id"], sec_tarih):
                                            st.warning("⚠️ Dün çalıştı, yine de atanıyor.")
                                        bas_saat, bit_saat = VARDIYA_SAATLERI.get(o["vardiya_tipi"], ("08:00","08:00"))
                                        try:
                                            sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                    (o["id"], gemi["id"], mak["id"], sec_tarih.isoformat(), bas_saat, bit_saat))
                                            audit_log("öneri", "atama", f"{o['id']} -> gemi:{gemi['id']} mak:{mak['id']} tarih:{sec_tarih}")
                                            st.toast(f"{o['ad']} {o['soyad']} atandı!"); del st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"]; st.rerun()
                                        except sqlite3.IntegrityError:
                                            st.error("Bu atama zaten mevcut!")
        st.divider()

def _sayfa_acil():
    st.subheader("⚡ Acil Panel")
    gem = sql_all("SELECT id,ad,konum FROM gemi ORDER BY ad")
    mak = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    bugun = date.today()
    izinli = bugun_izinli_ids()

    with st.expander("📅 Dün Kim Çalıştı?"):
        dun = (bugun - timedelta(days=1)).isoformat()
        col_d1, col_d2 = st.columns(2)
        with col_d1: dun_gemi = st.selectbox("Gemi", [g["id"] for g in gem], format_func=lambda i: next(g["ad"] for g in gem if g["id"]==i), key="dun_gemi")
        with col_d2: dun_mak = st.selectbox("Makine", [m["id"] for m in mak], format_func=lambda i: next(m["ad"] for m in mak if m["id"]==i), key="dun_mak")
        if btn("🔍 Sorgula", key="dun_sorgu", caption="Dünkü pozisyonun sahibini gösterir"):
            dun_atama = sql_one("SELECT p.ad||' '||p.soyad AS isim, v.baslangic_saat, v.bitis_saat FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.gemi_id=? AND v.makine_tipi_id=? AND v.tarih=?", (dun_gemi, dun_mak, dun))
            if dun_atama: st.success(f"Dün: **{dun_atama['isim']}** ({dun_atama['baslangic_saat']} - {dun_atama['bitis_saat']})")
            else: st.info("Dün bu pozisyonda kimse çalışmamış.")

    with st.expander("🏝️ Personeli İskeleye Çıkar"):
        isk_personel = st.selectbox("Personel Seç", [f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 AND durum='Gemide' ORDER BY ad")], key="iskele_cikar")
        if btn("🔄 İskeleye Çıkar", key="btn_iskele", caption="Personeli 'İskelede' yapar"):
            if isk_personel:
                pid = int(isk_personel.split("ID:")[1].replace(")",""))
                sql_run("UPDATE personel SET durum='İskelede' WHERE id=?", (pid,))
                audit_log("acil", "iskele", f"personel:{pid}")
                st.toast("Personel iskeleye çıkarıldı!"); st.rerun()

    with st.expander("🚀 İskeledekileri Akıllı Dağıt"):
        if btn("🧠 Akıllı Dağıtım Başlat", key="btn_akilli_dagit", caption="İskelede/İZİNCİ personeli boş yerlere otomatik yerleştirir"):
            with st.spinner("Akıllı dağıtım yapılıyor..."):
                iskeledekiler = sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum='İskelede')")
                if not iskeledekiler: st.warning("Dağıtılacak uygun personel yok.")
                else:
                    atanan = 0
                    for p in sorted(iskeledekiler, key=lambda x: 0 if x["vardiya_tipi"]=="IZINCI" else 1):
                        gids = _id_listesi(p.get("gemi_id_list")) or []
                        if p.get("gemi_id"): gids.append(p["gemi_id"])
                        mids = _id_listesi(p.get("makine_tipi_id_list"))
                        for gid in (gids if gids else [g["id"] for g in gem]):
                            gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gid,))]
                            for mid in (mids if mids else gemi_mak):
                                if vardiya_plani_kontrol(gid, mid, bugun): continue
                                oneri_listesi = onerileri_hesapla(gid, mid, bugun, limit=1)
                                if oneri_listesi and oneri_listesi[0]["id"] == p["id"]:
                                    bas_saat, bit_saat = VARDIYA_SAATLERI.get(p["vardiya_tipi"], ("08:00","08:00"))
                                    try:
                                        sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                (p["id"], gid, mid, bugun.isoformat(), bas_saat, bit_saat))
                                        sql_run("UPDATE personel SET durum='Gemide' WHERE id=?", (p["id"],))
                                        audit_log("akıllı", "atama", f"{p['id']} -> gemi:{gid} mak:{mid}")
                                        atanan += 1; break
                                    except sqlite3.IntegrityError: pass
                            if atanan: break
                    if atanan > 0: st.toast(f"{atanan} personel dağıtıldı!"); st.rerun()
                    else: st.warning("Hiçbir personel yerleştirilemedi.")

    st.divider(); st.markdown("### 👤 Boştakiler")
    if btn("🔍 Listele", key="bbos", caption="Bugün hiç görevi olmayan personeli listeler"):
        bos = []
        for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))"):
            if p["id"] in izinli: continue
            if sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih=?", (p["id"], bugun.isoformat()))["c"] == 0:
                gemi_adi = next((g["ad"] for g in gem if g["id"]==p["gemi_id"]), "Tüm Gemiler") if p["gemi_id"] else "Tüm Gemiler"
                mids = _id_listesi(p.get("makine_tipi_id_list"))
                mak_ad = ", ".join(next((m["ad"] for m in mak if m["id"]==mid), "") for mid in mids) if mids else "Tüm Makineler"
                bos.append(f"- **{p['ad']} {p['soyad']}** ({p['vardiya_tipi']}) → {gemi_adi} | Makine: {mak_ad} [{p.get('durum','')}]")
        if bos: st.success(f"{len(bos)} kişi boşta"); [st.write(b) for b in bos]
        else: st.info("Boşta kimse yok")

    st.divider(); st.markdown("### 🏝️ İskelede Bekleyenler")
    if btn("🔍 İskele Listesi", key="biskele", caption="'İskelede' durumundaki personeli gösterir"):
        isk = sql_all("SELECT ad,soyad,vardiya_tipi,gemi_id,makine_tipi_id_list FROM personel WHERE aktif=1 AND durum='İskelede'")
        if isk:
            st.success(f"{len(isk)} kişi iskelede:")
            for p in isk:
                gemi_adi = next((g["ad"] for g in gem if g["id"]==p["gemi_id"]), "Tüm Gemiler") if p["gemi_id"] else "Tüm Gemiler"
                mids = _id_listesi(p.get("makine_tipi_id_list"))
                mak_ad = ", ".join(next((m["ad"] for m in mak if m["id"]==mid), "") for mid in mids) if mids else "Tüm Makineler"
                st.write(f"- **{p['ad']} {p['soyad']}** ({p['vardiya_tipi']}) → {gemi_adi} | Makine: {mak_ad}")
        else: st.info("İskelede bekleyen yok")

    st.divider(); st.markdown("### 🏗️ Tersaneye Uygunlar")
    if btn("🔍 Tersane Listesi", key="btersane", caption="Tersanedeki gemilere uygun personeli listeler"):
        ters_gem = [g for g in gem if g.get("konum")=="Tersane"]
        if not ters_gem: st.warning("Tersanede gemi yok")
        else:
            uygun = []
            for g in ters_gem:
                for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND (gemi_id=? OR gemi_id_list LIKE ? OR (gemi_id IS NULL AND gemi_id_list='[]'))", (g["id"], f'%{g["id"]}%')):
                    if p["id"] in izinli: continue
                    mids = _id_listesi(p.get("makine_tipi_id_list"))
                    gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (g["id"],))]
                    for m in (mids if mids else gemi_mak):
                        if sertifika_gecerli_mi(p["id"], m, bugun):
                            uygun.append(f"- {p['ad']} {p['soyad']} ({p['vardiya_tipi']}) → {g['ad']} / {next((ma['ad'] for ma in mak if ma['id']==m),'')} [{p.get('durum','')}]")
            if uygun: st.success(f"{len(uygun)} uygun:"); [st.write(u) for u in uygun[:20]]
            else: st.info("Uygun yok")

    st.divider(); st.markdown("### 📞 Anlık İzin Yerine")
    c1, c2 = st.columns(2)
    with c1: cik = st.selectbox("İzin İsteyen", [f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")], key="acil_cik"); cik_id = int(cik.split("ID:")[1].replace(")","")) if cik else None
    with c2:
        hg = st.selectbox("Gemi", [g["id"] for g in gem], format_func=lambda i: next(g["ad"] for g in gem if g["id"]==i), key="acil_gemi")
        gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (hg,))]
        hm_secenek = [m for m in mak if m["id"] in gemi_mak]
        if not hm_secenek: st.warning("Seçili gemide makine yok"); return
        hm = st.selectbox("Makine", [m["id"] for m in hm_secenek], format_func=lambda i: next((m["ad"] for m in hm_secenek if m["id"]==i), ""), key="acil_mak")
    if btn("🚨 Öner (5)", key="acil_oner", caption="İzin isteyenin yerine en uygun 5 adayı getirir"):
        on = onerileri_hesapla(hg, hm, bugun, cikan_id=cik_id, limit=5)
        if not on: st.warning("Uygun yok")
        else:
            for i,o in enumerate(on):
                msg = f"{i+1}. {o['ad']} {o['soyad']} ({o['vardiya_tipi']}) - Puan:{o['puan']}"
                if o.get("ust_uste"): msg += " 🔄 DÜN ÇALIŞTI"
                st.success(msg)
                if o.get("uyari_8_5"): st.warning("⚠️ 8/5")
                if o.get("fazla_mesai"): st.warning("⚠️ Fazla mesai")
                if o.get("dinlenme_ihlali"): st.warning("🌙 Dinlenme ihlali")
                if o.get("pespese"): st.warning("🔁 Aynı gemide dün çalıştı")

def _sayfa_excel():
    st.subheader("🚢 Gemiler & Makine")
    with st.form("f_gemi"):
        st.write("##### Yeni Gemi Ekle")
        c1,c2,c3 = st.columns(3)
        gad = c1.text_input("Gemi Adı", key="gemi_adi")
        gkd = c2.text_input("Kod (opsiyonel)", key="gemi_kod")
        kon = c3.selectbox("Konum", GEMI_KONUMLARI, index=3, key="gemi_konum")
        makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
        if makineler:
            sec_mak = st.multiselect("Gemideki Makineler", [m["id"] for m in makineler],
                                     format_func=lambda i: next((m["ad"] for m in makineler if m["id"]==i), ""),
                                     key="gm_mak_sec")
        else:
            st.info("Önce makine tipi ekleyin.")
            sec_mak = []
        if st.form_submit_button("➕ Gemi Ekle"):
            st.caption("Gemi bilgilerini ve seçili makineleri kaydeder")
            if not gad: st.error("Gemi adı zorunludur.")
            else:
                try:
                    sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",
                            (gad.strip().upper(), gkd.strip().upper() if gkd else None,
                             None if kon == "Belirtilmedi" else kon))
                    new_gemi = sql_one("SELECT id FROM gemi WHERE ad=?", (gad.strip().upper(),))
                    if new_gemi and sec_mak:
                        for mid in sec_mak:
                            sql_run("INSERT INTO gemi_makine(gemi_id, makine_tipi_id) VALUES(?,?)", (new_gemi["id"], mid))
                    audit_log("kullanici", "gemi_ekle", f"{gad}")
                    st.toast("Gemi ve makineleri eklendi!"); st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")

    with st.expander("➕ Makine Tipi Ekle"):
        with st.form("f_makine"):
            mad_val = st.text_input("Makine Tipi Adı")
            if st.form_submit_button("➕ Makine Ekle"):
                st.caption("Yeni makine tipi ekler")
                if not mad_val: st.error("Makine adı zorunlu")
                else:
                    try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)", (mad_val.strip().upper(),))
                    except: st.warning("Bu makine tipi zaten var")
                    else:
                        audit_log("kullanici", "makine_ekle", f"{mad_val}")
                        st.toast("Makine tipi eklendi!"); st.rerun()

    st.divider()
    g_rows = sql_all("SELECT g.id,g.ad,g.kod,g.konum,COUNT(p.id) AS personel FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad")
    st.dataframe(pd.DataFrame(g_rows), width='stretch')

    with st.expander("🔗 Gemi-Makine Eşleştirme (Düzenle)"):
        gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
        makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
        sec_gemi = st.selectbox("Gemi", [g["id"] for g in gemiler], format_func=lambda i: next((g["ad"] for g in gemiler if g["id"]==i), ""), key="gm_gemi")
        if sec_gemi:
            mevcut_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (sec_gemi,))]
            sec_mak = st.multiselect("Gemideki Makineler", [m["id"] for m in makineler],
                                     default=mevcut_mak, format_func=lambda i: next((m["ad"] for m in makineler if m["id"]==i), ""),
                                     key="gm_mak")
            if btn("Güncelle", key="gm_guncelle", caption="Seçili makineleri gemiyle eşleştirir"):
                sql_run("DELETE FROM gemi_makine WHERE gemi_id=?", (sec_gemi,))
                for mid in sec_mak:
                    sql_run("INSERT INTO gemi_makine(gemi_id, makine_tipi_id) VALUES(?,?)", (sec_gemi, mid))
                audit_log("kullanici", "gemi_makine_guncelle", f"gemi:{sec_gemi}")
                st.toast("Gemi-makine eşleştirmesi güncellendi!"); st.rerun()

    with st.expander("👥 Gemi Bazlı Personel Listesi"):
        sec_gemi2 = st.selectbox("Gemi Seçin", [g["id"] for g in g_rows], format_func=lambda i: next((g["ad"] for g in g_rows if g["id"]==i), ""), key="gemi_bazli")
        if sec_gemi2:
            per_rows = sql_all("SELECT ad,soyad,vardiya_tipi,durum,makine_tipi_id_list FROM personel WHERE aktif=1 AND (gemi_id=? OR gemi_id_list LIKE ?)", (sec_gemi2, f'%{sec_gemi2}%'))
            if per_rows:
                tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
                for pr in per_rows:
                    mids = _id_listesi(pr.get("makine_tipi_id_list"))
                    pr["makineler"] = ", ".join(tum_mak.get(m, "") for m in mids) if mids else "Tüm Makineler"
                st.dataframe(pd.DataFrame(per_rows)[["ad","soyad","vardiya_tipi","durum","makineler"]], width='stretch')
            else:
                st.info("Bu gemide personel yok.")

    c1, c2 = st.columns(2)
    with c1:
        with st.expander("✏️ Gemi Düzenle/Sil"):
            if g_rows:
                gm = {f"{r['ad']} (ID:{r['id']})": r for r in g_rows}
                gs = st.selectbox("Gemi", list(gm.keys()), key="gds"); gr = gm[gs]
                na = st.text_input("Ad", gr["ad"] or "", key="gna"); nk = st.text_input("Kod", gr["kod"] or "", key="gnk")
                nkon = st.selectbox("Konum", GEMI_KONUMLARI, index=GEMI_KONUMLARI.index(gr["konum"]) if gr["konum"] in GEMI_KONUMLARI else 3, key="gnkon")
                if btn("Güncelle", key="bgd", caption="Geminin adını, kodunu veya konumunu günceller"):
                    if not na: st.error("Ad boş")
                    else:
                        sql_run("UPDATE gemi SET ad=?,kod=?,konum=? WHERE id=?", (na.strip().upper(), nk.strip().upper() if nk else None, nkon if nkon != "Belirtilmedi" else None, gr["id"]))
                        audit_log("kullanici", "gemi_guncelle", f"{gr['id']}"); st.toast("Gemi güncellendi!"); st.rerun()
                if btn("Sil", key="bgs", caption="Gemiyi tüm bağlantılarıyla siler"):
                    bagli_personel = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=? OR gemi_id_list LIKE ?", (gr["id"], f'%{gr["id"]}%'))
                    if bagli_personel and bagli_personel["c"] > 0:
                        st.error("Bağlı personel var, önce onları başka gemiye atayın veya silin.")
                    else:
                        sql_run("DELETE FROM gemi_makine WHERE gemi_id=?", (gr["id"],))
                        sql_run("DELETE FROM carkci WHERE gemi_id=?", (gr["id"],))
                        sql_run("DELETE FROM vardiya_plan WHERE gemi_id=?", (gr["id"],))
                        sql_run("DELETE FROM gemi WHERE id=?", (gr["id"],))
                        audit_log("kullanici", "gemi_sil", f"{gr['id']}"); st.toast("Gemi silindi!"); st.rerun()
    with c2:
        with st.expander("✏️ Makine Düzenle/Sil"):
            mr = sql_all("SELECT m.id,m.ad,COUNT(p.id) AS c FROM makine_tipi m LEFT JOIN personel p ON p.makine_tipi_id=m.id GROUP BY m.id ORDER BY m.ad")
            if mr:
                mm = {f"{r['ad']} (ID:{r['id']})": r for r in mr}
                ms = st.selectbox("Makine", list(mm.keys()), key="mds"); mrow = mm[ms]
                nm = st.text_input("Ad", mrow["ad"] or "", key="mna")
                if btn("Güncelle", key="bmd", caption="Makine adını günceller"):
                    if not nm: st.error("Ad boş")
                    else:
                        sql_run("UPDATE makine_tipi SET ad=? WHERE id=?", (nm.strip().upper(), mrow["id"]))
                        audit_log("kullanici", "makine_guncelle", f"{mrow['id']}"); st.toast("Makine güncellendi!"); st.rerun()
                if btn("Sil", key="bms", caption="Makineyi siler (bağlı personel varsa izin vermez)"):
                    if mrow["c"] > 0: st.error("Bağlı personel var")
                    else:
                        sql_run("DELETE FROM gemi_makine WHERE makine_tipi_id=?", (mrow["id"],))
                        sql_run("DELETE FROM vardiya_plan WHERE makine_tipi_id=?", (mrow["id"],))
                        sql_run("DELETE FROM makine_tipi WHERE id=?", (mrow["id"],))
                        audit_log("kullanici", "makine_sil", f"{mrow['id']}"); st.toast("Makine silindi!"); st.rerun()

def _sayfa_personel():
    st.subheader("👷 Personel")
    gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    arama = st.text_input("🔍 Personel Ara", key="personel_arama")
    c1, c2 = st.columns(2)
    with c1:
        fv = st.selectbox("Vardiya Tipi", ["Tümü"] + VARDIYA_TIPLERI, key="fv_select")
        if fv == "Tümü": fv = None
    with c2:
        fa = st.radio("Durum", ["Tümü", "Aktif", "Pasif"], key="fa_radio", horizontal=True)
        if fa == "Aktif": fa = 1
        elif fa == "Pasif": fa = 0
        else: fa = None
    q = "SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,p.is_kalitesi,p.performans_notu,p.durum,p.aktif FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id"
    params = ()
    where_clauses = []
    if fv:
        where_clauses.append("p.vardiya_tipi = ?")
        params += (fv,)
    if fa is not None:
        where_clauses.append("p.aktif = ?")
        params += (fa,)
    if where_clauses:
        q += " WHERE " + " AND ".join(where_clauses)
    rows = sql_all(q + " ORDER BY p.id DESC", params)
    if arama:
        arama = arama.upper()
        rows = [r for r in rows if arama in f"{r['ad']} {r['soyad']} {r['vardiya_tipi']} {r.get('gemi','')} {r.get('durum','')}".upper()]
    with st.expander("🔄 Toplu Durum Değiştir"):
        sec_personel = st.multiselect("Personel seç", [f"{r['ad']} {r['soyad']} (ID:{r['id']})" for r in rows], key="toplu_durum_personel")
        yeni_durum = st.selectbox("Yeni Durum", PERSONEL_DURUM, key="toplu_yeni_durum")
        if btn("Durumları Güncelle", key="toplu_durum_btn", caption="Seçili personelin durumunu topluca günceller"):
            if sec_personel:
                ids = [int(p.split("ID:")[1].replace(")","")) for p in sec_personel]
                for pid in ids:
                    sql_run("UPDATE personel SET durum=? WHERE id=?", (yeni_durum, pid))
                audit_log("kullanici", "toplu_durum", f"{len(ids)} personel")
                st.toast(f"{len(ids)} personelin durumu güncellendi!"); st.rerun()

    if not gemiler or not makineler: st.warning("Önce gemi/makine ekleyin."); return

    with st.expander("📤 Excel'den Toplu Personel Ekle"):
        st.markdown("Sütunlar: Ad, Soyad, Vardiya Tipi, Makine Tipi, Gemi, Durum, Performans Notu")
        personel_excel = st.file_uploader("Personel Excel'i", type=["xlsx", "xls"], key="toplu_personel_excel")
        if personel_excel is not None:
            try:
                df = pd.read_excel(personel_excel)
                st.dataframe(df.head(), width='stretch')
                if btn("📤 Ekle", key="btn_toplu_personel", caption="Excel'deki tüm satırları personel olarak kaydeder"):
                    eklenen = 0
                    for _, row in df.iterrows():
                        ad = str(row.get('Ad', '')).strip().upper()
                        soyad = str(row.get('Soyad', '')).strip().upper()
                        vt = str(row.get('Vardiya Tipi', '')).strip().upper()
                        makine_adi_str = str(row.get('Makine Tipi', '')).strip()
                        gemi_adi_str = str(row.get('Gemi', '')).strip().upper()
                        durum = str(row.get('Durum', 'Gemide')).strip()
                        p_not = str(row.get('Performans Notu', '')).strip() or None
                        if not ad or not soyad or not vt: continue
                        if vt not in VARDIYA_TIPLERI: continue
                        mak_ids = []
                        if makine_adi_str:
                            makine_adlari = [m.strip().upper() for m in makine_adi_str.split(",") if m.strip()]
                            for m_ad in makine_adlari:
                                mak = sql_one("SELECT id FROM makine_tipi WHERE ad=?", (m_ad,))
                                if not mak:
                                    st.warning(f"Makine '{m_ad}' bulunamadı, atlanıyor.")
                                    continue
                                mak_ids.append(mak["id"])
                        gemi = None
                        if gemi_adi_str:
                            gemi = sql_one("SELECT id FROM gemi WHERE ad=?", (gemi_adi_str,))
                            if not gemi:
                                st.warning(f"Gemi '{gemi_adi_str}' bulunamadı, atlanıyor.")
                                continue
                        if durum not in PERSONEL_DURUM: durum = "Gemide"
                        try:
                            sql_run("INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,durum,is_kalitesi,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                    (ad, soyad, gemi["id"] if gemi else None,
                                     json.dumps([gemi["id"]] if gemi else []),
                                     mak_ids[0] if mak_ids else None,
                                     json.dumps(mak_ids) if mak_ids else "[]",
                                     vt, "[]", durum, 3, p_not))
                            eklenen += 1
                        except: pass
                    if eklenen > 0: st.toast(f"{eklenen} personel eklendi!"); st.rerun()
                    else: st.warning("Eklenemedi.")
            except Exception as e: st.error(f"Excel hatası: {e}")

    with st.expander("➕ Yeni Personel"):
        c1,c2 = st.columns(2)
        ad = c1.text_input("Ad", key="p_ad"); soyad = c2.text_input("Soyad", key="p_soyad")
        vt = st.selectbox("Vardiya Tipi", VARDIYA_TIPLERI, key="p_vt")
        mak_sec = st.multiselect("Makine Tipleri", [r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="p_mak")
        gem_list = st.multiselect("Atandığı Gemiler", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="p_gem")
        sec = st.multiselect("Vardiya Günleri", GUNLER_TR, default=["Pazartesi","Çarşamba","Cuma"], key="p_vg")
        gun_json = json.dumps([GUNLER_TR.index(x) for x in sec])
        durum = st.selectbox("Durum", PERSONEL_DURUM, key="p_durum")
        is_kal = st.slider("İş Kalitesi", 1,5,3, key="p_ik")
        pn = st.text_area("Performans Notu", key="p_not")
        if btn("Kaydet", key="btn_pk", caption="Yeni personeli sisteme ekler"):
            if not ad or not soyad: st.error("Ad soyad zorunlu")
            else:
                try:
                    sql_run("INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,durum,is_kalitesi,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (ad.strip().upper(), soyad.strip().upper(),
                             gem_list[0] if gem_list else None,
                             _gemi_id_json(gem_list),
                             mak_sec[0] if mak_sec else None,
                             _makine_id_json(mak_sec) if mak_sec else "[]",
                             vt, gun_json, durum, is_kal, pn.strip() or None))
                    st.toast("Personel kaydedildi!"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")

    with st.expander("✏️ Düzenle/Sil & Sertifika"):
        pm = {f"{r['ad']} {r['soyad']} (ID:{r['id']})": r['id'] for r in sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad")}
        if not pm: st.info("Personel yok"); return
        secim = st.selectbox("Personel", list(pm.keys()), key="p_ds"); pid = pm[secim]
        mev = sql_one("SELECT * FROM personel WHERE id=?", (pid,))
        if not mev: return
        yvt = st.selectbox("Vardiya", VARDIYA_TIPLERI, index=VARDIYA_TIPLERI.index(mev["vardiya_tipi"]) if mev.get("vardiya_tipi") in VARDIYA_TIPLERI else 0, key="pd_vt")
        mids = _id_listesi(mev.get("makine_tipi_id_list"))
        ymak = st.multiselect("Makine", [r["id"] for r in makineler], default=[m for m in mids if m in [r["id"] for r in makineler]], format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="pd_mak")
        gids = _id_listesi(mev.get("gemi_id_list")) or ([mev["gemi_id"]] if mev.get("gemi_id") else [])
        ygem = st.multiselect("Gemi", [r["id"] for r in gemiler], default=[g for g in gids if g in [r["id"] for r in gemiler]], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"]==i), key="pd_gem")
        ydurum = st.selectbox("Durum", PERSONEL_DURUM, index=PERSONEL_DURUM.index(mev["durum"]) if mev.get("durum") in PERSONEL_DURUM else 0, key="pd_durum")
        ypn = st.text_area("Performans Notu", value=mev.get("performans_notu") or "", key="pd_pn")
        c1, c2 = st.columns(2)
        if c1.button("Güncelle", key="bpgu"):
            st.caption("Personel bilgilerini günceller")
            try:
                yeni_gemi_id = ygem[0] if ygem else None
                ilk_mak = int(ymak[0]) if ymak else None
                sql_run("UPDATE personel SET vardiya_tipi=?, makine_tipi_id_list=?, makine_tipi_id=?, gemi_id=?, gemi_id_list=?, durum=?, performans_notu=? WHERE id=?",
                        (yvt, _makine_id_json(ymak) if ymak else "[]", ilk_mak, yeni_gemi_id, _gemi_id_json(ygem), ydurum, ypn.strip() or None, pid))
                st.toast("Güncellendi!"); st.rerun()
            except Exception as e: st.error(f"Hata: {e}")
        if c2.button("Sil", key="bps"):
            st.caption("Personeli sistemden tamamen siler")
            for t in ["izin","vardiya_plan","personel_sertifika","performans_gecmis"]: sql_run(f"DELETE FROM {t} WHERE personel_id=?",(pid,))
            sql_run("DELETE FROM personel WHERE id=?",(pid,))
            st.toast("Silindi!"); st.rerun()
        st.markdown("---\n#### Sertifika")
        sert = sql_all("SELECT * FROM personel_sertifika WHERE personel_id=?", (pid,))
        if sert: st.dataframe(pd.DataFrame(sert), width='stretch')
        with st.form("sert_ekle", clear_on_submit=True):
            sm = st.selectbox("Makine", [r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"]==i), key="sm")
            sa = st.text_input("Sertifika Adı", key="sa"); sg = st.date_input("Geçerlilik", value=None, key="sg"); sn = st.text_input("Not", key="sn")
            if st.form_submit_button("Ekle"):
                st.caption("Yeni sertifika ekler")
                sql_run("INSERT INTO personel_sertifika VALUES(NULL,?,?,?,?,?)", (pid, sm, sa or None, sg.isoformat() if sg else None, sn or None))
                st.toast("Sertifika eklendi!"); st.rerun()
        if sert:
            sil_s = st.selectbox("Silinecek", [f"{s['sertifika_adi'] or 'Sertifika'} (ID:{s['id']})" for s in sert], key="sils")
            if btn("Sertifika Sil", key="bss", caption="Seçili sertifikayı siler"):
                sid = int(sil_s.split("ID:")[1].replace(")",""))
                sql_run("DELETE FROM personel_sertifika WHERE id=?", (sid,))
                st.toast("Silindi!"); st.rerun()

def _sayfa_izin():
    st.subheader("📅 İzin")
    pl = sql_all("SELECT id,ad,soyad,vardiya_gunleri FROM personel WHERE aktif=1 ORDER BY ad")
    if not pl: st.info("Personel yok"); return
    with st.expander("📤 Excel'den Toplu İzin Ekle"):
        st.markdown("Sütunlar: Ad, Soyad, Başlangıç, Bitiş, Not")
        izin_excel = st.file_uploader("İzin Excel'i", type=["xlsx", "xls"], key="toplu_izin_excel")
        if izin_excel is not None:
            try:
                df = pd.read_excel(izin_excel)
                st.dataframe(df.head(), width='stretch')
                if btn("📤 Ekle", key="btn_toplu_izin", caption="Excel'deki izinleri topluca sisteme aktarır"):
                    eklenen = 0
                    for _, row in df.iterrows():
                        ad = str(row.get('Ad', '')).strip().upper()
                        soyad = str(row.get('Soyad', '')).strip().upper()
                        bas_str = str(row.get('Başlangıç', '')).strip(); bit_str = str(row.get('Bitiş', '')).strip()
                        notlar = str(row.get('Not', '')).strip() or None
                        if not ad or not soyad or not bas_str or not bit_str: continue
                        p = sql_one("SELECT id FROM personel WHERE ad=? AND soyad=?", (ad, soyad))
                        if not p: continue
                        try:
                            for fmt in ["%Y-%m-%d", "%d.%m.%Y"]:
                                try: bas = datetime.strptime(bas_str, fmt).date(); break
                                except: pass
                            for fmt in ["%Y-%m-%d", "%d.%m.%Y"]:
                                try: bit = datetime.strptime(bit_str, fmt).date(); break
                                except: pass
                            gun = (bit - bas).days + 1
                            if gun > 0:
                                sql_run("INSERT INTO izin(personel_id,baslangic,bitis,gun_sayisi,notlar) VALUES(?,?,?,?,?)",
                                        (p["id"], bas.isoformat(), bit.isoformat(), gun, notlar))
                                eklenen += 1
                        except: continue
                    if eklenen > 0: st.toast(f"{eklenen} izin eklendi!"); st.rerun()
                    else: st.warning("Eklenemedi.")
            except Exception as e: st.error(f"Excel hatası: {e}")

    cf, cc = st.columns([1,1])
    with cf:
        sec = st.selectbox("Personel", pl, format_func=lambda p:f"{p['ad']} {p['soyad']}", key="izp")
        pid = sec["id"]; bas = st.date_input("Başlangıç", value=date.today(), key="izb"); bit = st.date_input("Bitiş", value=date.today(), key="izbi")
        if bit >= bas: gun = gun_sayisi(bas, bit); st.info(f"📅 {gun} gün")
        else: st.error("Tarih hatası"); gun = 0
        notlar = st.text_area("Not", key="izn", height=80)
        if btn("✅ Kaydet", key="biz", caption="İzni kaydeder. Görev çakışırsa uyarı gösterir"):
            if gun <= 0: st.error("Geçersiz aralık")
            else:
                calisan_gorevler = sql_all("SELECT DISTINCT v.tarih, g.ad || ' - ' || m.ad AS pozisyon FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id WHERE v.personel_id=? AND v.tarih BETWEEN ? AND ?",
                                           (pid, bas.isoformat(), bit.isoformat()))
                if calisan_gorevler:
                    st.warning("⚠️ Görev çakışması var!")
                    for gv in calisan_gorevler: st.write(f"- {gv['tarih']} → {gv['pozisyon']}")
                sql_run("INSERT INTO izin VALUES(NULL,?,?,?,?,?,?)", (pid, bas.isoformat(), bit.isoformat(), gun, notlar or None, None))
                st.toast("İzin kaydedildi!"); st.rerun()
    with cc:
        bugun = date.today()
        ay_s = st.selectbox("Ay", [f"{AY_ADLARI[m]} {bugun.year}" for m in range(1,13)], index=bugun.month-1, key="izay")
        ay_i = AY_ADLARI.index(ay_s.split()[0]); yil = int(ay_s.split()[1])
        isaret = set()
        for iz in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=?", (pid,)):
            d = date.fromisoformat(iz["baslangic"]); b = date.fromisoformat(iz["bitis"])
            while d <= b:
                if d.year == yil and d.month == ay_i: isaret.add(d)
                d += timedelta(days=1)
        st.markdown(_takvim_html(yil, ay_i, isaret), unsafe_allow_html=True)

    st.divider(); st.markdown("#### Kayıtlı İzinler")
    izinler = sql_all("SELECT i.id,p.ad,p.soyad,i.baslangic,i.bitis,i.gun_sayisi,i.notlar FROM izin i JOIN personel p ON p.id=i.personel_id ORDER BY i.baslangic DESC LIMIT 100")
    if not izinler: st.info("İzin yok")
    else:
        for iz in izinler:
            c1,c2,c3 = st.columns([4,2,1])
            c1.markdown(f"**{iz['ad']} {iz['soyad']}**  \n📅 {iz['baslangic']} → {iz['bitis']} · {iz['gun_sayisi']} gün")
            c2.markdown("🟠 Aktif" if iz["baslangic"] <= date.today().isoformat() <= iz["bitis"] else "✅ Tamamlandı")
            if c3.button("🗑️", key=f"izsil_{iz['id']}"):
                st.caption("Bu izin kaydını siler")
                sql_run("DELETE FROM izin WHERE id=?", (iz["id"],)); st.toast("Silindi!"); st.rerun()

def _sayfa_carkci():
    st.subheader("⚙️ Çarkçı")
    gem = sql_all("SELECT id,ad FROM gemi ORDER BY ad"); yag = sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not gem or not yag: st.warning("Gemi/personel yok"); return
    c1,c2 = st.columns(2)
    with c1: ad = c1.text_input("Ad", key="cka"); soyad = c2.text_input("Soyad", key="cks")
    gid = c1.selectbox("Gemi", [r["id"] for r in gem], format_func=lambda i:next(r["ad"] for r in gem if r["id"]==i), key="ckg")
    cvt = c1.selectbox("Vardiya", VARDIYA_TIPLERI, key="ckv"); cg = c1.multiselect("Günler", GUNLER_TR, key="ckgun")
    with c2:
        yop = [("(Seçilmedi)",None)] + [(f"{p['ad']} {p['soyad']}",p["id"]) for p in yag]
        ys = c2.selectbox("Sorunlu Yağcı", yop, format_func=lambda x:x[0], key="cky")
        sorun = c2.text_area("Sorun / Açıklama", key="ckso"); vn = c2.text_input("Vardiya Notu", key="ckvn")
        pk = c2.slider("Puan Kırma", 0,5,0, key="ckp")
    if btn("Oluştur", key="bck", caption="Çarkçı kaydını kaydeder ve varsa personel puanını düşürür"):
        if not ad or not soyad: st.error("Ad soyad zorunlu")
        else:
            gun_j = json.dumps([GUNLER_TR.index(g) for g in cg]) if cg else "[]"; pid_p = ys[1]
            sql_run("INSERT INTO carkci VALUES(NULL,?,?,?,?,?,?,?,?,?)",
                    (ad.strip().upper(), soyad.strip().upper(), gid, pid_p, sorun, vn, cvt, gun_j, pk))
            if pid_p:
                mev = sql_one("SELECT is_kalitesi FROM personel WHERE id=?", (pid_p,))
                if mev:
                    yeni = max(1, (mev["is_kalitesi"] or 3) - pk)
                    sql_run("UPDATE personel SET is_kalitesi=?,carkci_ile_sorun=1,carkci_sorun_notu=? WHERE id=?", (yeni, sorun.strip() or None, pid_p))
                    sql_run("INSERT INTO performans_gecmis VALUES(NULL,?,?,?,?)", (pid_p, date.today().isoformat(), yeni, 'carkci'))
            st.toast("Kayıt oluşturuldu!"); st.rerun()
    st.divider()
    cr = sql_all("SELECT c.id,c.ad,c.soyad,g.ad AS gemi,c.carkci_vardiya,c.vardiya_gunleri,p.ad||' '||p.soyad AS yagci,c.sorun_metni,c.puan_kirma FROM carkci c LEFT JOIN gemi g ON g.id=c.gemi_id LEFT JOIN personel p ON p.id=c.problemli_yagci_id ORDER BY c.id DESC LIMIT 30")
    for r in cr: r["vardiya_gunleri"] = _json_gunleri_metne(r.get("vardiya_gunleri"))
    st.dataframe(pd.DataFrame(cr), width='stretch')

def _sayfa_oneri():
    st.subheader("✦ Öneri & Plan")
    gem = sql_all("SELECT id,ad FROM gemi ORDER BY ad"); mak = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gem or not mak: st.warning("Gemi/makine yok"); return
    izinli = bugun_izinli_ids()
    if izinli: st.warning("🟠 Bugün izinli: " + ", ".join(f"{r['ad']} {r['soyad']}" for r in sql_all(f"SELECT ad,soyad FROM personel WHERE id IN ({','.join('?'*len(izinli))})", tuple(izinli))))
    esnek = st.checkbox("Esnek çakışma", value=False, key="esnek")
    st.info("💡 Öneri Motoru: İZİNCİ personel yüksek önceliklidir.")
    st.subheader("🗓️ Toplu Planlama (Adil)")
    with st.expander("Ayarlar"):
        sg = st.multiselect("Gemiler", [g["id"] for g in gem], format_func=lambda i: next(g["ad"] for g in gem if g["id"]==i), key="tpg")
        if sg:
            gemi_mak_ids = set()
            for gid in sg:
                gemi_mak_ids.update(r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gid,)))
            mak_secenek = [m for m in mak if m["id"] in gemi_mak_ids]
            sm = st.multiselect("Makine", [m["id"] for m in mak_secenek], format_func=lambda i: next((m["ad"] for m in mak_secenek if m["id"]==i), ""), key="tpm2")
        else: sm = []
        ba = st.date_input("Başlangıç", date.today(), key="tpb"); bi = st.date_input("Bitiş", date.today()+timedelta(days=7), key="tpi")
        gn = st.multiselect("Günler", GUNLER_TR, default=["Pazartesi","Salı","Çarşamba","Perşembe","Cuma"], key="tpgun")
        gi = [GUNLER_TR.index(g) for g in gn]
        if btn("🚀 Oluştur", key="btp", caption="Seçili aralıktaki tüm boş pozisyonları adilce doldurur"):
            if not sg or not sm: st.error("Seçim yapın")
            else:
                with st.spinner("Toplu planlama yapılıyor..."):
                    kul = {}; top = 0
                    for g in sg:
                        gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (g,))]
                        for m in (gemi_mak if not sm else [mid for mid in sm if mid in gemi_mak]):
                            d = ba
                            while d <= bi:
                                if d.weekday() in gi and not vardiya_plani_kontrol(g, m, d):
                                    on = onerileri_hesapla(g, m, d, limit=10, esnek_cakisma=esnek)
                                    on.sort(key=lambda x: kul.get(x["id"], 0))
                                    if on:
                                        sec = on[0]
                                        if not sec.get("zaten_atanmis"):
                                            bas_saat, bit_saat = VARDIYA_SAATLERI.get(sec["vardiya_tipi"], ("08:00","08:00"))
                                            try:
                                                sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?,?,?)",
                                                        (sec["id"], g, m, d.isoformat(), bas_saat, bit_saat))
                                                kul[sec["id"]] = kul.get(sec["id"], 0) + 1
                                                top += 1
                                            except sqlite3.IntegrityError: pass
                                d += timedelta(days=1)
                st.toast(f"{top} vardiya dağıtıldı!"); st.rerun()

    st.divider()
    with st.expander("🗑️ Vardiya Sil"):
        sil_gemi = st.selectbox("Gemi", [g["id"] for g in gem], format_func=lambda i: next(g["ad"] for g in gem if g["id"]==i), key="silgemi")
        sil_mak = st.selectbox("Makine", [m["id"] for m in mak], format_func=lambda i: next(m["ad"] for m in mak if m["id"]==i), key="silmak")
        sil_tarih = st.date_input("Tarih", date.today(), key="siltarih")
        mevcut_sil = sql_one("SELECT p.ad||' '||p.soyad AS isim FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.gemi_id=? AND v.makine_tipi_id=? AND v.tarih=?", (sil_gemi, sil_mak, sil_tarih.isoformat()))
        if mevcut_sil:
            st.warning(f"Mevcut: **{mevcut_sil['isim']}**")
            if btn("Atamayı Sil", key="sil_ata", caption="Belirtilen atamayı kaldırır"):
                sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (sil_gemi, sil_mak, sil_tarih.isoformat()))
                st.toast("Atama silindi!"); st.rerun()
        else: st.info("Bu tarihte atama yok")

    st.divider(); st.subheader("Tek Seferlik Öneri")
    gid = st.selectbox("Gemi", [g["id"] for g in gem], format_func=lambda i: next((g["ad"] for g in gem if g["id"]==i), ""), key="ong")
    gemi_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gid,))]
    mak_secenek = [m for m in mak if m["id"] in gemi_mak]
    if not mak_secenek: st.warning("Bu gemide makine tanımlı değil!"); return
    mid = st.selectbox("Makine", [m["id"] for m in mak_secenek], format_func=lambda i: next((m["ad"] for m in mak_secenek if m["id"]==i), ""), key="onm")
    ht = st.date_input("Tarih", date.today(), key="onht")
    tum = sql_all("SELECT id,ad,soyad,gemi_id,gemi_id_list FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))")
    gemi_p = [p for p in tum if not p["gemi_id"] or p["gemi_id"]==gid or gid in _id_listesi(p.get("gemi_id_list"))]
    cik_opts = [("(Yok)",None)] + [(f"{p['ad']} {p['soyad']}{' 🟠' if p['id'] in izinli else ''}",p["id"]) for p in sorted(gemi_p, key=lambda x:(0 if x['id'] in izinli else 1,x['ad']))]
    def_idx = next((i for i,(_,pid_val) in enumerate(cik_opts) if pid_val in izinli), 0)
    cik_sec = st.selectbox("Çıkan", cik_opts, format_func=lambda x:x[0], index=def_idx, key="oncik"); cik_id = cik_sec[1]
    if btn("🔍 Öner", key="bon", caption="Seçili pozisyon için en uygun 5 adayı listeler"):
        out = onerileri_hesapla(gid, mid, ht, cik_id, 5, esnek); rows = to_dict_rows(out)
        if not rows: st.warning("Uygun yok")
        elif any(r.get("zaten_atanmis") for r in rows): st.success("Zaten atanmış")
        else: st.success(f"{len(rows)} aday:"); st.dataframe(pd.DataFrame(rows), width='stretch')

    st.divider(); st.markdown("#### Tekil Ata (saatli)")
    ps = st.selectbox("Personel", [f"{p['ad']} {p['soyad']}" for p in sql_all("SELECT id,ad,soyad,vardiya_tipi FROM personel WHERE aktif=1")], key="vdp")
    vt_ps = sql_one("SELECT vardiya_tipi FROM personel WHERE ad||' '||soyad=?", (ps,))
    varsayilan_bas, varsayilan_bit = VARDIYA_SAATLERI.get(vt_ps["vardiya_tipi"] if vt_ps else "SABIT", ("08:00","08:00"))
    col_saat1, col_saat2 = st.columns(2)
    with col_saat1: bas_saat = st.text_input("Başlangıç Saati", value=varsayilan_bas, key="bas_saat")
    with col_saat2: bit_saat = st.text_input("Bitiş Saati", value=varsayilan_bit, key="bit_saat")
    if btn("✅ Kaydet", key="bvk", caption="Seçili personeli elle atar"):
        p_sec = sql_one("SELECT id,vardiya_tipi FROM personel WHERE ad||' '||soyad=?", (ps,))
        if p_sec:
            if vardiya_plani_kontrol(gid, mid, ht): st.error("Zaten atanmış")
            elif saat_cakismasi_var(p_sec["id"], ht, bas_saat, bit_saat): st.error("Saat çakışması var!")
            else:
                if iki_gun_ust_uste_mi(p_sec["id"], ht):
                    st.warning("⚠️ Bu personel dün de çalıştı.")
                try:
                    sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?,?,?)",
                            (p_sec["id"], gid, mid, ht.isoformat(), bas_saat, bit_saat))
                    st.toast("Vardiya atandı!"); st.rerun()
                except sqlite3.IntegrityError: st.error("Bu atama zaten mevcut!")

def _sayfa_bilgi():
    st.subheader("📊 Bilgi & Rapor")
    col1, col2, col3 = st.columns(3)
    col1.metric("👥 Toplam Personel", sql_one("SELECT COUNT(*) AS c FROM personel WHERE aktif=1")["c"])
    col2.metric("🚢 Toplam Gemi", sql_one("SELECT COUNT(*) AS c FROM gemi")["c"])
    col3.metric("🏝️ Bugün İzinde", len(bugun_izinli_ids()))

    c1, c2, c3 = st.columns(3)
    with c1:
        if btn("💾 Yedekle", key="byedek", caption="Veritabanının yedeğini alır"):
            st.toast(f"Yedek: {veritabani_yedekle().name}", icon="💾")
    with c2:
        if btn("🧪 Test Verisi", key="btest", caption="Örnek gemi, makine, personel ve izin kayıtları oluşturur"):
            test_verisi_olustur()
    with c3:
        st.download_button("📥 DB İndir", open(DB_PATH,"rb"), file_name=f"ordino_{date.today().isoformat()}.db", key="indir_db")
        st.caption("Veritabanını bilgisayara indirir")

    st.divider(); st.subheader("📄 PDF")
    cp1, cp2 = st.columns(2)
    with cp1:
        if btn("Aylık Özet PDF", key="bpdfa", caption="Aylık personel özeti PDF'i oluşturur"):
            p = pdf_rapor_olustur("aylik_ozet"); st.download_button("İndir", open(p,"rb"), file_name=p.name, key="indir_aylik")
    with cp2:
        p_bas = cp2.date_input("Başlangıç", date.today(), key="pdf_bas")
        p_bit = cp2.date_input("Bitiş", date.today()+timedelta(days=7), key="pdf_bit")
        if btn("PDF Oluştur", key="pdf_aralik", caption="Seçili aralıktaki vardiya planını PDF yapar"):
            p = pdf_rapor_olustur("vardiya_plani", baslangic=p_bas, bitis=p_bit); st.download_button("İndir", open(p,"rb"), file_name=p.name, key="indir_vardiya")

    if PLOTLY_AVAILABLE:
        df_grafik = pd.DataFrame(sql_all("SELECT g.ad AS gemi, COUNT(v.id) AS atama FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id GROUP BY gemi"))
        if not df_grafik.empty:
            fig = px.bar(df_grafik, x='gemi', y='atama', title='Gemi Bazlı Atama Sayıları')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("📊 Grafikler için `pip install plotly` yapın.")

    st.divider(); st.subheader("📅 Takvime Aktar (.ics)")
    if btn("⬇ .ics İndir", key="ics_indir", caption="Vardiya planını takvim dosyası olarak indirir"):
        ics_metin = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Ordino//Planlama//TR\n"
        rows = sql_all("SELECT v.tarih, v.baslangic_saat, v.bitis_saat, g.ad AS gemi, m.ad AS makine FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id")
        for r in rows:
            dt_bas = f"{r['tarih'].replace('-','')}T{r['baslangic_saat'].replace(':','')}00"
            dt_bit = f"{r['tarih'].replace('-','')}T{r['bitis_saat'].replace(':','')}00"
            ics_metin += f"BEGIN:VEVENT\nDTSTART:{dt_bas}\nDTEND:{dt_bit}\nSUMMARY:{r['gemi']} - {r['makine']}\nEND:VEVENT\n"
        ics_metin += "END:VCALENDAR"
        st.download_button("İndir .ics", ics_metin, file_name="ordino_plan.ics", key="indir_ics")

    st.divider(); st.subheader("📋 Bugünün Planı")
    bugun_plani = bugun_plani_olustur()
    if bugun_plani:
        st.dataframe(pd.DataFrame(bugun_plani), width='stretch')
        metin = "\n".join(f"{p['Gemi']} - {p['Makine']}: {p['Personel']}" for p in bugun_plani)
        st.code(metin, language="text")
    else:
        st.info("Bugün için planlanmış görev yok.")

# ---------- MAIN ----------
def main():
    st.set_page_config(page_title="Ordino", page_icon="⚓", layout="wide")
    if "ayarlar" not in st.session_state: st.session_state.ayarlar = DEFAULT_AYARLAR
    if "tema_koyu" not in st.session_state: st.session_state.tema_koyu = True
    init_db()
    st.markdown("""<style>
    @media (max-width: 768px) {
        .row-widget.stButton > button { width: 100% !important; }
        .stHorizontalBlock { flex-direction: column !important; }
    }
    .stButton>button { width: 100%; border-radius: 8px; }
    </style>""", unsafe_allow_html=True)

    with st.sidebar:
        st.title("⚓ Ordino")
        if btn("🌓 Tema Değiştir", key="tema_sidebar", caption="Açık/koyu tema arasında geçiş yapar"):
            st.session_state.tema_koyu = not st.session_state.tema_koyu
            st.rerun()
        st.markdown("---")
        for u in sertifika_uyarilari_al():
            st.warning(f"{u['ad']} {u['soyad']} - {u['sertifika_adi']} ({u['makine']}) → {u['gecerlilik_tarihi']}")
        for p in bugun_plani_olustur():
            st.write(f"{'✅' if 'BOŞ' not in p['Personel'] else '🟡'} {p['Gemi']} – {p['Makine']}: **{p['Personel']}**")
        st.caption("v7.6")

    tabs = st.tabs(["🧩 Yapboz","⚡ Acil","🚢 Gemiler","👷 Personel & İzin","✦ Öneri","📊 Bilgi","⚙️ Ayarlar"])
    with tabs[0]: _sayfa_yapboz()
    with tabs[1]: _sayfa_acil()
    with tabs[2]: _sayfa_excel()
    with tabs[3]: _sayfa_personel(); st.divider(); _sayfa_izin()
    with tabs[4]: _sayfa_oneri(); st.divider(); _sayfa_carkci()
    with tabs[5]: _sayfa_bilgi()
    with tabs[6]: ayarlar_sayfasi()

if __name__ == "__main__":
    main()
