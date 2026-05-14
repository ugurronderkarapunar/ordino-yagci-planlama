 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/claude deneme.py b/claude deneme.py
index 027b4f84ea490b2a9f8637a6b4de83782288d114..36658af865481b5120ce9a3ce60a50d72b5df67b 100644
--- a/claude deneme.py	
+++ b/claude deneme.py	
@@ -1,34 +1,34 @@
 """
 Ordino Yağcı Planlaması — v8.0 (Tüm sayfalar tam, gemi silme ve vardiya günü düzeltmeleriyle)
 """
 from __future__ import annotations
 
 import json, sqlite3, calendar as _cal, shutil
 from datetime import date, timedelta, datetime
 from pathlib import Path
-from typing import Tuple
+from typing import Optional, Tuple
 
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
@@ -176,53 +176,56 @@ def _id_listesi(v):
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
 
+def izinli_ids(kontrol_tarih: Optional[date] = None) -> set[int]:
+    hedef = (kontrol_tarih or date.today()).isoformat()
+    return {r["personel_id"] for r in sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (hedef,))}
+
 def bugun_izinli_ids():
-    bugun = date.today().isoformat()
-    return {r["personel_id"] for r in sql_all("SELECT DISTINCT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (bugun,))}
+    return izinli_ids(date.today())
 
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
            FROM vardiya_plan v JOIN gemi g ON v.gemi_id=g.id
            JOIN makine_tipi m ON v.makine_tipi_id=m.id
            JOIN personel p ON v.personel_id=p.id
            WHERE v.tarih=?""",
         (bugun,),
     )
     tum_pozisyonlar = sql_all(
@@ -274,51 +277,50 @@ def _takvim_html(yil, ay, isaretli, koyu=True):
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
         rows.append({"id": o["id"], "ad_soyad": f"{o['ad']} {o['soyad']}",
                      "vardiya": o.get("vardiya_tipi", "-"), "makine": makine_str,
                      "puan": o["puan"], "zaten_atanmis": o.get("zaten_atanmis", False)})
     return rows
 
 # ---------- ÖNERİ MOTORU ----------
-@st.cache_data(ttl=60, show_spinner=False)
 def _tum_aktif_personel_cache():
     return sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))")
 
 def onerileri_hesapla(gemi_id, makine_tipi_id, hedef_tarih, cikan_id=None, limit=5, esnek_cakisma=False):
     mevcut = vardiya_plani_kontrol(gemi_id, makine_tipi_id, hedef_tarih)
     if mevcut:
         p = sql_one("SELECT id,ad,soyad,vardiya_tipi,is_kalitesi FROM personel WHERE id=?", (mevcut,))
         if p: return [{**p, "puan":999, "uyari_8_5":p.get("vardiya_tipi")=="8_5", "zaten_atanmis":True}]
     tum = _tum_aktif_personel_cache()
     gemi_konum = (sql_one("SELECT konum FROM gemi WHERE id=?", (gemi_id,)) or {}).get("konum")
     hedef_gun  = hedef_tarih.weekday()
     izinli_ids = {r["personel_id"] for r in sql_all("SELECT personel_id FROM izin WHERE ? BETWEEN baslangic AND bitis", (hedef_tarih.isoformat(),))}
     tum_atamalar = sql_all("SELECT personel_id,baslangic_saat,bitis_saat FROM vardiya_plan WHERE tarih=?", (hedef_tarih.isoformat(),))
     atama_dict: dict[int, list] = {}
     for a in tum_atamalar:
         atama_dict.setdefault(a["personel_id"], []).append(a)
     ayar = st.session_state.get("ayarlar", DEFAULT_AYARLAR)
     max_saat = ayar.get("max_haftalik_saat", 45)
     sonuclar = []
     for p in tum:
         if cikan_id and p["id"] == cikan_id: continue
         if p["id"] in izinli_ids: continue
         vardiya = p.get("vardiya_tipi", "")
         bas_saat, bit_saat = VARDIYA_SAATLERI.get(vardiya, ("08:00","08:00"))
         bas_dk, bit_dk = saat_dakika(bas_saat), saat_dakika(bit_saat)
@@ -447,52 +449,86 @@ def init_db():
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
-    try: c.execute("ALTER TABLE personel ADD COLUMN yillik_izin_hakki INTEGER")
-    except: pass
+    def kolonlar(tablo: str) -> set[str]:
+        c.execute(f"PRAGMA table_info({tablo})")
+        return {row[1] for row in c.fetchall()}
+
+    def kolon_ekle(tablo: str, kolon: str, tip: str):
+        if kolon not in kolonlar(tablo):
+            c.execute(f"ALTER TABLE {tablo} ADD COLUMN {kolon} {tip}")
+
+    for kolon, tip in [("konum", "TEXT")]:
+        kolon_ekle("gemi", kolon, tip)
+
+    for kolon, tip in [
+        ("gemi_id_list", "TEXT"), ("makine_tipi_id_list", "TEXT"),
+        ("gemiden_cekilme", "INTEGER DEFAULT 0"), ("carkci_ile_sorun", "INTEGER DEFAULT 0"),
+        ("carkci_sorun_notu", "TEXT"), ("gemi_tutumu", "TEXT"),
+        ("izin_tercih_gunleri", "TEXT"), ("izin_saat_araligi", "TEXT"),
+        ("is_kalitesi", "INTEGER"), ("performans_notu", "TEXT"),
+        ("aktif", "INTEGER DEFAULT 1"), ("durum", "TEXT DEFAULT 'Gemide'"),
+        ("yillik_izin_hakki", "INTEGER"),
+    ]:
+        kolon_ekle("personel", kolon, tip)
+
+    kolon_ekle("izin", "gunler_json", "TEXT")
+
+    for kolon, tip in [("vardiya_gunleri", "TEXT"), ("puan_kirma", "INTEGER DEFAULT 0")]:
+        kolon_ekle("carkci", kolon, tip)
+
+    for kolon, tip in [("baslangic_saat", "TEXT DEFAULT '08:00'"), ("bitis_saat", "TEXT DEFAULT '08:00'")]:
+        kolon_ekle("vardiya_plan", kolon, tip)
+
+    try:
+        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vardiya_plan_tekil ON vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih)")
+    except sqlite3.IntegrityError:
+        # Eski veritabanında tekrar kayıt varsa uygulamanın açılmasını engelleme.
+        pass
+
     conn.commit()
     conn.close()
 
 def test_verisi_olustur():
     for t in ["vardiya_plan","personel_sertifika","performans_gecmis","carkci",
               "izin","personel","gemi_makine","makine_tipi","gemi","vardiya_takas"]:
         sql_run(f"DELETE FROM {t}")
     gemiler = [
         ("KABATEPE","G101","Tersane"),("M/T ATLANTIC","G202","Gecede"),
         ("M/V BOGAZICI","G303","Dışarıda"),("T/S CINAR","G404","Tersane"),
         ("M/V DENIZ YILDIZI","G505","Gecede"),
     ]
     for ad,kod,konum in gemiler:
         sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",(ad,kod,konum))
     gemi_ids = [r["id"] for r in sql_all("SELECT id FROM gemi")]
     for m in ["Dizel Motor","Kompresor","Pompa","Jenerator"]:
         sql_run("INSERT INTO makine_tipi(ad) VALUES(?)",(m,))
     makine_ids = [r["id"] for r in sql_all("SELECT id FROM makine_tipi")]
     for gid,mids in [
         (gemi_ids[0],[makine_ids[0],makine_ids[1]]),
         (gemi_ids[1],[makine_ids[1],makine_ids[2],makine_ids[3]]),
         (gemi_ids[2],[makine_ids[0],makine_ids[2]]),
         (gemi_ids[3],[makine_ids[3]]),
         (gemi_ids[4],[makine_ids[0],makine_ids[1],makine_ids[2],makine_ids[3]]),
     ]:
@@ -562,106 +598,110 @@ def _sayfa_yapboz():
             st.session_state.yapboz_tarih = st.session_state.yapboz_tarih + timedelta(days=7); st.rerun()
     gemiler    = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
     tum_mak    = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
     if not gemiler or not tum_mak:
         st.warning("Gemi ve makine ekleyin."); return
     col1, col2 = st.columns(2)
     with col1:
         if btn("🧹 Tüm Atamaları Temizle", key="yapboz_temizle", caption="Seçili tarihteki tüm vardiyaları siler", type="secondary"):
             sql_run("DELETE FROM vardiya_plan WHERE tarih=?", (sec_tarih.isoformat(),))
             st.toast("Tüm atamalar temizlendi!", icon="🧹"); st.rerun()
     with col2:
         if btn("🤖 Hepsini Otomatik Doldur", key="yapboz_otomatik", caption="Sistemin önerdiği en uygun personelle boşlukları doldurur"):
             with st.spinner("Otomatik dolduruluyor..."):
                 for gemi in gemiler:
                     for gm in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],)):
                         mak_id = gm["makine_tipi_id"]
                         if not vardiya_plani_kontrol(gemi["id"], mak_id, sec_tarih):
                             oneri = onerileri_hesapla(gemi["id"], mak_id, sec_tarih, limit=1)
                             if oneri and not oneri[0].get("zaten_atanmis"):
                                 b, e = VARDIYA_SAATLERI.get(oneri[0]["vardiya_tipi"], ("08:00","08:00"))
                                 try:
                                     sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                             (oneri[0]["id"],gemi["id"],mak_id,sec_tarih.isoformat(),b,e))
                                 except sqlite3.IntegrityError: pass
             st.toast("Tüm boş pozisyonlar dolduruldu!", icon="🤖"); st.rerun()
-    izinli = bugun_izinli_ids()
+    izinli = izinli_ids(sec_tarih)
     for gemi in gemiler:
         gemi_mak = sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?", (gemi["id"],))
         if not gemi_mak: continue
         g_mak_ids = {r["makine_tipi_id"] for r in gemi_mak}
         g_makineler = [m for m in tum_mak if m["id"] in g_mak_ids]
         atanan_count = sql_one("SELECT COUNT(*) AS c FROM vardiya_plan WHERE gemi_id=? AND tarih=?", (gemi["id"], sec_tarih.isoformat()))["c"]
         toplam_poz = len(g_makineler)
         doluluk_emoji = "✅" if atanan_count == toplam_poz else ("🟡" if atanan_count > 0 else "🔴")
         with st.expander(f"{doluluk_emoji} {gemi['ad']} — {atanan_count}/{toplam_poz} dolu", expanded=(atanan_count < toplam_poz)):
             cols = st.columns(max(len(g_makineler),1))
             for i, mak in enumerate(g_makineler):
                 with cols[i]:
                     mevcut = vardiya_plani_kontrol(gemi["id"], mak["id"], sec_tarih)
                     st.markdown(f"**{mak['ad']}**")
                     if mevcut:
                         p = sql_one("SELECT id,ad,soyad,vardiya_tipi,durum,is_kalitesi FROM personel WHERE id=?", (mevcut,))
                         if p:
                             renk = VARDIYA_RENKLERI.get(p["vardiya_tipi"],"#3a3a4e")
                             opacity = {1:0.5,2:0.6,3:0.75,4:0.9,5:1.0}.get(p["is_kalitesi"] or 3, 0.8)
                             st.markdown(f"<div style='background:{renk};padding:8px;border-radius:8px;color:white;text-align:center;font-weight:bold;opacity:{opacity}'>{p['ad']} {p['soyad']}<br>({p['vardiya_tipi']}) {p.get('durum','')}<br>⭐{p['is_kalitesi']}</div>", unsafe_allow_html=True)
                         cx, cd = st.columns(2)
                         with cx:
                             if btn("❌ Çıkar", key=f"c_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Bu personeli vardiyadan çıkarır"):
                                 sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi["id"],mak["id"],sec_tarih.isoformat()))
                                 st.toast("Personel çıkarıldı",icon="❌"); st.rerun()
                         with cd:
                             if btn("🔄 Değiştir", key=f"deg_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="Çıkarıp yeni öneri getirir"):
                                 sql_run("DELETE FROM vardiya_plan WHERE gemi_id=? AND makine_tipi_id=? AND tarih=?", (gemi["id"],mak["id"],sec_tarih.isoformat()))
                                 st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = onerileri_hesapla(gemi["id"],mak["id"],sec_tarih,limit=5)
                                 st.rerun()
                     else:
                         st.warning("⚠️ Boş")
                         hedef_gun = sec_tarih.weekday()
                         uygun = ["Seçiniz..."]
                         for p in sql_all("SELECT * FROM personel WHERE aktif=1 AND (vardiya_tipi='IZINCI' OR durum IN ('Gemide','İskelede'))"):
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
-                            uygun.append(f"{p['ad']} {p['soyad']} ({p.get('durum','')})")
+                            uygun.append(f"{p['ad']} {p['soyad']} (ID:{p['id']}) — {p.get('durum','')}")
                         if len(uygun) > 1:
                             sec = st.selectbox("Manuel Seç", uygun, key=f"s_{gemi['id']}_{mak['id']}_{sec_tarih}")
                             if sec != "Seçiniz...":
-                                pid_row = sql_one("SELECT id,vardiya_tipi FROM personel WHERE ad||' '||soyad=?", (sec.split(" (")[0],))
+                                try:
+                                    pid_sec = int(sec.split("ID:")[1].split(")")[0])
+                                except (IndexError, ValueError):
+                                    pid_sec = None
+                                pid_row = sql_one("SELECT id,vardiya_tipi FROM personel WHERE id=?", (pid_sec,)) if pid_sec else None
                                 if pid_row:
                                     b, e = VARDIYA_SAATLERI.get(pid_row["vardiya_tipi"],("08:00","08:00"))
                                     if iki_gun_ust_uste_mi(pid_row["id"],sec_tarih):
                                         st.warning("⚠️ Bu personel dün de çalıştı.")
                                     try:
                                         sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                                 (pid_row["id"],gemi["id"],mak["id"],sec_tarih.isoformat(),b,e))
                                         st.toast("Personel atandı!"); st.rerun()
                                     except sqlite3.IntegrityError:
                                         st.error("Bu atama zaten mevcut!")
                         else:
                             st.caption("Uygun personel yok.")
                         if btn("🔍 Öneri Al (5)", key=f"onerbtn_{gemi['id']}_{mak['id']}_{sec_tarih}", caption="En uygun 5 personeli listeler"):
                             st.session_state[f"oneriler_{gemi['id']}_{mak['id']}"] = onerileri_hesapla(gemi["id"],mak["id"],sec_tarih,limit=5)
                             st.rerun()
                         key_on = f"oneriler_{gemi['id']}_{mak['id']}"
                         if key_on in st.session_state and st.session_state[key_on]:
                             st.markdown("**Önerilen:**")
                             for o in st.session_state[key_on]:
                                 co1, co2 = st.columns([4,1])
                                 with co1:
                                     st.write(f"{o['ad']} {o['soyad']} ({o['vardiya_tipi']}) — {o['puan']}")
                                 with co2:
                                     if btn("✅ Ata", key=f"ata_{gemi['id']}_{mak['id']}_{o['id']}", caption="Bu kişiyi atar"):
                                         if o.get("zaten_atanmis"):
@@ -741,100 +781,110 @@ def _sayfa_takvim():
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
             while len(current_row) < 7: current_row.append("")
             satirlar.append(current_row)
         for satir in satirlar:
             cols = st.columns(7)
             for i, hucre in enumerate(satir):
                 if hucre: cols[i].markdown(hucre, unsafe_allow_html=True)
                 else: cols[i].markdown("<div style='padding:8px'></div>", unsafe_allow_html=True)
         st.markdown("**Renk:** 🟢 %80+ dolu &nbsp; 🟡 %40–80 &nbsp; 🔴 <%40 &nbsp; ⬛ Atama yok")
 
 def _sayfa_acil():
     st.subheader("⚡ Acil Panel")
     gem = sql_all("SELECT id,ad,konum FROM gemi ORDER BY ad")
     mak = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
+    if not gem or not mak:
+        st.warning("Acil paneli kullanmak için önce gemi ve makine tipi ekleyin.")
+        return
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
+                    personel_atandi = False
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
                                 try:
                                     sql_run("INSERT INTO vardiya_plan(personel_id,gemi_id,makine_tipi_id,tarih,baslangic_saat,bitis_saat) VALUES(?,?,?,?,?,?)",
                                             (p["id"],gid,mid,bugun.isoformat(),b,e))
                                     sql_run("UPDATE personel SET durum='Gemide' WHERE id=?",(p["id"],))
-                                    atanan+=1; break
+                                    atanan += 1
+                                    personel_atandi = True
+                                    break
                                 except sqlite3.IntegrityError: pass
-                        if atanan: break
+                        if personel_atandi: break
                 if atanan>0: st.toast(f"{atanan} personel dağıtıldı!"); st.rerun()
                 else: st.warning("Hiçbir personel yerleştirilemedi.")
     st.divider(); st.markdown("### 📞 Anlık İzin Yerine")
+    personel_opts = [f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")]
+    if not personel_opts:
+        st.info("Aktif personel yok.")
+        return
     c1,c2 = st.columns(2)
     with c1:
-        cik = st.selectbox("İzin İsteyen",[f"{p['ad']} {p['soyad']} (ID:{p['id']})" for p in sql_all("SELECT id,ad,soyad FROM personel WHERE aktif=1 ORDER BY ad")],key="acil_cik")
+        cik = st.selectbox("İzin İsteyen", personel_opts, key="acil_cik")
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
             sec_mak = st.multiselect("Gemideki Makineler",[m["id"] for m in makineler],
                                       format_func=lambda i:next((m["ad"] for m in makineler if m["id"]==i),""),key="gm_mak_sec")
@@ -846,86 +896,97 @@ def _sayfa_excel():
             else:
                 try:
                     sql_run("INSERT INTO gemi(ad,kod,konum) VALUES(?,?,?)",
                             (gad.strip().upper(),gkd.strip().upper() if gkd else None,None if kon=="Belirtilmedi" else kon))
                     ng = sql_one("SELECT id FROM gemi WHERE ad=?",(gad.strip().upper(),))
                     if ng and sec_mak:
                         for mid in sec_mak:
                             sql_run("INSERT INTO gemi_makine(gemi_id,makine_tipi_id) VALUES(?,?)",(ng["id"],mid))
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
     g_rows = sql_all("SELECT g.id,g.ad,g.kod,g.konum,COUNT(p.id) AS personel FROM gemi g LEFT JOIN personel p ON p.gemi_id=g.id GROUP BY g.id ORDER BY g.ad")
     if g_rows: st.dataframe(pd.DataFrame(g_rows),use_container_width=True)
     with st.expander("🔗 Gemi-Makine Eşleştirme"):
         gemiler  = sql_all("SELECT id,ad FROM gemi ORDER BY ad")
         makineler = sql_all("SELECT id,ad FROM makine_tipi ORDER BY ad")
-        sec_gemi = st.selectbox("Gemi",[g["id"] for g in gemiler],format_func=lambda i:next((g["ad"] for g in gemiler if g["id"]==i),""),key="gm_gemi")
+        if not gemiler or not makineler:
+            st.info("Eşleştirme için en az bir gemi ve bir makine tipi ekleyin.")
+            sec_gemi = None
+        else:
+            sec_gemi = st.selectbox("Gemi",[g["id"] for g in gemiler],format_func=lambda i:next((g["ad"] for g in gemiler if g["id"]==i),""),key="gm_gemi")
         if sec_gemi:
             mevcut_mak = [r["makine_tipi_id"] for r in sql_all("SELECT makine_tipi_id FROM gemi_makine WHERE gemi_id=?",(sec_gemi,))]
             sec_mak = st.multiselect("Makineler",[m["id"] for m in makineler],default=mevcut_mak,
                                       format_func=lambda i:next((m["ad"] for m in makineler if m["id"]==i),""),key="gm_mak")
             if btn("Güncelle",key="gm_guncelle",caption="Gemi-makine eşleştirmesini günceller"):
                 sql_run("DELETE FROM gemi_makine WHERE gemi_id=?",(sec_gemi,))
                 for mid in sec_mak:
                     sql_run("INSERT INTO gemi_makine(gemi_id,makine_tipi_id) VALUES(?,?)",(sec_gemi,mid))
                 st.toast("Güncellendi!"); st.rerun()
     c1, c2 = st.columns(2)
     with c1:
         with st.expander("✏️ Gemi Düzenle/Sil"):
             if g_rows:
                 gm = {f"{r['ad']} (ID:{r['id']})":r for r in g_rows}
                 gs = st.selectbox("Gemi",list(gm.keys()),key="gds"); gr = gm[gs]
                 na = st.text_input("Ad",gr["ad"] or "",key="gna"); nk = st.text_input("Kod",gr["kod"] or "",key="gnk")
                 nkon = st.selectbox("Konum",GEMI_KONUMLARI,index=GEMI_KONUMLARI.index(gr["konum"]) if gr["konum"] in GEMI_KONUMLARI else 3,key="gnkon")
                 if btn("Güncelle",key="bgd",caption="Geminin adını, kodunu veya konumunu günceller"):
                     if not na: st.error("Ad boş")
                     else:
                         sql_run("UPDATE gemi SET ad=?,kod=?,konum=? WHERE id=?",(na.strip().upper(),nk.strip().upper() if nk else None,nkon if nkon!="Belirtilmedi" else None,gr["id"]))
                         st.toast("Gemi güncellendi!"); st.rerun()
                 if btn("Sil",key="bgs",caption="Gemiyi tüm bağlantılarıyla siler"):
-                    bagli_personel = sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id=? OR gemi_id_list LIKE ?",(gr["id"],f'%{gr["id"]}%'))
-                    if bagli_personel and bagli_personel["c"] > 0:
+                    bagli_personeller = sql_all("SELECT id,gemi_id,gemi_id_list FROM personel")
+                    bagli_personel_var = any(
+                        r.get("gemi_id") == gr["id"] or gr["id"] in _id_listesi(r.get("gemi_id_list"))
+                        for r in bagli_personeller
+                    )
+                    if bagli_personel_var:
                         st.error("Bağlı personel var, önce onları başka gemiye atayın veya silin.")
                     else:
                         sql_run("DELETE FROM gemi_makine WHERE gemi_id=?",(gr["id"],))
                         sql_run("DELETE FROM carkci WHERE gemi_id=?",(gr["id"],))
                         sql_run("DELETE FROM vardiya_plan WHERE gemi_id=?",(gr["id"],))
                         sql_run("DELETE FROM gemi WHERE id=?",(gr["id"],))
                         st.toast("Gemi silindi!"); st.rerun()
     with c2:
         with st.expander("✏️ Makine Düzenle/Sil"):
             mr = sql_all("SELECT m.id,m.ad,COUNT(p.id) AS c FROM makine_tipi m LEFT JOIN personel p ON p.makine_tipi_id=m.id GROUP BY m.id ORDER BY m.ad")
+            personel_makine_listeleri = sql_all("SELECT makine_tipi_id_list FROM personel")
+            for r in mr:
+                r["c"] += sum(1 for p in personel_makine_listeleri if r["id"] in _id_listesi(p.get("makine_tipi_id_list")))
             if mr:
                 mm = {f"{r['ad']} (ID:{r['id']})":r for r in mr}
                 ms = st.selectbox("Makine",list(mm.keys()),key="mds"); mrow = mm[ms]
                 nm = st.text_input("Ad",mrow["ad"] or "",key="mna")
                 if btn("Güncelle",key="bmd",caption="Makine adını günceller"):
                     if not nm: st.error("Ad boş")
                     else: sql_run("UPDATE makine_tipi SET ad=? WHERE id=?",(nm.strip().upper(),mrow["id"])); st.toast("Makine güncellendi!"); st.rerun()
                 if btn("Sil",key="bms",caption="Makineyi siler (bağlı personel varsa izin vermez)"):
                     if mrow["c"]>0: st.error("Bağlı personel var")
                     else: sql_run("DELETE FROM gemi_makine WHERE makine_tipi_id=?",(mrow["id"],)); sql_run("DELETE FROM vardiya_plan WHERE makine_tipi_id=?",(mrow["id"],)); sql_run("DELETE FROM makine_tipi WHERE id=?",(mrow["id"],)); st.toast("Makine silindi!"); st.rerun()
 
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
@@ -1075,51 +1136,51 @@ def _sayfa_oneri():
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
                                         try:
                                             sql_run("INSERT INTO vardiya_plan VALUES(NULL,?,?,?,?,?,?)",(on[0]["id"],g,m,d.isoformat(),b,e))
                                             kul[on[0]["id"]] = kul.get(on[0]["id"],0)+1; top+=1
                                         except sqlite3.IntegrityError: pass
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
-    izinli = bugun_izinli_ids()
+    izinli = izinli_ids(ht)
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
         st.warning("Gemi/personel yok"); return
     c1, c2 = st.columns(2)
     with c1:
         ad = st.text_input("Ad", key="cka"); soyad = st.text_input("Soyad", key="cks")
         gid = st.selectbox("Gemi", [r["id"] for r in gem], format_func=lambda i: next(r["ad"] for r in gem if r["id"] == i), key="ckg")
         cvt = st.selectbox("Vardiya", VARDIYA_TIPLERI, key="ckv"); cg = st.multiselect("Günler", GUNLER_TR, key="ckgun")
     with c2:
         yop = [("(Seçilmedi)", None)] + [(f"{p['ad']} {p['soyad']}", p["id"]) for p in yag]
         ys = st.selectbox("Sorunlu Yağcı", yop, format_func=lambda x: x[0], key="cky")
         sorun = st.text_area("Sorun / Açıklama", key="ckso"); vn = st.text_input("Vardiya Notu", key="ckvn")
         pk = st.slider("Puan Kırma", 0, 5, 0, key="ckp")
 
EOF
)
