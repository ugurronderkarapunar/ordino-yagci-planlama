# ⚓ Ordino Yağcı Planlaması

> **Gemi personeli (yağcı) vardiyalarını yönetmek için geliştirilmiş, NLP destekli akıllı öneri motoruna ve modern kullanıcı arayüzüne sahip bir Streamlit uygulaması.**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31%2B-FF4B4B?logo=streamlit)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

---

## 📋 İçindekiler

- [Ekran Görüntüsü ve Öne Çıkanlar](#-ekran-görüntüsü-ve-öne-çıkanlar)
- [Sekmeler ve Genel Yapı](#-sekmeler-ve-genel-yapı)
- [🧩 Yapboz](#-yapboz-i̇nteraktif-vardiya-tahtası)
- [⚡ Acil Panel](#-acil-panel)
- [🚢 Gemiler & Makine](#-gemiler--makine-yönetimi)
- [👷 Personel & İzin](#-personel--i̇zin)
- [✦ Öneri & Plan](#-öneri--plan)
- [📊 Bilgi](#-bilgi)
- [🧠 Öneri Motoru (Arka Plan)](#-öneri-motoru-arka-plan)
- [🎨 UI/UX Özellikleri](#-uiux-özellikleri)
- [📈 Uygulama Akış Şeması](#-uygulama-akış-şeması)

---

## ✨ Öne Çıkanlar

| Özellik | Açıklama |
|---------|----------|
| 🧩 **Yapboz** | Günlük vardiya tahtasını renkli kutularda görsel olarak yönetir, tek tıkla personel atama/çıkarma yapılır |
| ⚡ **Acil Panel** | "Kim boşta?", "İskelede kim var?", "Aniden izin isteyen oldu, yerine kimi koyalım?" sorularına anında cevap |
| 🧠 **NLP Destekli Öneri Motoru** | Personel yorumlarını, çarkçı notlarını analiz eder; iş kalitesi, dinlenme süresi, rotasyon gibi 15+ kritere göre puanlama yapar |
| 🎨 **Modern UI/UX** | Koyu/aydınlık tema, sidebar navigasyon, toast bildirimleri, spinner animasyonları, özel buton stilleri, dashboard kartları |
| 📅 **Saatli Vardiya Planı** | Her vardiya tipi için tanımlı çalışma saatleri (SABİT 08-08, TERSANE 08-17, GECE 20-08) ile saat çakışması kontrolü |
| 🔄 **Adil Dağıtım** | Toplu planlamada en az kullanılan personeli tercih eden sayaç sistemi |
| 📱 **Mobil Uyum** | Telefonda rahat kullanım için optimize edilmiş arayüz, ana ekrana kısayol eklenebilir |
| 💾 **Veri Güvenliği** | Tüm veriler `ordino.db` dosyasında kalıcıdır; manuel yedekleme ve DB indirme butonları mevcuttur |

---

## 🧩 Sekmeler ve Genel Yapı

Uygulama **6 ana sekmeden** oluşur. Her sekme belirli bir işlevi yerine getirir.

| Sekme | Amaç |
|-------|------|
| 🧩 **Yapboz** | Günlük vardiya tahtasını görsel olarak yönetme |
| ⚡ **Acil** | Anlık ihtiyaçlar için hızlı personel bulma |
| 🚢 **Gemiler** | Gemi ve makine tipi kayıtlarını yönetme |
| 👷 **Personel & İzin** | Personel kaydı, düzenleme, izin takibi |
| ✦ **Öneri** | Vardiya planlama, öneri motoru, çarkçı kayıtları |
| 📊 **Bilgi** | Raporlar, istatistikler, yedekleme |

> **Sidebar:** Sol kenar çubuğunda tema değiştirme, mobil kullanım ipuçları ve hızlı erişim linkleri bulunur.

---

## 🧩 Yapboz (İnteraktif Vardiya Tahtası)

**Amaç:** Seçilen bir tarih için tüm gemi ve makine tiplerinde kimin görevli olduğunu renkli kutularda gösterir. Boş pozisyonlara hızlıca personel atamanızı sağlar.

- 🎨 **Renkli hücreler:** Her vardiya tipi farklı bir renkle gösterilir *(SABİT mavi, GRUPÇU yeşil, İZİNCİ turuncu, TERSANE kırmızı, 8_5 mor, GECE turkuaz)*. İş kalitesine göre hücre opaklığı değişir.
- 🔍 **Personel seçimi:** Boş bir hücreye tıkladığınızda, yalnızca o pozisyona **uygun** personeller listelenir *(izin, çakışma, sertifika, gemi yetkisi, çarkçı sorunu, saat çakışması gibi tüm kontroller yapılır)*.
- ❌ **Çıkar:** Atanmış personeli vardiyadan çıkarmak için kırmızı buton. Toast bildirimi ile onaylanır.
- 🧹 **Günü Temizle:** Seçilen tarihteki tüm atamaları tek tuşla siler.
- 📅 **Bugün:** Tarih seçiciyi bugüne hızlıca döndürür.
- 🤖 **Hepsini Otomatik Doldur:** Boş tüm pozisyonları, öneri motorunu kullanarak tek tıkla doldurur. Opsiyonel checkbox ile açılıp kapatılabilir. Spinner ile işlem süresi gösterilir.

---

## ⚡ Acil Panel

**Amaç:** Günlük operasyonda anlık kararlar vermenizi sağlar. *"Kim boşta?", "İskelede kim var?", "Aniden izin isteyen oldu, yerine kimi koyalım?"* gibi sorulara anında cevap verir.

- 👤 **Boştakiler:** Bugün hiçbir vardiyası olmayan aktif personeli, yetkili olduğu gemi/makinelerle birlikte listeler.
- 🏝️ **İskelede Bekleyenler:** Şu an iskelede olan personelin listesi.
- 🏗️ **Tersaneye Uygunlar:** Tersane konumundaki gemilere atanabilecek uygun personeli listeler.
- 📞 **Anlık İzin Yerine:** Bir personel aniden izin istediğinde, yerine önerilecek en uygun **5 adayı** sıralar. NLP analizi, dinlenme ihlali, peş peşe çalışma gibi uyarıları da gösterir.
- 🌐 **Tüm Boşluklar:** Tüm gemi/makine kombinasyonları için boş pozisyonları ve önerilen personeli gösterir.
- 🏝️ **İskeleye Çıkar:** Seçilen personeli tek tuşla "İskelede" durumuna alır.
- 🚀 **İskeledekileri Akıllı Dağıt:** İskelede bekleyen tüm personeli, **öneri motorunu kullanarak** en uygun boş pozisyonlara otomatik yerleştirir. Spinner ile işlem süresi gösterilir.
- 📅 **Dün Kim Çalıştı?:** Seçilen gemi/makine için dünkü vardiyadaki personeli ve saatlerini sorgular.

---

## 🚢 Gemiler & Makine Yönetimi

**Amaç:** Sistemdeki gemi ve makine tipi kayıtlarını tutar.

- ➕ **Yeni gemi/makine ekleme:** Aynı form üzerinden hem gemi hem makine tipi eklenir. Toast ile onaylanır.
- 📍 **Konum bilgisi:** Her geminin *Tersane, Dışarıda, Gecede, Belirtilmedi* konumlarından biri seçilir. Bu bilgi öneri motorunda kullanılır.
- 📤 **Excel ile toplu ekleme:** *Gemi Adı* ve *Makine Tipi* sütunları içeren bir Excel dosyasıyla toplu kayıt eklenebilir.
- 👥 **Gemi Bazlı Personel Listesi:** Seçilen gemide çalışan tüm personeli listeleyen genişletilebilir bir bölüm.
- ✏️ **Düzenleme ve silme:** Gemi ve makine tipleri ayrı ayrı düzenlenebilir veya silinebilir. *Bağlı personel varsa silmeye izin verilmez.* Toast ile onaylanır.

---

## 👷 Personel & İzin

**Amaç:** Tüm personel kayıtlarının ve izinlerin yönetildiği merkezdir.

### Personel Yönetimi

- 🔍 **Arama:** İsim, soyisim, vardiya tipi, gemi ve durum alanlarında anlık metin araması yapar.
- ⚡ **Hızlı Filtre:** Vardiya tipine göre tek tıkla filtreleme *(SABİT, GRUPÇU, İZİNCİ, TERSANE, 8_5, GECE)*.
- ✅ **Aktif/Pasif filtresi:** Sadece aktif veya sadece pasif personeli listelemek için butonlar.
- 🔄 **Toplu Durum Değiştirme:** Birden fazla personeli seçip tek tıkla "Gemide", "İskelede", "Raporlu" yapabilirsiniz.
- 🔍 **Personel Kartı:** Listedeki bir ismi seçince, o kişinin son 7 günlük çalışma/izin özeti, NLP skoru, iş kalitesi ve sertifikalarını gösteren genişletilebilir detaylı kart açılır.
- 📤 **Excel'den toplu ekleme:** *Ad, Soyad, Vardiya Tipi, Makine Tipi, Gemi, Durum* ve *Performans Notu* sütunlu Excel ile toplu personel kaydı. Toast ile onaylanır.
- ➕ **Yeni personel:** Tüm vardiya tipleri için **çoklu gemi seçimi** yapılabilir. Personelin durumu *(Gemide, İskelede, Raporlu)* belirlenir. İş kalitesi (1-5) ve **performans notu** *(NLP analizine tabi)* girilebilir.
- ✏️ **Düzenleme:** Personelin vardiya tipi, bildiği makineler, yetkili olduğu gemiler, durumu ve performans notu güncellenebilir.
- 🎓 **Sertifika Yönetimi:** Her personel için makine bazında sertifika eklenebilir. *Geçerlilik tarihi olan sertifikalar öneri motorunda kontrol edilir.* Toast ile onaylanır.

### İzin Yönetimi

- 📅 **Manuel izin ekleme:** Personel, tarih aralığı ve not ile izin tanımlanır. Takvimde izinli günler turuncu renkte görünür.
- 📤 **Excel'den toplu izin ekleme:** *Ad, Soyad, Başlangıç, Bitiş, Not* sütunlu Excel ile toplu izin kaydı. Tarihler hem `GG.AA.YYYY` hem `YYYY-AA-GG` formatında okunur.
- 🗑️ **İzin silme:** Kayıtlı izinler tek tek silinebilir. Toast ile onaylanır.
- 🖼️ **Görsel takvim:** Seçilen ay için izinli günleri renkli olarak gösterir. Bugünün hücresi belirgin bir çerçeveyle işaretlenir.

---

## ✦ Öneri & Plan

**Amaç:** Vardiya planlamasının kalbidir. Hem manuel hem otomatik planlama yapılır. Çarkçı kayıtları da bu sekmede yönetilir.

### 🗓️ Toplu Planlama (Adil Dağıtım)

- Birden fazla gemi ve makine tipi için, belirli bir tarih aralığında ve seçilen günlerde otomatik vardiya ataması yapar.
- ⚖️ **Adil dağıtım:** Aynı kişiyi tekrar tekrar atamak yerine, en az kullanılan personeli tercih eden bir sayaç sistemi kullanır. Öneri motorundan gelen sıralamayı da dikkate alır.
- ⏱️ **Spinner:** İşlem süresince yükleme animasyonu gösterilir. Toast ile sonuç bildirilir.

### 🗑️ Vardiya Sil

- Belirli bir gemi, makine ve tarihteki mevcut atamayı ve saatlerini gösterir ve *"Atamayı Sil"* butonuyla kaldırır. Toast ile onaylanır.

### Tek Seferlik Öneri

- Bir gemi, makine ve tarih için en uygun **5 personeli** puan sıralamasıyla listeler.
- 🚪 **Çıkan yağcı seçeneği:** Bir personelin o gün çıktığını varsayarak, onu listeye dahil etmeden öneri yapar.

### Tekil Ata (Manuel Vardiya Atama - Saatli)

> **"Tekil Ata"**, sistemin önerisine bağlı kalmadan, sizin seçtiğiniz belirli bir personeli doğrudan vardiyaya atamanızı sağlayan butondur.  
> Öneri listesini beğenmediğinizde veya özel bir durum olduğunda kullanılır. Atama öncesinde çakışma kontrolü yapılır.
> **Çalışma saatleri:** Vardiya tipine göre varsayılan başlangıç/bitiş saatleri otomatik gelir, istenirse elle değiştirilebilir.

### ⚙️ Çarkçı Kayıtları

- Çarkçı adı, soyadı, bağlı olduğu gemi, vardiyası ve vardiya günleri girilir.
- ⚠️ **Sorunlu yağcı** seçilerek, o yağcı hakkında sorun/not yazılabilir. *Bu notlar NLP analizine tabi tutulur.*
- 📉 **Puan kırma (0-5):** Yağcının iş kalitesi puanı düşürülür ve performans geçmişine işlenir.
- 🚫 *Çarkçı sorunu olan yağcılar öneri motorunda elenir.*

---

## 📊 Bilgi

**Amaç:** Durum özeti, uyarılar, performans raporları ve yedekleme işlemleri.

- 🃏 **Dashboard Kartları:** Toplam personel, toplam gemi ve bugün izinli sayısı görsel kartlarda anlık olarak gösterilir.
- 💾 **Yedekleme:** Veritabanını manuel olarak `yedekler` klasörüne yedekler *(son 10 yedek tutulur)*. Ayrıca veritabanını doğrudan indirme butonu vardır. Toast ile onaylanır.
- 🧪 **Test Verisi:** Sistemi hızlıca test etmek için **4 gemi, 5 makine ve 8 personel** oluşturur.
- 📄 **PDF Raporları:** Aylık personel özeti ve vardiya planı PDF olarak indirilebilir.
- 🕐 **Son 24 Saat Atamaları:** Son 24 saatte yapılan tüm vardiya atamalarını saatleriyle birlikte listeler.
- 🚨 **Uyarılar:**
  - Bugün izinli olan personel listesi
  - Fazla mesai yapan *(son 7 günde 6+ gün çalışan)* personel listesi
  - Yarın izne başlayacak personel listesi
  - 🔊 **Sesli uyarı:** Uyarı metnini sesli okur. **Gece modu** açıksa *22:00-07:00* arası sesli okuma yapılmaz.
- 📅 **Aylık Performans Özeti:** Her personelin seçilen aydaki çalışma ve izin günlerini **tablo ve çubuk grafikle** gösterir.
- 📈 **Performans Geçmişi:** Seçilen personelin zaman içindeki puan değişimini çizgi grafikle gösterir. Otomatik ve manuel kayıtların ortalamasını da verir.
- 📊 **Çarkçı Performans Raporu:** En çok puan kırma işlemi yapan çarkçıları listeler.
- 📊 **Gemi Bazında Ortalama İş Kalitesi:** Her gemideki personelin ortalama iş kalitesini gösterir.
- 📥 **Vardiya Planı Excel Çıktısı:** Mevcut tüm vardiya planını saat bilgisiyle birlikte Excel dosyası olarak indirir.

---

## 🧠 Öneri Motoru (Arka Plan)

Uygulamanın en önemli parçası olan öneri motoru, bir pozisyona en uygun personeli bulurken aşağıdaki kriterleri değerlendirir:

| Kontrol | Açıklama |
|--------|----------|
| **Aktiflik** | Sadece `aktif=1` olan personel değerlendirilir. |
| **Durum** | Sadece *"Gemide"* veya *"İskelede"* olanlar önerilir. |
| **İzin** | İzinli olanlar elenir. |
| **Çakışma** | Aynı gün başka gemide veya aynı gün başka makinede çalışanlar elenir. |
| **Saat çakışması** | Aynı gün, çalışma saatleri çakışan başka vardiyası olanlar elenir. |
| **Makine bilgisi** | Personelin o makine tipini bilmesi gerekir. |
| **Sertifika** | Geçerli sertifikası olmayanlar elenir. |
| **Gemi yetkisi** | Personelin o gemide çalışma yetkisi olmalıdır. |
| **Çarkçı sorunu** | Çarkçı tarafından sorunlu işaretlenenler elenir. |
| **GECE kısıtlaması** | GECE tipi personel sadece *"Gecede"* konumundaki gemilere atanır. |
| **Vardiya-Konum eşleşmesi** | TERSANE tipi sadece *"Tersane"* gemilerine, 8_5 tipi *"Dışarıda"* gemilerine atanır. |
| **İş kalitesi** | Düşük kalite (1-2) **ağır ceza (-30)**, yüksek kalite (5) **bonus (+20)** alır. |
| **NLP duygu analizi** | `performans_notu` ve `carkci_sorun_notu` metinlerindeki olumlu/olumsuz kelimeler taranır. Olumlu yorumlar puanı artırır, olumsuz yorumlar düşürür. Ağır olumsuz yorumlar personeli tamamen eleyebilir. |
| **Gece dinlenme** | Dün gece çalışan bir personel bugün önerilirse **-30 ceza** alır. |
| **Peş peşe aynı gemi** | Dün aynı gemide çalışan personel **-15 ceza** alır *(rotasyon teşviki)*. |
| **Fazla mesai** | Son 7 günde 6+ gün çalışan personel **-20 ceza** alır. |
| **Vardiya puanı** | İZİNCİ (100) > GECE *(105, sadece Gecede gemilerinde)* > TERSANE (95) > GRUPÇU (80) > SABİT (60) > 8_5 (40) |

---

## 🎨 UI/UX Özellikleri

| Özellik | Açıklama |
|---------|----------|
| 🌓 **Tema değiştirme** | Koyu ve aydınlık tema arasında geçiş yapabilirsiniz. Sidebar'daki butona tıklamanız yeterli. |
| 📊 **Dashboard kartları** | Bilgi sayfasındaki istatistikler görsel kartlarda sunulur. |
| 🔔 **Toast bildirimleri** | Tüm başarılı işlemlerde, silme ve güncellemelerde ekranın üstünde kaybolan bildirimler gösterilir. |
| ⏳ **Spinner** | Toplu planlama ve akıllı dağıtım gibi uzun süren işlemlerde yükleme animasyonu. |
| 🎯 **Özel buton stilleri** | Birincil, ikincil ve tehlike butonları CSS ile özelleştirilmiştir; hover efektleri ve gölgeler mevcuttur. |
| 📱 **Mobil uyum** | Telefonda rahat kullanım için optimize edilmiştir. Safari/Chrome'dan ana ekrana kısayol eklenebilir. |
| 🧭 **Sidebar navigasyon** | Sol kenar çubuğunda tema, mobil ipuçları ve hızlı bilgiler yer alır. |
| 🔄 **Veri kalıcılığı** | Tüm veriler `ordino.db` dosyasında saklanır. Uygulama kapansa da kaybolmaz. |

---

## 🕐 Çalışma Saatleri

Her vardiya tipi için tanımlanmış varsayılan saat aralıkları:

| Vardiya Tipi | Başlangıç | Bitiş | Açıklama |
|-------------|-----------|-------|----------|
| SABIT | 08:00 | 08:00 (ertesi gün) | 24 saat esaslı |
| GRUPCU | 08:00 | 08:00 (ertesi gün) | 24 saat esaslı |
| İZİNCİ | 08:00 | 08:00 (ertesi gün) | 24 saat esaslı |
| TERSANE | 08:00 | 17:00 | Gündüz vardiyası |
| 8_5 | 08:00 | 17:00 | Gündüz vardiyası |
| GECE | 20:00 | 08:00 (ertesi gün) | Gece vardiyası |

> **Saat çakışması kontrolü:** Aynı personelin aynı tarihte, çalışma saatleri çakışan başka bir vardiyası varsa atama yapılmaz. Manuel atamalarda saatler değiştirilebilir.

---

## 📈 Uygulama Akış Şeması

```mermaid
flowchart TD
    A[Kullanıcı Girişi] --> B{Ana Menü}
    B --> C[🧩 Yapboz]
    B --> D[⚡ Acil Panel]
    B --> E[🚢 Gemiler]
    B --> F[👷 Personel & İzin]
    B --> G[✦ Öneri & Plan]
    B --> H[📊 Bilgi]

    C --> C1[Tarih seç, vardiya tahtasını gör]
    C1 --> C2[Boş hücreye uygun personeli seç]
    C2 --> C3[Atamayı yap / çıkar]
    C1 --> C4["🤖 Otomatik doldur (opsiyonel)"]

    D --> D1[Boştakiler / İskele / Tersane listele]
    D --> D2[Anlık izin yerine öneri al]
    D --> D3[Akıllı dağıtım başlat]
    D --> D4["📅 Dün kim çalıştı?"]

    E --> E1[Gemi / Makine ekle, düzenle, sil]
    E --> E2[Excel ile toplu veri yükle]
    E --> E3[Gemi bazlı personel listesini gör]

    F --> F1[Personel ara, filtrele, ekle, düzenle]
    F --> F2["🔍 Personel kartı (detaylı özet)"]
    F --> F3[Toplu durum değiştir]
    F --> F4[Sertifika yönet]
    F --> F5[İzin ekle / toplu izin yükle / takvimde gör]

    G --> G1["Toplu planlama (adil dağıtım)"]
    G --> G2[Tek seferlik öneri]
    G --> G3["Tekil ata (manuel, saatli)"]
    G --> G4[Vardiya sil]
    G --> G5[Çarkçı kaydı ve puan kırma]

    H --> H1[Yedekleme / Test verisi / PDF rapor]
    H --> H2[Uyarılar ve sesli okuma]
    H --> H3[Performans özeti ve geçmiş grafikleri]
    H --> H4[Excel çıktısı indir]
