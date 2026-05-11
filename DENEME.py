"""
Ordino Yağcı Planlaması — Personel Kartı Gemi Adı + Yapboz Düzeltmeleri
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json, sqlite3, calendar as _cal, io, os, shutil, random
from datetime import date, timedelta, datetime, time
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF

# ---------- VERİTABANI ----------
DB_PATH = Path(__file__).parent / "ordino.db"
YEDEK_DIR = Path(__file__).parent / "yedekler"

VARDIYA_SAATLERI = {
    "SABIT": ("08:00", "08:00"),
    "GRUPCU": ("08:00", "08:00"),
    "IZINCI": ("08:00", "08:00"),
    "TERSANE": ("08:00", "17:00"),
    "8_5": ("08:00", "17:00"),
    "GECE": ("20:00", "08:00"),
}

def saat_cakisiyor(bas1: str, bit1: str, bas2: str, bit2: str) -> bool:
    def to_minutes(saat: str) -> int:
        h, m = map(int, saat.split(":"))
        return h * 60 + m
    b1 = to_minutes(bas1)
    e1 = to_minutes(bit1)
    b2 = to_minutes(bas2)
    e2 = to_minutes(bit2)
    if e1 <= b1: e1 += 24 * 60
    if e2 <= b2: e2 += 24 * 60
    return b1 < e2 and b2 < e1

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def sql_one(query, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
        if row: return dict(zip([d[0] for d in cur.description], row))
        return None

def sql_all(query, params=()):
    with get_connection() as conn:
        cur = conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

def sql_run(query, params=()):
    with get_connection() as conn:
        conn.execute(query, params)
        conn.commit()

def veritabani_yedekle():
    YEDEK_DIR.mkdir(exist_ok=True)
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek_yolu = YEDEK_DIR / f"ordino_yedek_{zaman}.db"
    shutil.copy2(DB_PATH, yedek_yolu)
    yedekler = sorted(YEDEK_DIR.glob("ordino_yedek_*.db"))
    if len(yedekler) > 10:
        for eski in yedekler[:-10]: eski.unlink()
    return yedek_yolu

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS gemi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL, kod TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS makine_tipi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL)")
    c.execute("""CREATE TABLE IF NOT EXISTS personel (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL, soyad TEXT NOT NULL,
        gemi_id INTEGER, gemi_id_list TEXT, makine_tipi_id INTEGER, makine_tipi_id_list TEXT,
        vardiya_tipi TEXT, vardiya_gunleri TEXT, gemiden_cekilme INTEGER DEFAULT 0,
        carkci_ile_sorun INTEGER DEFAULT 0, carkci_sorun_notu TEXT,
        gemi_tutumu TEXT, izin_tercih_gunleri TEXT, izin_saat_araligi TEXT,
        is_kalitesi INTEGER, performans_notu TEXT, aktif INTEGER DEFAULT 1,
        durum TEXT DEFAULT 'Gemide'
    )""")
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
        UNIQUE(personel_id, gemi_id, makine_tipi_id, tarih)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS personel_sertifika (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        makine_tipi_id INTEGER NOT NULL, sertifika_adi TEXT, gecerlilik_tarihi TEXT, notlar TEXT,
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE,
        FOREIGN KEY(makine_tipi_id) REFERENCES makine_tipi(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS performans_gecmis (
        id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER NOT NULL,
        tarih TEXT NOT NULL, puan INTEGER NOT NULL, kaynak TEXT DEFAULT 'manuel',
        FOREIGN KEY(personel_id) REFERENCES personel(id) ON DELETE CASCADE)""")
    for tab, col, typ in [("gemi","konum","TEXT"),
                          ("personel","gemi_id_list","TEXT"),("personel","makine_tipi_id_list","TEXT"),
                          ("personel","gemiden_cekilme","INTEGER DEFAULT 0"),("personel","carkci_ile_sorun","INTEGER DEFAULT 0"),
                          ("personel","carkci_sorun_notu","TEXT"),("personel","gemi_tutumu","TEXT"),
                          ("personel","izin_tercih_gunleri","TEXT"),("personel","izin_saat_araligi","TEXT"),
                          ("personel","is_kalitesi","INTEGER"),("personel","performans_notu","TEXT"),
                          ("personel","aktif","INTEGER DEFAULT 1"),("personel","durum","TEXT DEFAULT 'Gemide'"),
                          ("izin","gunler_json","TEXT"),("carkci","vardiya_gunleri","TEXT"),
                          ("carkci","puan_kirma","INTEGER DEFAULT 0"),
                          ("vardiya_plan","baslangic_saat","TEXT DEFAULT '08:00'"),
                          ("vardiya_plan","bitis_saat","TEXT DEFAULT '08:00'")]:
        c.execute(f"PRAGMA table_info({tab})")
        if col not in [r[1] for r in c.fetchall()]:
            try: c.execute(f"ALTER TABLE {tab} ADD COLUMN {col} {typ}")
            except: pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vardiya_unique ON vardiya_plan(personel_id, gemi_id, makine_tipi_id, tarih)")
    except: pass
    conn.commit()
    conn.close()

