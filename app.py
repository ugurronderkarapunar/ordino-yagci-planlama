"""
Ordino Yağcı Planlaması — Streamlit web uygulaması.
Çalıştır: proje kökünde `streamlit run app.py`
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src import database as db
from src.config import get_admin_credentials
from src.oneri_motoru import to_dict_rows, onerileri_hesapla
from src.vardiya_kurallari import gun_sayisi, izin_pzt_3gun

GUNLER_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _login_form() -> None:
    st.title("Ordino — Yağcı planlaması")
    u_def, p_def = get_admin_credentials()
    with st.form("login"):
        uid = st.text_input("Kullanıcı ID")
        pwd = st.text_input("Şifre", type="password")
        ok = st.form_submit_button("Giriş")
    if ok:
        if uid == u_def and pwd == p_def:
            st.session_state["ordino_auth"] = True
            st.rerun()
        else:
            st.error("Hatalı kullanıcı veya şifre.")


def _logout() -> None:
    if st.sidebar.button("Çıkış"):
        st.session_state.pop("ordino_auth", None)
        st.rerun()


def _sayfa_excel() -> None:
    st.subheader("Tanımlar — gemi ve makine tipleri")
    st.caption("Bu alandan tüm gemi ve makine girişlerini elle yapabilirsiniz.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Gemi ekle")
        with st.form("gemi_ekle_form", clear_on_submit=True):
            gad = st.text_input("Gemi adı")
            gkod = st.text_input("Gemi kodu (opsiyonel)")
            gok = st.form_submit_button("Gemi kaydet")
        if gok:
            if not gad.strip():
                st.error("Gemi adı zorunlu.")
            else:
                db.sql_run("INSERT INTO gemi(ad, kod) VALUES (?, ?)", (gad.strip(), gkod.strip() or None))
                st.success("Gemi kaydedildi.")
                st.rerun()

    with c2:
        st.markdown("#### Makine tipi ekle")
        with st.form("makine_ekle_form", clear_on_submit=True):
            mad = st.text_input("Makine tipi adı")
            mok = st.form_submit_button("Makine tipi kaydet")
        if mok:
            if not mad.strip():
                st.error("Makine tipi adı zorunlu.")
            else:
                db.sql_run("INSERT INTO makine_tipi(ad) VALUES (?)", (mad.strip(),))
                st.success("Makine tipi kaydedildi.")
                st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı gemiler")
    g_rows = db.sql_all(
        """
        SELECT g.id, g.ad, g.kod, COUNT(p.id) AS personel_sayisi
        FROM gemi g
        LEFT JOIN personel p ON p.gemi_id = g.id
        GROUP BY g.id, g.ad, g.kod
        ORDER BY g.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in g_rows]), use_container_width=True)
    gid_sil = st.number_input("Silinecek gemi ID", min_value=1, step=1, key="gid_sil")
    if st.button("Gemiyi sil", type="secondary"):
        bagli = db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE gemi_id = ?", (int(gid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu gemiye bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            db.sql_run("DELETE FROM gemi WHERE id = ?", (int(gid_sil),))
            st.success("Gemi silindi.")
            st.rerun()

    st.divider()
    st.markdown("#### Kayıtlı makine tipleri")
    m_rows = db.sql_all(
        """
        SELECT m.id, m.ad, COUNT(p.id) AS personel_sayisi
        FROM makine_tipi m
        LEFT JOIN personel p ON p.makine_tipi_id = m.id
        GROUP BY m.id, m.ad
        ORDER BY m.ad
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in m_rows]), use_container_width=True)
    mid_sil = st.number_input("Silinecek makine tipi ID", min_value=1, step=1, key="mid_sil")
    if st.button("Makine tipini sil", type="secondary"):
        bagli = db.sql_one("SELECT COUNT(*) AS c FROM personel WHERE makine_tipi_id = ?", (int(mid_sil),))
        if bagli and int(bagli["c"]) > 0:
            st.error("Bu makine tipine bağlı personel var. Önce personeli güncelleyin/silin.")
        else:
            db.sql_run("DELETE FROM makine_tipi WHERE id = ?", (int(mid_sil),))
            st.success("Makine tipi silindi.")
            st.rerun()


def _sayfa_personel() -> None:
    st.subheader("Personel")
    rows = db.sql_all(
        """
        SELECT p.id, p.ad, p.soyad, g.ad AS gemi, m.ad AS makine, p.vardiya_tipi, p.vardiya_gunleri,
               p.gemiden_cekilme, p.carkci_ile_sorun, p.gemi_tutumu, p.izin_tercih_gunleri,
               p.izin_saat_araligi, p.is_kalitesi, p.performans_notu
        FROM personel p
        LEFT JOIN gemi g ON g.id = p.gemi_id
        LEFT JOIN makine_tipi m ON m.id = p.makine_tipi_id
        ORDER BY p.id DESC
        """
    )
    st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

    gemiler = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = db.sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Önce Tanımlar sekmesinden en az bir gemi ve makine tipi ekleyin.")
        return

    with st.expander("Yeni personel"):
        c1, c2 = st.columns(2)
        ad = c1.text_input("Ad")
        soyad = c2.text_input("Soyad")
        gid = st.selectbox("Gemi", options=[r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i))
        mid = st.selectbox("Makine tipi", options=[r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i))
        vt = st.selectbox("Vardiya tipi", ["SABIT", "GRUPCU", "8_5"])
        secilen = st.multiselect("Vardiya günleri (8/5 için boş bırakılabilir)", GUNLER_TR, default=["Pazartesi", "Çarşamba", "Cuma"])
        gun_json = json.dumps([GUNLER_TR.index(x) for x in secilen]) if secilen else "[]"
        st.markdown("##### Personel profil detayları")
        gemi_tutumu = st.selectbox("Gemi içi tutum", ["Mükemmel", "İyi", "Orta", "Gelişmeli"])
        izin_gunleri = st.multiselect("Tercih edilen izin günleri", GUNLER_TR)
        izin_gun_json = json.dumps([GUNLER_TR.index(x) for x in izin_gunleri]) if izin_gunleri else "[]"
        c3, c4 = st.columns(2)
        izin_bas = c3.time_input("Tercih edilen izin başlangıç saati")
        izin_bit = c4.time_input("Tercih edilen izin bitiş saati")
        is_kalitesi = st.slider("İş kalitesi puanı", min_value=1, max_value=5, value=4)
        performans_notu = st.text_area("Performans notu", placeholder="Örn: Acil durumlarda hızlı reaksiyon, ekip uyumu yüksek.")
        if st.button("Personel kaydet"):
            if not ad or not soyad:
                st.error("Ad ve soyad zorunlu.")
            else:
                db.sql_run(
                    """INSERT INTO personel(
                           ad, soyad, gemi_id, makine_tipi_id, vardiya_tipi, vardiya_gunleri,
                           gemi_tutumu, izin_tercih_gunleri, izin_saat_araligi, is_kalitesi, performans_notu
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ad,
                        soyad,
                        int(gid),
                        int(mid),
                        vt,
                        gun_json,
                        gemi_tutumu,
                        izin_gun_json,
                        f"{izin_bas.strftime('%H:%M')} - {izin_bit.strftime('%H:%M')}",
                        int(is_kalitesi),
                        performans_notu.strip() or None,
                    ),
                )
                st.success("Kaydedildi.")
                st.rerun()

    with st.expander("Personel sil / bayrak"):
        pid = st.number_input("Personel ID", min_value=1, step=1)
        if st.button("Sil", type="primary"):
            db.sql_run("DELETE FROM personel WHERE id = ?", (int(pid),))
            st.success("Silindi.")
            st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("Gemiden çekildi işaretle"):
            db.sql_run("UPDATE personel SET gemiden_cekilme = 1 WHERE id = ?", (int(pid),))
            st.rerun()
        if c2.button("Çarkçı sorunu temizle"):
            db.sql_run("UPDATE personel SET carkci_ile_sorun = 0 WHERE id = ?", (int(pid),))
            st.rerun()


