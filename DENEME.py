"""
Ordino Yağcı Planlaması — TÜM DÜZELTMELER (gemi_id, toplam personel, vardiya silme, fotoğraf kaldırma, boştakiler makine, grafik, unique)
Çalıştır: streamlit run app.py
"""
from __future__ import annotations

import json, sqlite3, calendar as _cal, io, os, shutil, random
from datetime import date, timedelta, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF

# ---------- VERİTABANI ----------
DB_PATH = Path(__file__).parent / "ordino.db"
FOTO_DIR = Path(__file__).parent / "gemi_fotolari"
YEDEK_DIR = Path(__file__).parent / "yedekler"

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
    c.execute("CREATE TABLE IF NOT EXISTS gemi (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT UNIQUE NOT NULL, kod TEXT, konum TEXT, foto TEXT)")
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
    # Eksik sütunları ekle
    for tab, col, typ in [("gemi","konum","TEXT"),("gemi","foto","TEXT"),
                          ("personel","gemi_id_list","TEXT"),("personel","makine_tipi_id_list","TEXT"),
                          ("personel","gemiden_cekilme","INTEGER DEFAULT 0"),("personel","carkci_ile_sorun","INTEGER DEFAULT 0"),
                          ("personel","carkci_sorun_notu","TEXT"),("personel","gemi_tutumu","TEXT"),
                          ("personel","izin_tercih_gunleri","TEXT"),("personel","izin_saat_araligi","TEXT"),
                          ("personel","is_kalitesi","INTEGER"),("personel","performans_notu","TEXT"),
                          ("personel","aktif","INTEGER DEFAULT 1"),("personel","durum","TEXT DEFAULT 'Gemide'"),
                          ("izin","gunler_json","TEXT"),("carkci","vardiya_gunleri","TEXT"),
                          ("carkci","puan_kirma","INTEGER DEFAULT 0")]:
        c.execute(f"PRAGMA table_info({tab})")
        if col not in [r[1] for r in c.fetchall()]:
            try: c.execute(f"ALTER TABLE {tab} ADD COLUMN {col} {typ}")
            except: pass
    # Unique constraint kontrolü (eski veritabanlarında olmayabilir)
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

def fazla_mesai_kontrol(pid, tarih):
    bas = (tarih - timedelta(days=7)).isoformat()
    bit = tarih.isoformat()
    row = sql_one("SELECT COUNT(DISTINCT tarih) AS c FROM vardiya_plan WHERE personel_id=? AND tarih >= ? AND tarih <= ?", (pid, bas, bit))
    gun = row["c"] if row else 0
    return gun >= 6, gun

def vardiya_plani_kontrol(gemi_id, makine_tipi_id, tarih):
    row = sql_one("SELECT personel_id FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi_id, makine_tipi_id, tarih.isoformat()))
    return row["personel_id"] if row else None

def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
    mevcut = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
    if mevcut:
        p = sql_one("SELECT id,ad,soyad,vardiya_tipi,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,carkci_ile_sorun,is_kalitesi,durum FROM personel WHERE id=?", (mevcut,))
        if p: return [{**p, "puan":999, "uyari_8_5":p.get("vardiya_tipi")=="8_5", "zaten_atanmis":True}]
    tum = sql_all("SELECT id,ad,soyad,vardiya_tipi,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,carkci_ile_sorun,is_kalitesi,durum FROM personel WHERE aktif=1 AND durum IN ('Gemide','İskelede')")
    gemi_konum = sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,))["konum"]
    sonuclar = []
    for p in tum:
        if cikan_id and p["id"] == cikan_id: continue
        if izinde_mi(p["id"], hedef_tarih): continue
        if baska_gemide_mi(p["id"], hedef_tarih, gemi_id, esnek=esnek_cakisma): continue
        if ayni_gun_baska_makine(p["id"], hedef_tarih, makine_tipi_id): continue
        vardiya = p.get("vardiya_tipi","")
        if vardiya == "GECE" and gemi_konum != "Gecede": continue
        mids = _id_listesi(p.get("makine_tipi_id_list")) or ([p["makine_tipi_id"]] if p.get("makine_tipi_id") else [])
        if makine_tipi_id not in mids: continue
        if not sertifika_gecerli_mi(p["id"], makine_tipi_id, hedef_tarih): continue
        gids = _id_listesi(p.get("gemi_id_list")) or ([p.get("gemi_id")] if p.get("gemi_id") else [])
        if gemi_id not in gids: continue
        if p.get("carkci_ile_sorun"): continue
        fazla, gun = fazla_mesai_kontrol(p["id"], hedef_tarih)
        vardiya_puan = {"IZINCI":100, "TERSANE":95, "GECE":105, "GRUPCU":80, "SABIT":60, "8_5":40}.get(vardiya, 50)
        kalite_puan = (p.get("is_kalitesi") or 3) * 10
        mesai_ceza = -20 if fazla else 0
        sonuclar.append({**p, "puan":vardiya_puan+kalite_puan+mesai_ceza, "uyari_8_5":vardiya=="8_5", "zaten_atanmis":False, "fazla_mesai":fazla, "son_7_gun":gun})
    sonuclar.sort(key=lambda x: -x["puan"])
    return sonuclar[:limit]

def to_dict_rows(oneriler):
    tum_mak = {r["id"]: r["ad"] for r in sql_all("SELECT id,ad FROM makine_tipi")}
    rows = []
    for o in oneriler:
        mids = _id_listesi(o.get("makine_tipi_id_list")) or ([o["makine_tipi_id"]] if o.get("makine_tipi_id") else [])
        ad = f"{o['ad']} {o['soyad']}"
        if o.get("fazla_mesai"): ad += " ⚠️ FAZLA MESAİ"
        rows.append({"id":o["id"], "ad_soyad":ad, "vardiya":o.get("vardiya_tipi","-"), "makine":", ".join(tum_mak.get(m,str(m)) for m in mids), "puan":o["puan"], "uyari_8_5":o.get("uyari_8_5",False), "zaten_atanmis":o.get("zaten_atanmis",False)})
    return rows