# ---------- YARDIMCI ----------
GUNLER_TR = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
AY_ADLARI = ["","Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
VARDIYA_TIPLERI = ["SABIT","GRUPCU","IZINCI","TERSANE","8_5","GECE"]
GEMI_KONUMLARI = ["Tersane", "Dışarıda", "Gecede", "Belirtilmedi"]
PERSONEL_DURUM = ["Gemide", "İskelede", "Raporlu"]
VARDIYA_RENKLERI = {"SABIT":"#3498db","GRUPCU":"#2ecc71","IZINCI":"#f39c12","TERSANE":"#e74c3c","8_5":"#9b59b6","GECE":"#1abc9c"}
VARDIYA_KONUM_ESLESME = {"TERSANE":"Tersane", "8_5":"Dışarıda"}

OLUMLU_KELIMELER = [
    "iyi", "çalışkan", "başarılı", "güvenilir", "hızlı", "dikkatli", "özenli",
    "disiplinli", "yardımsever", "titiz", "profesyonel", "mükemmel", "harika",
    "süper", "efsane", "gayretli", "istekli", "düzenli", "sorumlu", "kooperatif"
]
OLUMSUZ_KELIMELER = [
    "kötü", "berbat", "yetersiz", "tembel", "sorunlu", "problemli", "geç kalıyor",
    "işe yaramaz", "ilgisiz", "dikkatsiz", "başarısız", "yavaş", "isteksiz",
    "uyumsuz", "şikayet", "kavga", "saygısız", "sorumsuz", "eksik", "hatalı",
    "verimsiz", "güvenilmez", "disiplinsiz", "özensiz"
]
AGIR_OLUMSUZ_KELIMELER = [
    "berbat", "işe yaramaz", "güvenilmez", "disiplinsiz", "kovulmalı", "kesinlikle çalışmaz"
]

def nlp_skor(metin: str) -> float:
    if not metin: return 0.0
    metin = metin.lower()
    olumlu = sum(1 for k in OLUMLU_KELIMELER if k in metin)
    olumsuz = sum(1 for k in OLUMSUZ_KELIMELER if k in metin)
    agir = sum(1 for k in AGIR_OLUMSUZ_KELIMELER if k in metin)
    toplam_olumsuz = olumsuz + (agir * 2)
    if olumlu + toplam_olumsuz == 0: return 0.0
    return (olumlu - toplam_olumsuz) / max(olumlu + toplam_olumsuz, 5)

def _json_gunleri_metne(v):
    if not v: return "-"
    try:
        idx = json.loads(v)
        if not isinstance(idx, list): return "-"
        return ", ".join(GUNLER_TR[int(i)] for i in idx if 0 <= int(i) < 7) or "-"
    except: return "-"

def _makine_id_json(lst): return json.dumps(lst)
def _gemi_id_json(lst): return json.dumps(lst)

def _id_listesi(v):
    if not v: return []
    try:
        p = json.loads(v)
        return [int(x) for x in p] if isinstance(p, list) else [int(p)]
    except: return []

def _personel_label_map(rows):
    return {f"{r['ad']} {r['soyad']} (ID:{r['id']})": int(r["id"]) for r in rows}

def gun_sayisi(bas, bit): return (bit - bas).days + 1

def bugun_izinli_ids():
    bugun = date.today().isoformat()
    return {r["personel_id"] for r in sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (bugun,))}