def _sayfa_izin() -> None:
    st.subheader("İzin takibi")
    plist = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not plist:
        st.info("Önce personel ekleyin.")
        return
    pid = st.selectbox("Personel", [r["id"] for r in plist], format_func=lambda i: f"{next(r['ad'] for r in plist if r['id']==i)} {next(r['soyad'] for r in plist if r['id']==i)}")
    c1, c2 = st.columns(2)
    bas = c1.date_input("Başlangıç", value=date.today())
    bit = c2.date_input("Bitiş", value=date.today())
    gun = gun_sayisi(bas, bit)
    st.write(f"Hesaplanan gün sayısı: **{gun}**")
    ucb = st.checkbox("Pazartesi vardiya günü izni → 3 gün (Pzt–Sal–Çar) uygula")
    if ucb and bas.weekday() == 0:
        bas, bit = izin_pzt_3gun(bas)
        st.info(f"Tarihler güncellendi: {bas} → {bit}")
        gun = gun_sayisi(bas, bit)
    notlar = st.text_input("Not (isteğe bağlı)")
    if st.button("İzin kaydet"):
        db.sql_run(
            "INSERT INTO izin(personel_id, baslangic, bitis, gun_sayisi, notlar) VALUES (?,?,?,?,?)",
            (int(pid), bas.isoformat(), bit.isoformat(), int(gun), notlar or None),
        )
        st.success("İzin kaydedildi.")
        st.rerun()
    st.divider()
    st.write("Kayıtlı izinler")
    iz = db.sql_all(
        """SELECT i.id, p.ad, p.soyad, i.baslangic, i.bitis, i.gun_sayisi, i.notlar
           FROM izin i JOIN personel p ON p.id = i.personel_id ORDER BY i.baslangic DESC LIMIT 50"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in iz]), use_container_width=True)


def _sayfa_carkci() -> None:
    st.subheader("Çarkçı kayıtları")
    gemiler = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    yagcilar = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not yagcilar:
        st.warning("Gemi ve personel gerekli.")
        return
    ad = st.text_input("Çarkçı adı")
    soyad = st.text_input("Çarkçı soyadı")
    gid = st.selectbox("Gemi", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i))
    yid = st.selectbox("Sorunlu yağcı (personel)", [r["id"] for r in yagcilar], format_func=lambda i: f"{next(r['ad'] for r in yagcilar if r['id']==i)} {next(r['soyad'] for r in yagcilar if r['id']==i)}")
    sorun = st.text_area("Sorun / açıklama")
    vn = st.text_input("Çarkçı vardiya notu")
    if st.button("Çarkçı kaydı oluştur ve yağcıyı öneri dışı bırak"):
        db.sql_run(
            """INSERT INTO carkci(ad, soyad, gemi_id, problemli_yagci_id, sorun_metni, vardiya_notu)
               VALUES (?,?,?,?,?,?)""",
            (ad, soyad, int(gid), int(yid), sorun, vn),
        )
        db.sql_run("UPDATE personel SET carkci_ile_sorun = 1 WHERE id = ?", (int(yid),))
        st.success("Kaydedildi; yağcı öneri motorunda elendi.")
        st.rerun()
    st.divider()
    cr = db.sql_all(
        """SELECT c.id, c.ad, c.soyad, g.ad AS gemi, p.ad || ' ' || p.soyad AS yagci, c.sorun_metni
           FROM carkci c
           LEFT JOIN gemi g ON g.id = c.gemi_id
           LEFT JOIN personel p ON p.id = c.problemli_yagci_id
           ORDER BY c.id DESC LIMIT 30"""
    )
    st.dataframe(pd.DataFrame([dict(r) for r in cr]), use_container_width=True)


def _sayfa_oneri() -> None:
    st.subheader("Yağcı öneri (en fazla 5, skor 5 en iyi)")
    gemiler = db.sql_all("SELECT id, ad FROM gemi ORDER BY ad")
    makineler = db.sql_all("SELECT id, ad FROM makine_tipi ORDER BY ad")
    plist = db.sql_all("SELECT id, ad, soyad FROM personel WHERE aktif = 1 ORDER BY ad")
    if not gemiler or not makineler:
        st.warning("Gemi ve makine tipi gerekli.")
        return
    gid = st.selectbox("Gemi", [r["id"] for r in gemiler], format_func=lambda i: next(r["ad"] for r in gemiler if r["id"] == i), key="og")
    mid = st.selectbox("Makine tipi", [r["id"] for r in makineler], format_func=lambda i: next(r["ad"] for r in makineler if r["id"] == i), key="om")
    ht = st.date_input("Hedef tarih", value=date.today())
    cik_labels = ["(Çıkan yağcı yok)"] + [f"{r['ad']} {r['soyad']}" for r in plist]
    cik_sel = st.selectbox("Çıkan yağcı", cik_labels)
    cik = None if cik_sel == "(Çıkan yağcı yok)" else next(int(r["id"]) for r in plist if f"{r['ad']} {r['soyad']}" == cik_sel)
    if st.button("Önerileri hesapla"):
        out = onerileri_hesapla(int(gid), int(mid), ht, cik, limit=5)
        rows = to_dict_rows(out)
        if not rows:
            st.warning("Uygun aday bulunamadı (kurallar veya veri eksik).")
        else:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            for r in rows:
                if r.get("uyari_8_5"):
                    st.warning(f"8/5 uyarısı: {r['ad_soyad']}")


def main() -> None:
    st.set_page_config(
        page_title="Ordino Yağcı Planlaması",
        page_icon="⚓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .stApp {
          background-image:
            linear-gradient(rgba(22, 15, 8, 0.32), rgba(22, 15, 8, 0.32)),
            linear-gradient(160deg, rgba(255, 247, 239, 0.78) 0%, rgba(255, 224, 191, 0.72) 45%, rgba(255, 210, 161, 0.72) 100%),
            url("https://commons.wikimedia.org/wiki/Special:FilePath/Ferry_%C5%9EH-DURUSU_approaching_Yenikap%C4%B1_Ferry_Terminal,_Istanbul,_March_2024_01.jpg");
          background-size: cover;
          background-repeat: no-repeat;
          background-position: center center;
          background-attachment: fixed;
          color: #2f251b;
        }
        [data-testid="stAppViewContainer"] .main .block-container {
          background: rgba(255, 255, 255, 0.96);
          border-radius: 14px;
          padding: 1rem 1rem 1.2rem;
          border: 1px solid #ffd2a1;
          box-shadow: 0 12px 34px rgba(28, 17, 8, 0.22);
        }
        h1, h2, h3, h4, p, li, label, span, div {
          color: #2f251b !important;
        }
        [data-testid="stForm"] {
          background: #fffaf4;
          border: 1px solid #ffd8b0;
          border-radius: 12px;
          padding: 0.9rem 1rem 0.4rem;
        }
        [data-testid="stExpander"] {
          border: 1px solid #ffd8b0;
          border-radius: 12px;
          background: #fffdf9;
        }
        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        .stDateInput > div > div {
          background: #fff8f0;
          border-color: #f4bf8a !important;
          border-radius: 10px;
        }
        [data-baseweb="input"] input,
        [data-baseweb="select"] input {
          color: #2f251b !important;
        }
        html, body, [class*="css"] { font-size: 16px; }
        .stTabs [role="tablist"] {
          overflow-x: auto;
          white-space: nowrap;
          gap: 0.45rem;
          padding-bottom: 0.35rem;
        }
        .stTabs [role="tab"] {
          padding: 0.55rem 0.95rem;
          background: #fff5ea;
          border: 1px solid #ffcb97;
          border-radius: 8px;
          color: #5a320a;
          font-weight: 600;
        }
        .stTabs [aria-selected="true"] {
          background: #f3831f !important;
          color: #ffffff !important;
          border-color: #f3831f !important;
          box-shadow: 0 4px 12px rgba(243, 131, 31, 0.35);
        }
        .stButton button {
          width: 100%;
          min-height: 44px;
          background: #f3831f;
          color: #ffffff;
          border: 1px solid #d66d12;
          border-radius: 10px;
          font-weight: 600;
          transition: all 0.15s ease-in-out;
        }
        .stButton button:hover {
          background: #d96f14;
          border-color: #bf5f10;
          color: #ffffff;
          transform: translateY(-1px);
        }
        .stDataFrame, .stTable {
          background: #ffffff;
          border-radius: 10px;
          border: 1px solid #f7d7b4;
        }
        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, #fff3e3 0%, #ffe7cc 100%);
          border-left: 1px solid #ffd1a0;
        }
        .stAlert {
          border-radius: 10px;
        }
        @media (max-width: 768px) {
          .block-container { padding: 0.8rem 0.7rem 1.2rem; }
          .stDataFrame { font-size: 13px; }
          h1, h2, h3 { line-height: 1.2; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    db.init_db()
    if not st.session_state.get("ordino_auth"):
        _login_form()
        return
    _logout()
    st.sidebar.caption("Şifreyi değiştirmek için yerelde `.env` veya Streamlit Cloud’da Secrets içinde `ORDINO_ADMIN_PASSWORD` düzenleyin.")
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["Excel", "Personel", "İzin", "Çarkçı", "Öneri", "Bilgi"]
    )
    with tab1:
        _sayfa_excel()
    with tab2:
        _sayfa_personel()
    with tab3:
        _sayfa_izin()
    with tab4:
        _sayfa_carkci()
    with tab5:
        _sayfa_oneri()
    with tab6:
        st.markdown(
            """
### Kalıcı web adresi ve güvenlik
- **Google Colab** tek başına kalıcı güvenli kurumsal site **değildir**; oturum bitince kapanır.
- **Önerilen:** Bu projeyi GitHub’a koyup [Streamlit Community Cloud](https://streamlit.io/cloud) ile yayınlayın; `Secrets` içine şifre koyun → size özel **https://....streamlit.app** adresi verilir, HTTPS ve her PC’den erişim.
- **Colab kullanımı:** Geliştirme / eğitim için not defteri ile paket kurulumu yapılabilir; üretim verisini Colab’da bırakmayın.

### Veri girisi
Gemi, makine tipi, personel ve izin verilerini uygulama icinden manuel olarak ekleyebilirsiniz.
            """
        )


main()