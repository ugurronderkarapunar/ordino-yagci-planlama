# ⚓ Ordino Yağcı Planlaması v8.0

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28%2B-FF4B4B?logo=streamlit)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite)
![Lisans](https://img.shields.io/badge/Lisans-MIT-green)
![Version](https://img.shields.io/badge/Sürüm-8.0-orange)

> **Gemi personeli için akıllı vardiya planlama, takip ve analiz platformu.**  
> Çarkçılar, yöneticiler ve planlamacılar için özel olarak geliştirilmiş, modern arayüzüyle vardiya yönetimini kolaylaştırır.

---

## 🧭 İçindekiler

- [Özellikler](#-özellikler)
- [v8.0 ile Gelen Yenilikler](#-v80-ile-gelen-yenilikler)
- [Ekran Görüntüleri](#-ekran-görüntüleri)
- [Kurulum](#-kurulum)
- [Kullanım](#-kullanım)
- [Yapılandırma](#-yapılandırma)
- [Veritabanı Şeması](#-veritabanı-şeması)
- [Proje Yapısı](#-proje-yapısı)
- [Katkıda Bulunma](#-katkıda-bulunma)
- [Lisans](#-lisans)

---

## ✨ Özellikler

- **İnteraktif Yapboz Paneli**  
  Gemi ve makine bazında sürükle‑bırak mantığıyla günlük vardiya atamaları.  
  Gemi doluluk özeti, anlık öneri motoru, manuel atama ve toplu temizleme.

- **Akıllı Öneri Motoru**  
  Personel yetkinlikleri, çalışma saatleri, dinlenme süreleri, NLP notları ve iş kalitesini değerlendirerek en uygun adayı önerir.  
  Özel puanlama algoritması sayesinde adil dağıtım.

- **Haftalık / Aylık Takvim Görünümü**  
  7 günlük grid ve aylık ısı haritası ile planı toplu görüntüleyin.  
  Günlük doluluk oranları renk kodlu olarak gösterilir.

- **Vardiya Takas Talepleri**  
  Personeller kendi aralarında değişiklik talep edebilir, yönetici onayıyla vardiyalar otomatik değişir.

- **Kapsamlı Analitik Panoları**
  - Personel yük dengesi grafiği (kim ne kadar çalışıyor?)
  - Gemi doluluk oranı zaman serisi
  - Fazla mesai takip ve uyarı sistemi
  - Üst üste çalışma / çakışma raporu

- **Esnek Konfigürasyon**  
  Minimum dinlenme süresi, haftalık çalışma limiti, yıllık izin hakkı gibi kuralları ayarlar sayfasından canlı olarak değiştirin.

- **Mobil Uyumlu Arayüz**  
  Telefon ve tablette rahat kullanım için duyarlı tasarım.

- **Veri Yönetimi**  
  SQLite veritabanı, yedekleme, dışa aktarma (PDF, .ics, Excel) ve audit log desteği.

---

## 🚀 v8.0 ile Gelen Yenilikler

- **Performans**: N+1 sorgu problemi giderildi, tüm sorgular JOIN ile birleştirildi. Öneri motoru `st.cache_data` ile önbelleğe alındı.
- **Yeni Takvim Sekmesi**: Haftalık detay grid ve aylık doluluk ısı haritası.
- **Analitik Sekmesi**: Yük dengesi, gemi doluluk, fazla mesai, çakışma raporu.
- **Takas Talebi**: İki personel arasında vardiya değişimi için onay mekanizması.
- **Mobil CSS İyileştirmeleri**: Butonlar ve sütunlar küçük ekranlarda üst üste binmez.
- **Form Temizleme**: Tüm formlara `clear_on_submit=True` eklendi.
- **Arayüz**: Yapboz sayfası gemi bazlı **accordion** yapısına geçti, doluluk emoji özeti eklendi.

---

## 📸 Ekran Görüntüleri

> *(Uygulama içinden alınmış örnek görseller)*

| Yapboz Paneli | Haftalık Takvim | Analitik Paneli |
|---------------|----------------|-----------------|
| ![Yapboz](docs/yapboz.png) | ![Takvim](docs/takvim.png) | ![Analitik](docs/analitik.png) |

*(Görseller `docs/` klasörüne eklenebilir.)*

---

## ⚙️ Kurulum

1. **Depoyu klonlayın**
   ```bash
   git clone https://github.com/kullanici/ordino-yagci.git
   cd ordino-yagci