def izinde_mi(pid, kontrol):
    t = kontrol.isoformat()
    return bool(sql_one("SELECT id FROM izin WHERE personel_id=? AND ?>=baslangic AND ?<=bitis", (pid, t, t)))

def sertifika_gecerli_mi(pid, makine_tipi_id, kontrol_tarih):
    return bool(sql_one("SELECT id FROM personel_sertifika WHERE personel_id=? AND makine_tipi_id=? AND (gecerlilik_tarihi IS NULL OR gecerlilik_tarihi >= ?)", (pid, makine_tipi_id, kontrol_tarih.isoformat())))

def baska_gemide_mi(pid, tarih, mevcut_gemi_id, esnek=False):
    if esnek: return False
    row = sql_one("SELECT v.gemi_id FROM vardiya_plan v WHERE v.personel_id=? AND v.tarih=? AND v.gemi_id != ?", (pid, tarih.isoformat(), mevcut_gemi_id))
    return row is not None

def ayni_gun_baska_makine(pid, tarih, makine_tipi_id):
    return bool(sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND tarih=? AND makine_tipi_id != ?", (pid, tarih.isoformat(), makine_tipi_id)))

def saat_cakismasi_var(pid, tarih, bas_saat, bit_saat):
    rows = sql_all("SELECT baslangic_saat, bitis_saat FROM vardiya_plan WHERE personel_id=? AND tarih=?", (pid, tarih.isoformat()))
    for r in rows:
        if saat_cakisiyor(bas_saat, bit_saat, r["baslangic_saat"], r["bitis_saat"]):
            return True
    return False

def fazla_mesai_kontrol(pid, tarih):
    bas = (tarih - timedelta(days=7)).isoformat()
    bit = tarih.isoformat()
    row = sql_one("SELECT COUNT(DISTINCT tarih) AS c FROM vardiya_plan WHERE personel_id=? AND tarih >= ? AND tarih <= ?", (pid, bas, bit))
    gun = row["c"] if row else 0
    return gun >= 6, gun

def ayni_gemi_peş_pese(pid, tarih, gemi_id):
    dun = (tarih - timedelta(days=1)).isoformat()
    row = sql_one("SELECT id FROM vardiya_plan WHERE personel_id=? AND gemi_id=? AND tarih=?", (pid, gemi_id, dun))
    return row is not None

def gece_sonrasi_dinlenme(pid, tarih):
    dun = (tarih - timedelta(days=1)).isoformat()
    dun_gece = sql_one("SELECT v.gemi_id FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.personel_id=? AND v.tarih=? AND p.vardiya_tipi='GECE'", (pid, dun))
    return dun_gece is not None

def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    row = sql_one("SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi_id, makine_tipi_id, tarih.isoformat()))
    return row["personel_id"] if row else None

def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
    mevcut = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut:
        p = sql_one("SELECT id,ad,soyad,vardiya_tipi,is_kalitesi FROM personel WHERE id=?", (mevcut,))
        if p: return [{**p, "puan":999, "uyari_8_5":p.get("vardiya_tipi")=="8_5", "zaten_atanmis":True}]
    tum = sql_all("SELECT * FROM personel WHERE aktif=1 AND durum IN ('Gemide','İskelede')")
    gemi_konum = sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,))["konum"]
    sonuclar = []
    for p in tum:
        if cikan_id and p["id"] == cikan_id: continue
        if izinde_mi(p["id"], hedef_tarih): continue
        if baska_gemide_mi(p["id"], hedef_tarih, gemi_id, esnek=esnek_cakisma): continue
        if ayni_gun_baska_makine(p["id"], hedef_tarih, makine_tipi_id): continue
        vardiya = p.get("vardiya_tipi","")
        if vardiya == "GECE" and gemi_konum != "Gecede": continue
        if vardiya in VARDIYA_KONUM_ESLESME and gemi_konum != VARDIYA_KONUM_ESLESME[vardiya]: continue
        mids = _id_listesi(p.get("makine_tipi_id_list")) or ([p["makine_tipi_id"]] if p.get("makine_tipi_id") else [])
        if makine_tipi_id not in mids: continue
        if not sertifika_gecerli_mi(p["id"], makine_tipi_id, hedef_tarih): continue
        gids = _id_listesi(p.get("gemi_id_list")) or ([p.get("gemi_id")] if p.get("gemi_id") else [])
        if gemi_id not in gids: continue
        if p.get("carkci_ile_sorun"): continue
        bas_saat, bit_saat = VARDIYA_SAATLERI.get(vardiya, ("08:00","08:00"))
        if saat_cakismasi_var(p["id"], hedef_tarih, bas_saat, bit_saat): continue
        performans_notu_metni = p.get("performans_notu") or ""
        carkci_notu_metni = p.get("carkci_sorun_notu") or ""
        nlp_puan = nlp_skor(performans_notu_metni) + nlp_skor(carkci_notu_metni)
        nlp_etki = nlp_puan * 25
        kalite = p.get("is_kalitesi") or 3
        if kalite <= 2: kalite_puan = -30
        elif kalite == 3: kalite_puan = 0
        elif kalite == 4: kalite_puan = 10
        else: kalite_puan = 20
        dinlenme_cezasi = -30 if gece_sonrasi_dinlenme(p["id"], hedef_tarih) else 0
        pespese_cezasi = -15 if ayni_gemi_peş_pese(p["id"], hedef_tarih, gemi_id) else 0
        fazla, gun = fazla_mesai_kontrol(p["id"], hedef_tarih)
        vardiya_puan = {"IZINCI":100, "TERSANE":95, "GECE":105, "GRUPCU":80, "SABIT":60, "8_5":40}.get(vardiya, 50)
        mesai_ceza = -20 if fazla else 0
        toplam_puan = vardiya_puan + kalite_puan + mesai_ceza + dinlenme_cezasi + pespese_cezasi + nlp_etki
        sonuclar.append({**p, "puan":toplam_puan, "uyari_8_5":vardiya=="8_5", "zaten_atanmis":False, "fazla_mesai":fazla, "son_7_gun":gun, "dinlenme_ihlali":dinlenme_cezasi<0, "pespese":pespese_cezasi<0, "nlp_puan":nlp_puan, "bas_saat":bas_saat, "bit_saat":bit_saat})
    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list")) or ([o["makine_tipi_id"]] if o.get("makine_tipi_id") else [])
        ad = f"{o['ad']} {o['soyad']}"
        if o.get("fazla_mesai"): ad += " ⚠️ FAZLA MESAİ"
        if o.get("dinlenme_ihlali"): ad += " 🌙 DİNLENME"
        if o.get("pespese"): ad += " 🔁 PEŞ PEŞE"
        if o.get("nlp_puan", 0) < -0.3: ad += " 📝 OLUMSUZ YORUM"
        elif o.get("nlp_puan", 0) > 0.3: ad += " 👍 OLUMLU YORUM"
        rows.append({"id":o["id"], "ad_soyad":ad, "vardiya":o.get("vardiya_tipi","-"), "makine":", ".join(tum_mak.get(m,str(m)) for m in mids), "puan":o["puan"], "uyari_8_5":o.get("uyari_8_5",False), "zaten_atanmis":o.get("zaten_atanmis",False)})
    return rows

