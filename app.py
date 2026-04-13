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
from src.excel_yukle import ornek_sablon, yukle_gemiler_ve_makineler
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
    st.subheader("Excel — gemi ve makine tipleri")
    st.caption("Excel dosyanızı gönderdiğinizde kolon eşlemesi `src/excel_yukle.py` içinde güncellenebilir.")
    f = st.file_uploader("Excel yükle (.xlsx)", type=["xlsx"])
    if f and st.button("Yükle ve içe aktar"):
        g, m = yukle_gemiler_ve_makineler(f)
        st.success(f"İşlendi (satır sayıları yaklaşık): Gemi {g}, Makine {m}")
    st.download_button("Örnek şablon indir", data=ornek_sablon(), file_name="ordino_sablon.xlsx")


def _sayfa_personel() -> None:
    st.subheader("Personel")
    rows = db.sql_all(
        """
        SELECT p.id, p.ad, p.soyad, g.ad AS gemi, m.ad AS makine, p.vardiya_tipi, p.vardiya_gunleri,
               p.gemiden_cekilme, p.carkci_ile_sorun
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
        st.warning("Önce Excel ile en az bir gemi ve makine tipi ekleyin.")
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
        if st.button("Personel kaydet"):
            if not ad or not soyad:
                st.error("Ad ve soyad zorunlu.")
            else:
                db.sql_run(
                    """INSERT INTO personel(ad, soyad, gemi_id, makine_tipi_id, vardiya_tipi, vardiya_gunleri)
                       VALUES (?,?,?,?,?,?)""",
                    (ad, soyad, int(gid), int(mid), vt, gun_json),
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
        html, body, [class*="css"] { font-size: 16px; }
        .stTabs [role="tablist"] { overflow-x: auto; white-space: nowrap; }
        .stTabs [role="tab"] { padding: 0.5rem 0.8rem; }
        .stButton button { width: 100%; min-height: 44px; }
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

### Excel
Göndereceğiniz dosyada sayfa adları **Gemi** ve **Makine** ise otomatik içe aktarılır; değilse `src/excel_yukle.py` güncellenir.
            """
        )


main()
d