# ---------- TAKVİM ----------
def _takvim_html(yil, ay, isaretli):
    son_gun = _cal.monthrange(yil, ay)[1]
    ilk = date(yil, ay, 1).weekday()
    bugun = date.today()
    css = "<style>.cal{font-family:system-ui;max-width:400px;margin:0 auto;background:#2b2b2b;border-radius:16px;padding:16px;}.cal-title{text-align:center;font-size:18px;font-weight:600;color:#f0f0f0;margin-bottom:12px;}.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}.cal-hdr{text-align:center;font-size:12px;font-weight:600;color:#aaa;padding:6px 0;}.cal-cell{text-align:center;padding:10px 2px;border-radius:10px;font-size:14px;font-weight:500;}.cal-empty{background:transparent;}.cal-normal{background:#3a3a3a;color:#ddd;}.cal-izin{background:#f3831f;color:#fff;font-weight:600;}.cal-bugun{background:#2b2b2b;color:#f3831f;border:2px solid #f3831f;font-weight:700;}</style>"
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
        pdf.set_font('Arial','B',14)
        pdf.cell(0,10,'Vardiya Plani',0,1,'C')
        pdf.ln(5)
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
        sql_run("INSERT INTO personel(ad,soyad,gemi_id,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,is_kalitesi,durum) VALUES(?,?,?,?,?,?,?,?,?)",(ad,soyad,gid,mid,_makine_id_json([mid]),vt,json.dumps(random.sample(range(7),random.randint(2,5))),random.randint(2,5),random.choice(PERSONEL_DURUM)))
    st.success("Test verileri oluşturuldu!")
    st.rerun()

# ---------- SAYFALAR ----------
def _sayfa_yapboz():
    st.subheader("🧩 İnteraktif Yapboz")
    sec_tarih = st.date_input("Tarih", value=date.today(), key="yapboz_tarih", format="DD.MM.YYYY")
    gemiler = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler: st.warning("Gemi ve makine ekleyin."); return
    izinli = {r["personel_id"] for r in sql_all("SELECT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (sec_tarih.isoformat(),))}
    for gemi in gemiler:
        st.markdown(f"### 🚢 {gemi['ad']}")
        cols = st.columns(len(makineler))
        for i, mak in enumerate(makineler):
            with cols[i]:
                mevcut = vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih)
                if mevcut:
                    p = sql_one("SELECT ad,soyad,vardiya_tipi,durum FROM personel WHERE id=?",(mevcut,))
                    if p: st.success(f"**{p['ad']} {p['soyad']}** ({p['vardiya_tipi']}) {p.get('durum','')}")
                    if st.button("❌", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}"):
                        sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",(gemi["id"],mak["id"],sec_tarih.isoformat()))
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
                        uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum','')})")
                    if len(uygun)==1: st.caption("Uygun yok")
                    else:
                        sec = st.selectbox("Seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                        if sec != "Seçiniz...":
                            pid = sql_one("SELECT id FROM personel WHERE ad||' '||soyad=?",(sec.split(" (")[0],))["id"]
                            try:
                                sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?)",(pid,gemi["id"],mak["id"],sec_tarih.isoformat()))
                                sql_run("INSERT INTO performans_gecmis(personel_id,tarih,puan,kaynak) VALUES(?,?,?,?)",(pid,sec_tarih.isoformat(),sql_one("SELECT is_kalitesi FROM personel WHERE id=?",(pid,))["is_kalitesi"] or 3,'otomatik'))
                                st.success("Atandı!"); st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Bu atama zaten mevcut!")
        st.divider()

def _sayfa_excel():
    st.subheader("🚢 Gemiler & Makine")
    with st.form("f"):
        c1,c2,c3,c4 = st.columns(4)
        gad=c1.text_input("Gemi Adı"); gkd=c2.text_input("Kod")
        mad=c3.text_input("Makine Tipi"); kon=c4.selectbox("Konum",GEMI_KONUMLARI,index=3)
        if st.form_submit_button("➕ Ekle"):
            if not gad or not mad: st.error("Zorunlu alanlar")
            else:
                try: sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(gad.strip(),gkd.strip() or None,kon if kon!="Belirtilmedi" else None))
                except: st.warning("Gemi var")
                try: sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(mad.strip(),))
                except: st.warning("Makine var")
                st.success("Eklendi"); st.rerun()
    st.divider()
    g_rows = sql_all("SELECT g.id,g.ad,g.kod,g.konum,COUNT(p.id) AS personel FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad")
    st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)
    c1,c2=st.columns(2)
    with c1:
        with st.expander("✏️ Gemi Düzenle/Sil (Fotoğraf)"):
            if g_rows:
                gm={f"{r['ad']} (ID:{r['id']})":r for r in g_rows}
                gs=st.selectbox("Gemi",list(gm.keys()),key="gds"); gr=gm[gs]
                na=st.text_input("Ad",gr["ad"] or "",key="gna"); nk=st.text_input("Kod",gr["kod"] or "",key="gnk")
                nkon=st.selectbox("Konum",GEMI_KONUMLARI,index=GEMI_KONUMLARI.index(gr["konum"]) if gr["konum"] in GEMI_KONUMLARI else 3,key="gnkon")
                if gr.get("foto") and Path(gr["foto"]).exists():
                    st.image(str(gr["foto"]),width=200)
                    if st.button("🗑️ Fotoğrafı Kaldır", key="foto_sil"):
                        os.remove(gr["foto"])
                        sql_run("UPDATE gemi SET foto=NULL WHERE id=?",(gr["id"],))
                        st.success("Fotoğraf kaldırıldı"); st.rerun()
                uf=st.file_uploader("Yeni Foto",type=["png","jpg"],key="gdf")
                if st.button("Güncelle",key="bgd"):
                    if not na: st.error("Ad boş")
                    else:
                        fk=gr["foto"]
                        if uf:
                            FOTO_DIR.mkdir(exist_ok=True)
                            fp=FOTO_DIR/f"gemi_{gr['id']}.{uf.name.split('.')[-1]}"
                            with open(fp,"wb") as f: f.write(uf.getbuffer())
                            fk=str(fp)
                        sql_run("UPDATE gemi SET ad=?,kod=?,konum=?,foto=? WHERE id=?",(na.strip(),nk.strip() or None,nkon if nkon!="Belirtilmedi" else None,fk,gr["id"]))
                        st.success("Güncellendi"); st.rerun()
                if st.button("Sil",key="bgs",type="secondary"):
                    if sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=?",(gr["id"],))["c"]>0: st.error("Bağlı personel var")
                    else:
                        if gr.get("foto") and Path(gr["foto"]).exists(): os.remove(gr["foto"])
                        sql_run("DELETE FROM carkci WHERE gemi_id=?",(gr["id"],)); sql_run("DELETE FROM vardiya_plan WHERE gemi_id=?",(gr["id"],)); sql_run("DELETE FROM gemi WHERE id=?",(gr["id"],))
                        st.success("Silindi"); st.rerun()
    with c2:
        with st.expander("✏️ Makine Düzenle/Sil"):
            mr=sql_all("SELECT m.id,m.ad,COUNT(p.id) AS c FROM makine_tipi m LEFT JOIN personel p ON p.makine_tipi_id=m.id GROUP BY m.id ORDER BY m.ad")
            if mr:
                mm={f"{r['ad']} (ID:{r['id']})":r for r in mr}
                ms=st.selectbox("Makine",list(mm.keys()),key="mds"); mrow=mm[ms]
                nm=st.text_input("Ad",mrow["ad"] or "",key="mna")
                if st.button("Güncelle",key="bmd"):
                    if not nm: st.error("Ad boş")
                    else: sql_run("UPDATE makine_tipi SET ad=? WHERE id=?",(nm.strip(),mrow["id"])); st.success("Güncellendi"); st.rerun()
                if st.button("Sil",key="bms",type="secondary"):
                    if mrow["c"]>0: st.error("Bağlı personel var")
                    else: sql_run("DELETE FROM vardiya_plan WHERE makine_tipi_id=?",(mrow["id"],)); sql_run("DELETE FROM makine_tipi WHERE id=?",(mrow["id"],)); st.success("Silindi"); st.rerun()
    st.divider()
    st.subheader("📸 Gemi Detay")
    for g in sql_all("SELECT * FROM gemi ORDER BY ad"):
        with st.container():
            c1,c2=st.columns([1,2])
            with c1:
                if g.get("foto") and Path(g["foto"]).exists(): st.image(str(g["foto"]), use_container_width=True)
                else: st.markdown("⚓")
            with c2:
                st.markdown(f"### {g['ad']} ({g.get('konum','-')})")
                yg=sql_all("SELECT ad,soyad,vardiya_tipi FROM personel WHERE aktif=1 AND (gemi_id=? OR gemi_id_list LIKE ?)",(g["id"],f'%{g["id"]}%'))
                if yg: st.markdown("**Yağcılar:** "+", ".join(f"{y['ad']} {y['soyad']} ({y['vardiya_tipi']})" for y in yg))
                else: st.markdown("*Yağcı yok*")
                ck=sql_all("SELECT ad,soyad,carkci_vardiya FROM carkci WHERE gemi_id=?",(g["id"],))
                if ck: st.markdown("**Çarkçılar:** "+", ".join(f"{c['ad']} {c['soyad']} ({c['carkci_vardiya']})" for c in ck))
                else: st.markdown("*Çarkçı yok*")
            st.markdown("---")