# ---------- TEMA ----------
def _tema_css(koyu=True):
    base = """
    <style>
    .stApp{background:#1a1a2e}
    .main .block-container{background:#2b2b3d;border-radius:20px;padding:1.5rem 1rem;box-shadow:0 4px 20px rgba(0,0,0,0.4);margin-top:10px;color:#f0f0f0;max-width:900px}
    h1,h2,h3,h4,h5,h6,p,span,div,label{color:#f0f0f0!important}
    .stButton>button{background:#f3831f;color:white;border:none;border-radius:10px;padding:.5rem 1rem;font-weight:600;width:100%;min-height:44px;transition:all 0.3s ease;box-shadow:0 2px 5px rgba(243,131,31,0.3);}
    .stButton>button:hover{background:#d35400;box-shadow:0 4px 10px rgba(243,131,31,0.5);transform:translateY(-1px);}
    button[kind="secondary"]{background:#555!important;color:#ddd!important;border:1px solid #777!important;}
    button[kind="secondary"]:hover{background:#666!important;}
    </style>
    """
    if not koyu:
        base = """<style>.stApp{background:#f5f7fa}.main .block-container{background:#fff;border-radius:20px;padding:1.5rem 1rem;box-shadow:0 4px 20px rgba(0,0,0,0.05);margin-top:10px;color:#1a1a1a;max-width:900px}h1,h2,h3,h4,h5,h6,p,span,div,label{color:#1a1a1a!important}.stButton>button{background:#f3831f;color:white;border:none;border-radius:10px;padding:.5rem 1rem;font-weight:600;width:100%;min-height:44px;}.stButton>button:hover{background:#d35400;}button[kind="secondary"]{background:#eee!important;color:#333!important;}</style>"""
    return base

# ---------- TAKVİM ----------
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

def pdf_rapor_olustur(tip="aylik_ozet", ay=None, yil=None):
    pdf = PDFRapor()
    pdf.alias_nb_pages()
    pdf.add_page()
    def tr_to_en(t):
        return t.translate(str.maketrans('ığüşöçİĞÜŞÖÇ','igusocIGUSOC'))
    if tip == "aylik_ozet":
        if not ay: ay = date.today().month
        if not yil: yil = date.today().year
        bas = date(yil, ay, 1)
        son = date(yil, ay, _cal.monthrange(yil, ay)[1])
        pdf.set_font('Arial','B',14)
        pdf.cell(0,10,tr_to_en(f'Aylik Personel Ozeti - {AY_ADLARI[ay]} {yil}'),0,1,'C')
        pdf.ln(5)
        pdf.set_font('Arial','B',10)
        pdf.cell(50,7,'Personel',1); pdf.cell(30,7,'Calisma',1); pdf.cell(30,7,'Izin',1); pdf.cell(30,7,'Toplam',1); pdf.ln()
        pdf.set_font('Arial','',10)
        for p in sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad"):
            izin_gun = sum(max(0, (min(date.fromisoformat(i["bitis"]),son)-max(date.fromisoformat(i["baslangic"]),bas)).days+1) for i in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=? AND baslangic<=? AND bitis>=?", (p["id"],son.isoformat(),bas.isoformat())))
            calisma = sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih>=? AND tarih<=?", (p["id"],bas.isoformat(),son.isoformat()))["c"]
            pdf.cell(50,7,tr_to_en(f"{p['ad']} {p['soyad']}"),1)
            pdf.cell(30,7,str(calisma),1); pdf.cell(30,7,str(izin_gun),1); pdf.cell(30,7,str(calisma+izin_gun),1); pdf.ln()
    else:
        pdf.set_font('Arial','B',14); pdf.cell(0,10,'Vardiya Plani',0,1,'C'); pdf.ln(5)
        pdf.set_font('Arial','B',9)
        pdf.cell(30,7,'Tarih',1); pdf.cell(40,7,'Gemi',1); pdf.cell(35,7,'Makine',1); pdf.cell(40,7,'Personel',1); pdf.ln()
        pdf.set_font('Arial','',9)
        for p in sql_all("SELECT v.tarih,g.ad AS gemi,m.ad AS makine,p.ad||' '||p.soyad AS personel FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id JOIN personel p ON v.personel_id=p.id ORDER BY v.tarih DESC LIMIT 50"):
            pdf.cell(30,7,p['tarih'],1); pdf.cell(40,7,tr_to_en(p['gemi']),1); pdf.cell(35,7,tr_to_en(p['makine']),1); pdf.cell(40,7,tr_to_en(p['personel']),1); pdf.ln()
    path = Path(__file__).parent / f"rapor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(str(path))
    return path

def test_verisi_olustur():
    for g in [("M/T ATLANTIC","Gecede"),("M/V BOGAZICI","Dışarıda"),("T/S CINAR","Tersane"),("M/V DENIZ YILDIZI","Gecede")]:
        try: sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(g[0],f"G{random.randint(100,999)}",g[1]))
        except: pass
    for m in ["Dizel Motor","Kompresor","Pompa","Jenerator","Kazan"]:
        try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(m,))
        except: pass
    gemiler = sql_all("SELECT id FROM gemi")
    makineler = sql_all("SELECT id FROM makine_tipi")
    for ad, soyad in [("Ahmet","Yilmaz"),("Mehmet","Demir"),("Ali","Kaya"),("Veli","Sahin"),("Ayse","Celik"),("Fatma","Aydin"),("Hasan","Ozturk"),("Huseyin","Arslan")]:
        gid = random.choice(gemiler)["id"]
        mid = random.choice(makineler)["id"]
        vt = random.choice(VARDIYA_TIPLERI)
        sql_run("INSERT INTO personel(ad,soyad,gemi_id,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum,performans_notu) VALUES(?,?,?,?,?,?,?,?,?,?)",(ad,soyad,gid,mid,_makine_id_json([mid]),vt,json.dumps(random.sample(range(7),random.randint(2,5))),random.randint(2,5),random.choice(PERSONEL_DURUM),random.choice(["iyi çalışkan","sorunlu geç kalıyor","","berbat işe yaramaz","başarılı ve dikkatli"])))
    st.success("Test verileri oluşturuldu!")
    st.rerun()