def _sayfa_personel():
    st.subheader("👷 Personel")
    gemiler=sql_all("SELECT id,ad FROM gemi ORDER BY ad")
    makineler=sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    st.caption("Filtre:")
    cs=st.columns(len(VARDIYA_TIPLERI)+1)
    if cs[0].button("Tümü",key="f0"): st.session_state.fv=None
    for i,vt in enumerate(VARDIYA_TIPLERI):
        if cs[i+1].button(vt,key=f"f{vt}"): st.session_state.fv=vt
    fv=st.session_state.get("fv",None)
    q="SELECT p.id,p.ad,p.soyad,g.ad AS gemi,p.gemi_id_list,p.makine_tipi_id_list,p.vardiya_tipi,p.vardiya_gunleri,p.gemiden_cekilme,p.carkci_ile_sorun,p.gemi_tutumu,p.izin_tercih_gunleri,p.izin_saat_araligi,p.is_kalitesi,p.performans_notu,p.durum FROM personel p LEFT JOIN gemi g ON g.id=p.gemi_id"
    if fv: q+=" WHERE p.vardiya_tipi=?"; rows=sql_all(q+" ORDER BY p.id DESC",(fv,))
    else: rows=sql_all(q+" ORDER BY p.id DESC")
    for s in rows:
        s["vardiya_gunleri"]=_json_gunleri_metne(s.get("vardiya_gunleri"))
        s["izin_tercih_gunleri"]=_json_gunleri_metne(s.get("izin_tercih_gunleri"))
        mids=_id_listesi(s.get("makine_tipi_id_list"))
        s["makine_tipleri"]=", ".join(str(m) for m in mids) if mids else "-"
        gids=_id_listesi(s.get("gemi_id_list"))
        s["gemiler"]=", ".join(str(g) for g in gids) if gids else (s.get("gemi") or "-")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if not gemiler or not makineler: st.warning("Önce gemi/makine ekleyin."); return
    with st.expander("➕ Yeni Personel"):
        c1,c2=st.columns(2)
        ad=c1.text_input("Ad",key="p_ad"); soyad=c2.text_input("Soyad",key="p_soyad")
        vt=st.selectbox("Vardiya Tipi",VARDIYA_TIPLERI,key="p_vt")
        mak_sec=st.multiselect("Makine Tipleri",[r["id"] for r in makineler],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="p_mak")
        gem_list=st.multiselect("Atandığı Gemiler",[r["id"] for r in gemiler],format_func=lambda i:next(r["ad"] for r in gemiler if r["id"]==i),key="p_gem")
        gem_tek=int(gem_list[0]) if gem_list else None
        sec=st.multiselect("Vardiya Günleri",GUNLER_TR,default=["Pazartesi","Çarşamba","Cuma"],key="p_vg")
        gun_json=json.dumps([GUNLER_TR.index(x) for x in sec])
        durum=st.selectbox("Durum",PERSONEL_DURUM,key="p_durum")
        st.markdown("##### Profil")
        c3,c4=st.columns(2)
        is_kal=c3.slider("İş Kalitesi (1-5)",1,5,3,key="p_ik")
        gemi_tut=c4.selectbox("Gemi İçi Tutum",["Mükemmel","İyi","Orta","Gelişmeli"],key="p_tut")
        izin_g=st.multiselect("Tercih İzin Günleri",GUNLER_TR,key="p_ig")
        izin_g_json=json.dumps([GUNLER_TR.index(x) for x in izin_g]) if izin_g else "[]"
        ib=c3.time_input("İzin Baş.",value=None,key="p_ib"); it=c4.time_input("İzin Bit.",value=None,key="p_it")
        pn=st.text_area("Performans Notu",key="p_not")
        if st.button("Kaydet",key="btn_pk"):
            if not ad or not soyad: st.error("Ad soyad zorunlu")
            elif not mak_sec: st.error("Makine seçin")
            else:
                try:
                    sql_run("INSERT INTO personel(ad,soyad,gemi_id,gemi_id_list,makine_tipi_id,makine_tipi_id_list,vardiya_tipi,vardiya_gunleri,gemi_tutumu,izin_tercih_gunleri,izin_saat_araligi,is_kalitesi,performans_notu,durum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (ad,soyad,gem_tek,_gemi_id_json(gem_list),int(mak_sec[0]),_makine_id_json(mak_sec),vt,gun_json,gemi_tut,izin_g_json,f"{ib.strftime('%H:%M')} - {it.strftime('%H:%M')}" if ib and it else None,is_kal,pn.strip() or None,durum))
                    st.success("Kaydedildi"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")
    with st.expander("✏️ Düzenle/Sil & Sertifika"):
        pm=_personel_label_map(sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad"))
        if not pm: st.info("Personel yok"); return
        secim=st.selectbox("Personel",list(pm.keys()),key="p_ds"); pid=pm[secim]
        mev=sql_one("SELECT * FROM personel WHERE id=?",(pid,))
        if not mev: return
        yvt=st.selectbox("Vardiya Tipi",VARDIYA_TIPLERI,index=VARDIYA_TIPLERI.index(mev["vardiya_tipi"]) if mev.get("vardiya_tipi") in VARDIYA_TIPLERI else 0,key="pd_vt")
        mids=_id_listesi(mev.get("makine_tipi_id_list")) or [mev["makine_tipi_id"]]
        ymak=st.multiselect("Makine Tipleri",[r["id"] for r in makineler],default=[m for m in mids if m in [r["id"] for r in makineler]],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="pd_mak")
        gids=_id_listesi(mev.get("gemi_id_list")) or ([mev["gemi_id"]] if mev.get("gemi_id") else [])
        ygem=st.multiselect("Atandığı Gemiler",[r["id"] for r in gemiler],default=[g for g in gids if g in [r["id"] for r in gemiler]],format_func=lambda i:next(r["ad"] for r in gemiler if r["id"]==i),key="pd_gem")
        ydurum=st.selectbox("Durum",PERSONEL_DURUM,index=PERSONEL_DURUM.index(mev["durum"]) if mev.get("durum") in PERSONEL_DURUM else 0,key="pd_durum")
        c1,c2=st.columns(2)
        if c1.button("Güncelle",key="bpgu"):
            if not ymak: st.error("Makine seçin")
            else:
                try:
                    yeni_gemi_id = ygem[0] if ygem else None
                    sql_run("UPDATE personel SET vardiya_tipi=?, makine_tipi_id_list=?, makine_tipi_id=?, gemi_id=?, gemi_id_list=?, durum=? WHERE id=?",
                            (yvt, _makine_id_json(ymak), int(ymak[0]), yeni_gemi_id, _gemi_id_json(ygem), ydurum, pid))
                    st.success("Güncellendi"); st.rerun()
                except Exception as e: st.error(f"Hata: {e}")
        if c2.button("Sil",key="bps",type="secondary"):
            for t in ["izin","vardiya_plan","personel_sertifika","performans_gecmis"]: sql_run(f"DELETE FROM {t} WHERE personel_id=?",(pid,))
            sql_run("DELETE FROM personel WHERE id=?",(pid,)); st.success("Silindi"); st.rerun()
        st.markdown("---\n#### Sertifika")
        sert=sql_all("SELECT * FROM personel_sertifika WHERE personel_id=?",(pid,))
        if sert: st.dataframe(pd.DataFrame(sert), use_container_width=True, hide_index=True)
        with st.form("sert_ekle",clear_on_submit=True):
            sm=st.selectbox("Makine",[r["id"] for r in makineler],format_func=lambda i:next(r["ad"] for r in makineler if r["id"]==i),key="sm")
            sa=st.text_input("Sertifika Adı",key="sa"); sg=st.date_input("Geçerlilik",value=None,key="sg",format="DD.MM.YYYY"); sn=st.text_input("Not",key="sn")
            if st.form_submit_button("Ekle"):
                sql_run("INSERT INTO personel_sertifika VALUES(NULL,?,?,?,?,?)",(pid,sm,sa or None,sg.isoformat() if sg else None,sn or None))
                st.success("Eklendi"); st.rerun()
        if sert:
            sil_s=st.selectbox("Silinecek",[f"{s['sertifika_adi'] or 'Sertifika'} (ID:{s['id']})" for s in sert],key="sils")
            if st.button("Sertifika Sil",key="bss"):
                sid=int(sil_s.split("ID:")[1].replace(")",""))
                sql_run("DELETE FROM personel_sertifika WHERE id=?",(sid,)); st.success("Silindi"); st.rerun()

def _sayfa_izin():
    st.subheader("📅 İzin")
    pl=sql_all("SELECT id,ad,soyad,vardiya_gunleri FROM personel WHERE aktif=1 ORDER BY ad")
    if not pl: st.info("Personel yok"); return
    cf,cc=st.columns([1,1])
    with cf:
        sec=st.selectbox("Personel",pl,format_func=lambda p:f"{p['ad']} {p['soyad']}",key="izp")
        pid=sec["id"]
        bas=st.date_input("Başlangıç",value=date.today(),key="izb",format="DD.MM.YYYY")
        bit=st.date_input("Bitiş",value=date.today(),key="izbi",format="DD.MM.YYYY")
        if bit>=bas:
            gun=gun_sayisi(bas,bit)
            st.info(f"📅 {gun} gün")
        else: st.error("Tarih hatası"); gun=0
        notlar=st.text_area("Not",key="izn",height=80)
        if st.button("✅ Kaydet",key="biz"):
            if gun<=0: st.error("Geçersiz aralık")
            else: sql_run("INSERT INTO izin VALUES(NULL,?,?,?,?,?,?)",(pid,bas.isoformat(),bit.isoformat(),gun,notlar or None,None)); st.success("Kaydedildi"); st.rerun()
    with cc:
        bugun=date.today()
        ay_s=st.selectbox("Ay",[f"{AY_ADLARI[m]} {bugun.year}" for m in range(1,13)],index=bugun.month-1,key="izay")
        ay_i=AY_ADLARI.index(ay_s.split()[0]); yil=int(ay_s.split()[1])
        isaret=set()
        for iz in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=?",(pid,)):
            d=date.fromisoformat(iz["baslangic"]); b=date.fromisoformat(iz["bitis"])
            while d<=b:
                if d.year==yil and d.month==ay_i: isaret.add(d)
                d+=timedelta(days=1)
        st.markdown(_takvim_html(yil,ay_i,isaret), unsafe_allow_html=True)
    st.divider(); st.markdown("#### Kayıtlı İzinler")
    izinler=sql_all("SELECT i.id,p.ad,p.soyad,i.baslangic,i.bitis,i.gun_sayisi,i.notlar FROM izin i JOIN personel p ON p.id=i.personel_id ORDER BY i.baslangic DESC LIMIT 100")
    if not izinler: st.info("İzin yok")
    else:
        for iz in izinler:
            c1,c2,c3=st.columns([4,2,1])
            c1.markdown(f"**{iz['ad']} {iz['soyad']}**  \n📅 {iz['baslangic']} → {iz['bitis']} · {iz['gun_sayisi']} gün")
            c2.markdown("🟠 Aktif" if iz["baslangic"]<=date.today().isoformat()<=iz["bitis"] else "✅ Tamamlandı")
            if c3.button("🗑️",key=f"izsil_{iz['id']}"): sql_run("DELETE FROM izin WHERE id=?",(iz["id"],)); st.success("Silindi"); st.rerun()

def _sayfa_carkci():
    st.subheader("⚙️ Çarkçı")
    gem=sql_all("SELECT id,ad FROM gemi ORDER BY ad"); yag=sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")
    if not gem or not yag: st.warning("Gemi/personel yok"); return
    c1,c2=st.columns(2)
    with c1:
        ad=c1.text_input("Ad",key="cka"); soyad=c2.text_input("Soyad",key="cks")
        gid=c1.selectbox("Gemi",[r["id"] for r in gem],format_func=lambda i:next(r["ad"] for r in gem if r["id"]==i),key="ckg")
        cvt=c1.selectbox("Vardiya",VARDIYA_TIPLERI,key="ckv"); cg=c1.multiselect("Günler",GUNLER_TR,key="ckgun")
    with c2:
        yop=[("(Seçilmedi)",None)]+[(f"{p['ad']} {p['soyad']}",p["id"]) for p in yag]
        ys=c2.selectbox("Sorunlu Yağcı",yop,format_func=lambda x:x[0],key="cky")
        sorun=c2.text_area("Sorun",key="ckso"); vn=c2.text_input("Vardiya Notu",key="ckvn")
        pk=c2.slider("Puan Kırma",0,5,0,key="ckp")
    if st.button("Oluştur",key="bck"):
        if not ad or not soyad: st.error("Ad soyad zorunlu")
        else:
            gun_j=json.dumps([GUNLER_TR.index(g) for g in cg]) if cg else "[]"
            pid_p=ys[1]
            sql_run("INSERT INTO carkci VALUES(NULL,?,?,?,?,?,?,?,?,?)",(ad,soyad,gid,pid_p,sorun,vn,cvt,gun_j,pk))
            if pid_p:
                mev=sql_one("SELECT is_kalitesi FROM personel WHERE id=?",(pid_p,))
                if mev:
                    yeni=max(1,(mev["is_kalitesi"] or 3)-pk)
                    sql_run("UPDATE personel SET is_kalitesi=?,carkci_ile_sorun=1,carkci_sorun_notu=? WHERE id=?",(yeni,sorun.strip() or None,pid_p))
                    sql_run("INSERT INTO performans_gecmis VALUES(NULL,?,?,?,?)",(pid_p,date.today().isoformat(),yeni,'carkci'))
                st.success("Yağcı puanı düşürüldü")
            else: st.success("Çarkçı eklendi")
            st.rerun()
    st.divider()
    cr=sql_all("SELECT c.id,c.ad,c.soyad,g.ad AS gemi,c.carkci_vardiya,c.vardiya_gunleri,p.ad||' '||p.soyad AS yagci,c.sorun_metni,c.puan_kirma FROM carkci c LEFT JOIN gemi g ON g.id=c.gemi_id LEFT JOIN personel p ON p.id=c.problemli_yagci_id ORDER BY c.id DESC LIMIT 30")
    for r in cr: r["vardiya_gunleri"]=_json_gunleri_metne(r.get("vardiya_gunleri"))
    st.dataframe(pd.DataFrame(cr), use_container_width=True, hide_index=True)

def _sayfa_acil():
    st.subheader("⚡ Acil Panel")
    gem=sql_all("SELECT id,ad,konum FROM gemi ORDER BY ad")
    mak=sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    bugun=date.today(); izinli=bugun_izinli_ids()
    
    st.markdown("### 👤 Boştakiler")
    if st.button("🔍 Listele",key="bbos"):
        bos=[]
        for p in sql_all("SELECT * FROM personel WHERE aktif=1"):
            if p["id"] in izinli: continue
            if sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih=?",(p["id"],bugun.isoformat()))["c"]==0:
                gemi_adi=next((g["ad"] for g in gem if g["id"]==p["gemi_id"]),"Bilinmiyor")
                mak_list = _id_listesi(p.get("makine_tipi_id_list")) or [p["makine_tipi_id"]]
                mak_ad = ", ".join(next((m["ad"] for m in mak if m["id"]==mid),"") for mid in mak_list)
                bos.append(f"- **{p['ad']} {p['soyad']}** ({p['vardiya_tipi']}) → {gemi_adi} | Makine: {mak_ad} [{p.get('durum','')}]")
        if bos: st.success(f"{len(bos)} kişi boşta"); [st.write(b) for b in bos]
        else: st.info("Boşta kimse yok")
    st.divider()
    
    st.markdown("### 🏝️ İskelede Bekleyenler")
    if st.button("🔍 İskele Listesi",key="biskele"):
        isk=sql_all("SELECT ad,soyad,vardiya_tipi,gemi_id FROM personel WHERE aktif=1 AND durum='İskelede'")
        if isk:
            st.success(f"{len(isk)} kişi iskelede:")
            for p in isk: st.write(f"- {p['ad']} {p['soyad']} ({p['vardiya_tipi']}) → {next((g['ad'] for g in gem if g['id']==p['gemi_id']),'?')}")
        else: st.info("İskelede bekleyen yok")
    st.divider()
    
    st.markdown("### 🏗️ Tersaneye Uygunlar")
    if st.button("🔍 Tersane Listesi",key="btersane"):
        ters_gem=[g for g in gem if g.get("konum")=="Tersane"]
        if not ters_gem: st.warning("Tersanede gemi yok")
        else:
            uygun=[]
            for g in ters_gem:
                for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND (gemi_id=? OR gemi_id_list LIKE ?)",(g["id"],f'%{g["id"]}%')):
                    if p["id"] in izinli: continue
                    if izinde_mi(p["id"],bugun): continue
                    mids=_id_listesi(p.get("makine_tipi_id_list")) or [p["makine_tipi_id"]]
                    for m in mak:
                        if m["id"] in mids and sertifika_gecerli_mi(p["id"],m["id"],bugun):
                            uygun.append(f"- {p['ad']} {p['soyad']} ({p['vardiya_tipi']}) → {g['ad']} / {m['ad']} [{p.get('durum','')}]")
            if uygun: st.success(f"{len(uygun)} uygun:"); [st.write(u) for u in uygun[:20]]
            else: st.info("Uygun yok")
    st.divider()
    
    st.markdown("### 📞 Anlık İzin Yerine")
    c1,c2=st.columns(2)
    with c1: cik=st.selectbox("İzin İsteyen",[f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")],key="acil_cik"); cik_id=int(cik.split("ID:")[1].replace(")","")) if cik else None
    with c2: hg=st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="acil_gemi"); hm=st.selectbox("Makine",[m["id"] for m in mak],format_func=lambda i:next(m["ad"] for m in mak if m["id"]==i),key="acil_mak")
    if st.button("🚨 Öner (5)",key="bacil"):
        on=onerileri_hesapla(hg,hm,bugun,cikan_id=cik_id,limit=5)
        if not on: st.warning("Uygun yok")
        else:
            for i,o in enumerate(on):
                st.success(f"{i+1}. {o['ad']} {o['soyad']} ({o['vardiya_tipi']}) - Puan:{o['puan']}")
                if o.get("uyari_8_5"): st.warning("⚠️ 8/5")
                if o.get("fazla_mesai"): st.warning("⚠️ Fazla mesai")
    st.divider()
    st.markdown("### 🌐 Tüm Boşluklar")
    if st.button("📋 Göster",key="btum"):
        for g in gem:
            for m in mak:
                if not vardiya_plani_kontrol(g["id"],m["id"],bugun):
                    on=onerileri_hesapla(g["id"],m["id"],bugun,limit=1)
                    if on: st.write(f"🔸 {g['ad']}/{m['ad']} → **{on[0]['ad']} {on[0]['soyad']}**")
                    else: st.write(f"🔸 {g['ad']}/{m['ad']} → ❌ Uygun yok")

def _sayfa_oneri():
    st.subheader("✦ Öneri & Plan")
    gem=sql_all("SELECT id,ad FROM gemi ORDER BY ad"); mak=sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
    if not gem or not mak: st.warning("Gemi/makine yok"); return
    izinli=bugun_izinli_ids()
    if izinli: st.warning("🟠 Bugün izinli: "+", ".join(f"{r['ad']} {r['soyad']}" for r in sql_all(f"SELECT ad,soyad FROM personel WHERE id IN ({','.join('?'*len(izinli))})",tuple(izinli))))
    esnek=st.checkbox("Esnek çakışma",value=False,key="esnek")
    st.subheader("🗓️ Toplu Planlama (Adil)")
    with st.expander("Ayarlar"):
        sg=st.multiselect("Gemiler",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="tpg"); sm=st.multiselect("Makine",[m["id"] for m in mak],format_func=lambda i:next(m["ad"] for m in mak if m["id"]==i),key="tpm")
        ba=st.date_input("Başlangıç",date.today(),key="tpb",format="DD.MM.YYYY"); bi=st.date_input("Bitiş",date.today()+timedelta(days=7),key="tpi",format="DD.MM.YYYY")
        gn=st.multiselect("Günler",GUNLER_TR,default=["Pazartesi","Salı","Çarşamba","Perşembe","Cuma"],key="tpgun"); gi=[GUNLER_TR.index(g) for g in gn]
        if st.button("🚀 Oluştur",key="btp"):
            if not sg or not sm: st.error("Seçim yapın")
            else:
                kul={}; top=0
                for g in sg:
                    for m in sm:
                        d=ba
                        while d<=bi:
                            if d.weekday() in gi and not vardiya_plani_kontrol(g,m,d):
                                on=onerileri_hesapla(g,m,d,limit=10,esnek_cakisma=esnek)
                                on.sort(key=lambda x:kul.get(x["id"],0))
                                if on:
                                    sec=on[0]
                                    if not sec.get("zaten_atanmis"):
                                        try:
                                            sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?)",(sec["id"],g,m,d.isoformat()))
                                            kul[sec["id"]]=kul.get(sec["id"],0)+1; top+=1
                                        except sqlite3.IntegrityError: pass
                            d+=timedelta(days=1)
                st.success(f"{top} vardiya adil dağıtıldı"); st.rerun()
    st.divider()
    # Vardiya silme arayüzü
    with st.expander("🗑️ Vardiya Sil"):
        sil_gemi=st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="silgemi")
        sil_mak=st.selectbox("Makine",[m["id"] for m in mak],format_func=lambda i:next(m["ad"] for m in mak if m["id"]==i),key="silmak")
        sil_tarih=st.date_input("Tarih",date.today(),key="siltarih",format="DD.MM.YYYY")
        mevcut_sil=sql_one("SELECT p.ad||' '||p.soyad AS isim FROM vardiya_plan v JOIN personel p ON v.personel_id=p.id WHERE v.gemi_id=? AND v.makine_tipi_id=? AND v.tarih=?",(sil_gemi,sil_mak,sil_tarih.isoformat()))
        if mevcut_sil:
            st.warning(f"Mevcut atama: {mevcut_sil['isim']}")
            if st.button("Atamayı Sil",key="sil_ata"):
                sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?",(sil_gemi,sil_mak,sil_tarih.isoformat()))
                st.success("Atama silindi"); st.rerun()
        else: st.info("Bu tarihte atama yok")
    st.divider()
    st.subheader("Tek Seferlik Öneri")
    gid=st.selectbox("Gemi",[g["id"] for g in gem],format_func=lambda i:next(g["ad"] for g in gem if g["id"]==i),key="ong"); mid=st.selectbox("Makine",[m["id"] for m in mak],format_func=lambda i:next(m["ad"] for m in mak if m["id"]==i),key="onm")
    ht=st.date_input("Tarih",date.today(),key="onht",format="DD.MM.YYYY")
    tum=sql_all("SELECT id,ad,soyad,gemi_id,gemi_id_list FROM personel WHERE aktif=1")
    gemi_p=[p for p in tum if p["gemi_id"]==gid or gid in _id_listesi(p.get("gemi_id_list"))]
    cik_opts=[("(Yok)",None)]+[(f"{p['ad']} {p['soyad']}{' 🟠' if p['id'] in izinli else ''}",p["id"]) for p in sorted(gemi_p,key=lambda x:(0 if x['id'] in izinli else 1,x['ad']))]
    def_idx=next((i for i,(_,pid) in enumerate(cik_opts) if pid in izinli),0)
    cik_sec=st.selectbox("Çıkan",cik_opts,format_func=lambda x:x[0],index=def_idx,key="oncik"); cik_id=cik_sec[1]
    st.info("💡 Mantık: 1) İzin/çakışma/sorun yok, 2) İZİNCİ/TERSANE/GECE öncelikli, 3) Sertifika")
    if st.button("🔍 Öner",key="bon"):
        out=onerileri_hesapla(gid,mid,ht,cik_id,5,esnek)
        rows=to_dict_rows(out)
        if not rows: st.warning("Uygun yok")
        else:
            if any(r.get("zaten_atanmis") for r in rows): st.success("Zaten atanmış")
            else: st.success(f"{len(rows)} aday:"); st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.divider(); st.markdown("#### Tekil Ata")
    ps=st.selectbox("Personel",[f"{p['ad']} {p['soyad']}" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1")],key="vdp")
    if st.button("✅ Kaydet",key="bvk"):
        p_sec=sql_one("SELECT id FROM personel WHERE ad||' '||soyad=?",(ps,))
        if p_sec:
            if not esnek and baska_gemide_mi(p_sec["id"],ht,gid): st.error("Başka gemide çalışıyor")
            elif vardiya_plani_kontrol(gid,mid,ht): st.error("Zaten atanmış")
            else:
                try:
                    sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?)",(p_sec["id"],gid,mid,ht.isoformat()))
                    st.success("Atandı")
                except sqlite3.IntegrityError:
                    st.error("Bu atama zaten mevcut")

def _sayfa_bilgi():
    st.subheader("📊 Bilgi & Rapor")
    c1,c2,c3=st.columns(3)
    with c1:
        if st.button("💾 Yedekle",key="byedek"): st.success(f"Yedek: {veritabani_yedekle().name}")
    with c2:
        if st.button("🧪 Test Verisi",key="btest"): test_verisi_olustur()
    with c3:
        st.download_button("📥 DB İndir",open(DB_PATH,"rb"),file_name=f"ordino_{date.today().isoformat()}.db")
    st.divider()
    st.subheader("📄 PDF")
    cp1,cp2=st.columns(2)
    with cp1:
        if st.button("Aylık Özet PDF",key="bpdfa"):
            p=pdf_rapor_olustur("aylik_ozet"); st.download_button("İndir",open(p,"rb"),file_name=p.name)
    with cp2:
        if st.button("Vardiya Plan PDF",key="bpdfv"):
            p=pdf_rapor_olustur("vardiya_plani"); st.download_button("İndir",open(p,"rb"),file_name=p.name)
    st.divider()
    st.markdown("### 🚨 Uyarılar")
    uyari_say=0; uyari_metin=[]
    bugun=date.today()
    izinli=sql_all("SELECT p.ad,p.soyad FROM izin i JOIN personel p ON p.id=i.personel_id WHERE date('now') BETWEEN i.baslangic AND i.bitis")
    if izinli:
        uyari_say+=len(izinli); uyari_metin.append(f"{len(izinli)} kişi izinde")
        with st.expander(f"🟠 İzinli ({len(izinli)})",expanded=True): st.dataframe(pd.DataFrame(izinli), use_container_width=True, hide_index=True)
    fazla=[]
    for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1"):
        fz,gn=fazla_mesai_kontrol(p["id"],bugun)
        if fz: fazla.append(f"{p['ad']} {p['soyad']} ({gn} gün)")
    if fazla:
        uyari_say+=len(fazla); uyari_metin.append(f"{len(fazla)} kişi fazla mesai")
        with st.expander("⚠️ Fazla Mesai"): [st.write(f"- {f}") for f in fazla]
    yarin=(bugun+timedelta(days=1)).isoformat()
    y_izin=sql_all("SELECT p.ad,p.soyad FROM izin i JOIN personel p ON p.id=i.personel_id WHERE i.baslangic=?",(yarin,))
    if y_izin:
        uyari_say+=len(y_izin); uyari_metin.append(f"Yarın {len(y_izin)} kişi izin başlıyor")
        with st.expander("🔵 Yarın Başlayacak"): st.dataframe(pd.DataFrame(y_izin), use_container_width=True, hide_index=True)
    if uyari_say==0: st.success("Uyarı yok")
    elif st.button("🔊 Sesli Oku"):
        js=f"<script>var m=new SpeechSynthesisUtterance('{'. '.join(uyari_metin)}');m.lang='tr-TR';speechSynthesis.speak(m)</script>"
        st.components.v1.html(js,height=0)
    st.divider()
    st.subheader("📅 Aylık Performans")
    ay_s=st.selectbox("Ay",[f"{AY_ADLARI[m]} {bugun.year}" for m in range(1,13)],index=bugun.month-1,key="ozetay")
    ay_i=AY_ADLARI.index(ay_s.split()[0]); yil=int(ay_s.split()[1])
    bas=date(yil,ay_i,1); son=date(yil,ay_i,_cal.monthrange(yil,ay_i)[1])
    data=[]
    for p in sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad"):
        iz=sum(max(0,(min(date.fromisoformat(i["bitis"]),son)-max(date.fromisoformat(i["baslangic"]),bas)).days+1) for i in sql_all("SELECT baslangic,bitis FROM izin WHERE personel_id=? AND baslangic<=? AND bitis>=?",(p["id"],son.isoformat(),bas.isoformat())))
        cal=sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE personel_id=? AND tarih>=? AND tarih<=?",(p["id"],bas.isoformat(),son.isoformat()))["c"]
        data.append({"Personel":f"{p['ad']} {p['soyad']}","Çalışma":cal,"İzin":iz})
    if data:
        df=pd.DataFrame(data); st.dataframe(df, use_container_width=True, hide_index=True)
        st.bar_chart(df.set_index("Personel"), use_container_width=True)
    st.divider()
    st.subheader("📈 Performans Geçmişi")
    per_sec=st.selectbox("Personel",[f"{p['ad']} {p['soyad']}" for p in sql_all("SELECT id,ad,soyad FROM personel ORDER BY ad")],key="perfp")
    if per_sec:
        pid=sql_one("SELECT id FROM personel WHERE ad||' '||soyad=?",(per_sec,))["id"]
        gec=sql_all("SELECT tarih,puan,kaynak FROM performans_gecmis WHERE personel_id=? ORDER BY tarih",(pid,))
        if gec:
            dfp=pd.DataFrame(gec)
            dfp['tarih'] = pd.to_datetime(dfp['tarih'])  # Düzgün tarih ekseni için
            dfp = dfp.sort_values('tarih')
            st.line_chart(dfp.set_index("tarih")["puan"], use_container_width=True)
        else: st.info("Geçmiş yok")
    st.divider()
    st.metric("Toplam Personel (Aktif)", sql_one("SELECT COUNT(*) AS c FROM personel WHERE aktif=1")["c"])
    st.metric("Toplam Gemi", sql_one("SELECT COUNT(*) AS c FROM gemi")["c"])
    st.divider(); st.markdown("#### 📥 Excel Çıktısı")
    plan=sql_all("SELECT v.tarih,g.ad AS gemi,m.ad AS makine,p.ad||' '||p.soyad AS personel FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id JOIN makine_tipi m ON v.makine_tipi_id=m.id JOIN personel p ON v.personel_id=p.id ORDER BY v.tarih DESC")
    if plan:
        st.dataframe(pd.DataFrame(plan), use_container_width=True, hide_index=True)
        buf=io.BytesIO(); pd.DataFrame(plan).to_excel(buf,index=False); buf.seek(0)
        st.download_button("📥 Excel",data=buf,file_name="vardiya_plani.xlsx")

def main():
    st.set_page_config(page_title="Ordino Yağcı", page_icon="⚓", layout="centered")
    st.markdown("""<style>.stApp{background:#1a1a2e}.main .block-container{background:#2b2b3d;border-radius:20px;padding:1.5rem 1rem;box-shadow:0 4px 20px rgba(0,0,0,0.4);margin-top:10px;color:#f0f0f0;max-width:700px;margin-left:auto;margin-right:auto}h1,h2,h3,h4,h5,h6,p,span,div,label{color:#f0f0f0!important}.stTabs [role="tablist"]{gap:.2rem;flex-wrap:wrap}.stTabs [role="tab"]{background:#3a3a4e;border:none;border-radius:10px;padding:.4rem .6rem;color:#ccc!important;font-weight:500;font-size:.85rem}.stTabs [aria-selected="true"]{background:#f3831f;color:#fff!important}.stButton>button{background:#f3831f;color:white;border:none;border-radius:10px;padding:.5rem 1rem;font-weight:600;width:100%;min-height:44px}.stButton>button:hover{background:#d35400}</style>""",unsafe_allow_html=True)
    init_db()
    st.title("⚓ Ordino Yağcı Planlaması")
    t1,t2,t3,t4,t5,t6=st.tabs(["🧩 Yapboz","⚡ Acil","🚢 Gemiler","👷 Personel & İzin","✦ Öneri","📊 Bilgi"])
    with t1: _sayfa_yapboz()
    with t2: _sayfa_acil()
    with t3: _sayfa_excel()
    with t4: _sayfa_personel(); st.divider(); _sayfa_izin()
    with t5: _sayfa_oneri(); st.divider(); _sayfa_carkci()
    with t6: _sayfa_bilgi()
    st.divider()
    with st.expander("📱 Telefonda Kullanım"): st.markdown("- Safari → Paylaş → Ana Ekrana Ekle\n- Chrome → Ana Ekrana Ekle")

if __name__ == "__main__":
    main()