# ---------- SAYFALAR ----------
def _sayfa_yapboz():
    st.subheader("🧩 İnteraktif Yapboz")
    c1,c2 = st.columns([3,1])
    with c1: sec_tarih = st.date_input("Tarih", value=date.today(), key="yapboz_tarih", format="DD.MM.YYYY")
    with c2:
        if st.button("📅 Bugün", key="yapboz_bugun"): st.session_state.yapboz_tarih = date.today(); st.rerun()
    gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler: st.warning("Gemi ve makine ekleyin."); return
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 Tüm Atamaları Temizle", key="temizle_yapboz", type="secondary"):
            sql_run("DELETE FROM vardiya_plan WHERE tarih=?", (sec_tarih.isoformat(),))
            st.toast("Tüm atamalar temizlendi!", icon="🧹")
            st.rerun()
    with col2:
        if st.button("🤖 Hepsini Otomatik Doldur", key="otomatik_doldur_btn"):
            with st.spinner("Otomatik dolduruluyor..."):
                for gemi in gemiler:
                    for mak in makineler:
                        if not vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih):
                            oneri = onerileri_hesapla(gemi["id"], mak["id"], sec_tarih, limit=1)
                            if oneri and not oneri[0].get("zaten_atanmis"):
                                bas_saat, bit_saat = VARDIYA_SAATLERI.get(oneri[0]["vardiya_tipi"], ("08:00","08:00"))
                                try:
                                    sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                            (oneri[0]["id"], gemi["id"], mak["id"], sec_tarih.isoformat(), bas_saat, bit_saat))
                                except sqlite3.IntegrityError: pass
            st.toast("Tüm boş pozisyonlar dolduruldu!", icon="🤖")
            st.rerun()
    izinli = {r["personel_id"] for r in sql_all("SELECT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (sec_tarih.isoformat(),))}
    for gemi in gemiler:
        st.markdown(f"### 🚢 {gemi['ad']}")
        cols = st.columns(len(makineler))
        for i, mak in enumerate(makineler):
            with cols[i]:
                mevcut = vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih)
                if mevcut:
                    p = sql_one("SELECT ad,soyad,vardiya_tipi,durum,is_kalitesi FROM personel WHERE id=?",(mevcut,))
                    if p:
                        renk = VARDIYA_RENKLERI.get(p['vardiya_tipi'], '#3a3a4e')
                        opacity = {1:0.5,2:0.6,3:0.75,4:0.9,5:1.0}.get(p['is_kalitesi'] or 3, 0.8)
                        st.markdown(f"<div style='background:{renk};padding:8px;border-radius:8px;color:white;text-align:center;font-weight:bold;opacity:{opacity}'>{p['ad']} {p['soyad']}<br>({p['vardiya_tipi']}) {p.get('durum','')}<br>⭐{p['is_kalitesi']}</div>", unsafe_allow_html=True)
                    if st.button("❌", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}"):
                        sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",(gemi["id"],mak["id"],sec_tarih.isoformat()))
                        st.toast("Personel vardiyadan çıkarıldı", icon="❌")
                        st.rerun()
                else:
                    st.warning("Boş")
                    uygun = ["Seçiniz..."]
                    for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND durum IN ('Gemide','İskelede')"):
                        if p["id"] in izinli: continue
                        if baska_gemide_mi(p["id"], sec_tarih, gemi["id"]): continue
                        if ayni_gun_baska_makine(p["id"], sec_tarih, mak["id"]): continue
                        mids = _id_listesi(p.get("makine_tipi_id_list")) or [p["makine_tipi_id"]]
                        if mak["id"] not in mids: continue
                        if not sertifika_gecerli_mi(p["id"], mak["id"], sec_tarih): continue
                        gids = _id_listesi(p.get("gemi_id_list")) or [p["gemi_id"]]
                        if gemi["id"] not in gids: continue
                        if p.get("carkci_ile_sorun"): continue
                        gemi_konum = sql_one("SELECT konum FROM gemi WHERE id=?",(gemi["id"],))["konum"]
                        if p["vardiya_tipi"] == "GECE" and gemi_konum != "Gecede": continue
                        if p["vardiya_tipi"] in VARDIYA_KONUM_ESLESME and gemi_konum != VARDIYA_KONUM_ESLESME[p["vardiya_tipi"]]: continue
                        bas_saat, bit_saat = VARDIYA_SAATLERI.get(p["vardiya_tipi"], ("08:00","08:00"))
                        if saat_cakismasi_var(p["id"], sec_tarih, bas_saat, bit_saat): continue
                        uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum','')})")
                    if len(uygun)==1:
                        st.caption("Uygun personel yok (izin/çakışma/sertifika/konum/saat)")
                    else:
                        sec = st.selectbox("Seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                        if sec != "Seçiniz...":
                            pid_row = sql_one("SELECT id,vardiya_tipi FROM personel WHERE ad||' '||soyad=?",(sec.split(" (")[0],))
                            if pid_row:
                                bas_saat, bit_saat = VARDIYA_SAATLERI.get(pid_row["vardiya_tipi"], ("08:00","08:00"))
                                # Son kontrol: saat çakışması
                                if saat_cakismasi_var(pid_row["id"], sec_tarih, bas_saat, bit_saat):
                                    st.error("Saat çakışması nedeniyle atanamaz!")
                                else:
                                    try:
                                        sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                (pid_row["id"],gemi["id"],mak["id"],sec_tarih.isoformat(),bas_saat,bit_saat))
                                        sql_run("INSERT INTO performans_gecmis(personel_id,tarih,puan,kaynak) VALUES(?,?,?,?)",(pid_row["id"],sec_tarih.isoformat(),sql_one("SELECT is_kalitesi FROM personel WHERE id=?",(pid_row["id"],))["is_kalitesi"] or 3,'otomatik'))
                                        st.toast("Personel atandı!", icon="✅")
                                        st.rerun()
                                    except sqlite3.IntegrityError:
                                        st.error("Bu atama zaten mevcut!")
                            else:
                                st.error("Personel bulunamadı!")
        st.divider()

def _sayfa_personel():
    # ... (önceki personel kodu, sadece personel kartı değişikliği)
    st.subheader("👷 Personel")
    gemiler=sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler=sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    arama = st.text_input("🔍 Personel Ara", key="personel_arama")
    st.caption("Filtre:")
    cols = st.columns(len(VARDIYA_TIPLERI) + 3)
    with cols[0]:
        if st.button("Tümü", key="filtre_tumu"):
            st.session_state.fv = None; st.session_state.fa = None
    for i, vt in enumerate(VARDIYA_TIPLERI):
        with cols[i + 1]:
            if st.button(vt, key=f"filtre_{vt}"):
                st.session_state.fv = vt; st.session_state.fa = None
    with cols[-2]:
        if st.button("Aktif", key="filtre_aktif"):
            st.session_state.fa = "aktif"; st.session_state.fv = None
    with cols[-1]:
        if st.button("Pasif", key="filtre_pasif"):
            st.session_state.fa = "pasif"; st.session_state.fv = None
    fv = st.session_state.get("fv", None)
    fa = st.session_state.get("fa", None)
    q="SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,p.gemiden_cekilme,p.carkci_ile_sorun,p.gemi_tutumu,p.izin_tercih_gunleri,p.izin_saat_araligi,p.is_kalitesi,p.performans_notu,p.durum,p.aktif FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id"
    params=()
    if fv: q+=" WHERE p.vardiya_tipi=?"; params=(fv,)
    if fa:
        if "WHERE" in q: q+=" AND p.aktif=?" if fa=="aktif" else " AND p.aktif=0"
        else: q+=" WHERE p.aktif=?" if fa=="aktif" else " WHERE p.aktif=0"
        params=params+(1,) if fa=="aktif" else params+(0,)
    rows=sql_all(q+" ORDER BY p.id DESC",params)
    if arama:
        arama=arama.lower()
        rows=[r for r in rows if arama in f"{r['ad']} {r['soyad']} {r['vardiya_tipi']} {r.get('gemi','')} {r.get('durum','')}".lower()]
    # Toplu durum değiştirme
    with st.expander("🔄 Toplu Durum Değiştir"):
        sec_personel = st.multiselect("Personel seç", [f"{r['ad']} {r['soyad']} (ID:{r['id']})" for r in rows], key="toplu_durum_personel")
        yeni_durum = st.selectbox("Yeni Durum", PERSONEL_DURUM, key="toplu_yeni_durum")
        if st.button("Durumları Güncelle", key="toplu_durum_btn"):
            if sec_personel:
                ids = [int(p.split("ID:")[1].replace(")","")) for p in sec_personel]
                for pid in ids:
                    sql_run("UPDATE personel SET durum=? WHERE id=?", (yeni_durum, pid))
                st.toast(f"{len(ids)} personelin durumu güncellendi!", icon="🔄")
                st.rerun()
    # Personel kartı (GEMİ ADI EKLENDİ)
    st.subheader("🔍 Personel Kartı")
    kart_sec = st.selectbox("Personel seç (detaylı kart için)", [f"{r['ad']} {r['soyad']} (ID:{r['id']})" for r in rows], key="personel_kart")
    if kart_sec:
        pid = int(kart_sec.split("ID:")[1].replace(")",""))
        # Gemi adını da getir
        p = sql_one("SELECT p.*, g.ad AS gemi_adi FROM personel p LEFT JOIN gemi g ON p.gemi_id = g.id WHERE p.id=?", (pid,))
        if p:
            with st.expander(f"📋 {p['ad']} {p['soyad']} - Detaylı Kart", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Vardiya Tipi:** {p['vardiya_tipi']}")
                    st.markdown(f"**Durum:** {p.get('durum','-')}")
                    st.markdown(f"**İş Kalitesi:** {p.get('is_kalitesi','-')}")
                    st.markdown(f"**Gemi:** {p.get('gemi_adi', '-')}")
                    st.markdown(f"**Gemi Tutum:** {p.get('gemi_tutumu','-')}")
                with col2:
                    st.markdown(f"**NLP Skoru:** {nlp_skor(p.get('performans_notu') or '') + nlp_skor(p.get('carkci_sorun_notu') or ''):.2f}")
                    st.markdown(f"**Performans Notu:** {p.get('performans_notu') or '-'}")
                    st.markdown(f"**Çarkçı Sorun Notu:** {p.get('carkci_sorun_notu') or '-'}")
                bugun = date.today()
                son_7_gun = [(bugun - timedelta(days=i)).isoformat() for i in range(7)]
                calisma_gunleri = sql_all("SELECT tarih FROM vardiya_plan WHERE personel_id=? AND tarih >= ?", (pid, (bugun - timedelta(days=7)).isoformat()))
                izin_gunleri = sql_all("SELECT baslangic, bitis FROM izin WHERE personel_id=? AND baslangic <= ? AND bitis >= ?", (pid, bugun.isoformat(), (bugun - timedelta(days=7)).isoformat()))
                st.markdown("**Son 7 Gün:**")
                gunler_str = ""
                for gun in son_7_gun:
                    if any(g["tarih"] == gun for g in calisma_gunleri): gunler_str += f"🟢 {gun} | "
                    elif any(g["baslangic"] <= gun <= g["bitis"] for g in izin_gunleri): gunler_str += f"🔴 {gun} | "
                    else: gunler_str += f"⚪ {gun} | "
                st.text(gunler_str)
                sertifikalar = sql_all("SELECT m.ad AS makine, s.sertifika_adi, s.gecerlilik_tarihi FROM personel_sertifika s JOIN makine_tipi m ON s.makine_tipi_id=m.id WHERE s.personel_id=?", (pid,))
                if sertifikalar:
                    st.markdown("**Sertifikalar:**")
                    st.dataframe(pd.DataFrame(sertifikalar), use_container_width=True, hide_index=True)
    # ... (devamı aynı)
