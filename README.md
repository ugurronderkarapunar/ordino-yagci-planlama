🧩 Sekmeler ve Genel Yapı
Uygulama 6 ana sekmeden oluşur. Her sekme belirli bir işlevi yerine getirir.

Sekme	Amaç
🧩 Yapboz	Günlük vardiya tahtasını görsel olarak yönetme
⚡ Acil	Anlık ihtiyaçlar için hızlı personel bulma
🚢 Gemiler	Gemi ve makine tipi kayıtlarını yönetme
👷 Personel & İzin	Personel kaydı, düzenleme, izin takibi
✦ Öneri	Vardiya planlama, öneri motoru, çarkçı kayıtları
📊 Bilgi	Raporlar, istatistikler, yedekleme
🧩 Yapboz (İnteraktif Vardiya Tahtası)
Amaç: Seçilen bir tarih için tüm gemi ve makine tiplerinde kimin görevli olduğunu renkli kutularda gösterir. Boş pozisyonlara hızlıca personel atamanızı sağlar.

Renkli hücreler: Her vardiya tipi farklı bir renkle gösterilir (SABİT mavi, GRUPÇU yeşil, İZİNCİ turuncu, TERSANE kırmızı, 8_5 mor, GECE turkuaz).

Personel seçimi: Boş bir hücreye tıkladığınızda, yalnızca o pozisyona uygun personeller listelenir (izin, çakışma, sertifika, gemi yetkisi, çarkçı sorunu gibi tüm kontroller yapılır).

❌ Çıkar: Atanmış personeli vardiyadan çıkarmak için kırmızı buton.

🧹 Günü Temizle: Seçilen tarihteki tüm atamaları tek tuşla siler.

📅 Bugün: Tarih seçiciyi bugüne hızlıca döndürür.

⚡ Acil Panel
Amaç: Günlük operasyonda anlık kararlar vermenizi sağlar. "Kim boşta?", "İskelede kim var?", "Aniden izin isteyen oldu, yerine kimi koyalım?" gibi sorulara anında cevap verir.

👤 Boştakiler: Bugün hiçbir vardiyası olmayan aktif personeli, hangi gemi ve makinelerde yetkili olduğuyla birlikte listeler.

🏝️ İskelede Bekleyenler: Şu an iskelede olan personelin listesi.

🏗️ Tersaneye Uygunlar: Tersane konumundaki gemilere atanabilecek uygun personeli listeler.

📞 Anlık İzin Yerine: Bir personel aniden izin istediğinde, onun yerine önerilecek en uygun 5 adayı sıralar.

🌐 Tüm Boşluklar: Tüm gemi/makine kombinasyonları için boş pozisyonları ve önerilen personeli gösterir.

🏝️ İskeleye Çıkar: Seçilen personeli tek tuşla "İskelede" durumuna alır.

🚀 İskeledekileri Akıllı Dağıt: İskelede bekleyen tüm personeli, öneri motorunu kullanarak en uygun boş pozisyonlara otomatik yerleştirir.

🚢 Gemiler & Makine Yönetimi
Amaç: Sistemdeki gemi ve makine tipi kayıtlarını tutar.

Yeni gemi/makine ekleme: Aynı form üzerinden hem gemi hem makine tipi eklenir.

Konum bilgisi: Her geminin "Tersane, Dışarıda, Gecede, Belirtilmedi" konumlarından biri seçilir. Bu bilgi öneri motorunda kullanılır.

Excel ile toplu ekleme: "Gemi Adı" ve "Makine Tipi" sütunları içeren bir Excel dosyasıyla toplu kayıt eklenebilir.

👥 Gemi Bazlı Personel Listesi: Seçilen gemide çalışan tüm personeli listeleyen genişletilebilir bir bölüm.

Düzenleme ve silme: Gemi ve makine tipleri ayrı ayrı düzenlenebilir veya silinebilir. Bağlı personel varsa silmeye izin verilmez.

👷 Personel & İzin
Amaç: Tüm personel kayıtlarının ve izinlerin yönetildiği merkezdir.

Personel Yönetimi
🔍 Arama: İsim, soyisim, vardiya tipi, gemi ve durum alanlarında anlık metin araması yapar.

Hızlı Filtre: Vardiya tipine göre tek tıkla filtreleme (SABİT, GRUPÇU, İZİNCİ, TERSANE, 8_5, GECE).

Aktif/Pasif filtresi: Sadece aktif veya sadece pasif personeli listelemek için butonlar.

Excel'den toplu ekleme: Ad, Soyad, Vardiya Tipi, Makine Tipi, Gemi, Durum ve Performans Notu sütunlu Excel ile toplu personel kaydı.

Yeni personel: Tüm vardiya tipleri için çoklu gemi seçimi yapılabilir. Personelin durumu (Gemide, İskelede, Raporlu) belirlenir. İş kalitesi (1-5) ve performans notu (NLP analizine tabi) girilebilir.

Düzenleme: Personelin vardiya tipi, bildiği makineler, yetkili olduğu gemiler, durumu ve performans notu güncellenebilir.

Sertifika Yönetimi: Her personel için makine bazında sertifika eklenebilir. Geçerlilik tarihi olan sertifikalar öneri motorunda kontrol edilir.

İzin Yönetimi
Manuel izin ekleme: Personel, tarih aralığı ve not ile izin tanımlanır. Takvimde izinli günler turuncu renkte görünür.

Excel'den toplu izin ekleme: Ad, Soyad, Başlangıç, Bitiş, Not sütunlu Excel ile toplu izin kaydı. Tarihler hem GG.AA.YYYY hem YYYY-AA-GG formatında okunur.

İzin silme: Kayıtlı izinler tek tek silinebilir.

Görsel takvim: Seçilen ay için izinli günleri renkli olarak gösterir. Bugünün hücresi belirgin bir çerçeveyle işaretlenir.

✦ Öneri & Plan
Amaç: Vardiya planlamasının kalbidir. Hem manuel hem otomatik planlama yapılır. Çarkçı kayıtları da bu sekmede yönetilir.

🗓️ Toplu Planlama (Adil Dağıtım)
Birden fazla gemi ve makine tipi için, belirli bir tarih aralığında ve seçilen günlerde otomatik vardiya ataması yapar.

Adil dağıtım: Aynı kişiyi tekrar tekrar atamak yerine, en az kullanılan personeli tercih eden bir sayaç sistemi kullanır. Öneri motorundan gelen sıralamayı da dikkate alır.

🗑️ Vardiya Sil
Belirli bir gemi, makine ve tarihteki mevcut atamayı gösterir ve "Atamayı Sil" butonuyla kaldırır.

Tek Seferlik Öneri
Bir gemi, makine ve tarih için en uygun 5 personeli puan sıralamasıyla listeler.

Çıkan yağcı seçeneği: Bir personelin o gün çıktığını varsayarak, onu listeye dahil etmeden öneri yapar.

Tekil Ata (Manuel Vardiya Atama)
"Tekil Ata", sistemin önerisine bağlı kalmadan, sizin seçtiğiniz belirli bir personeli doğrudan vardiyaya atamanızı sağlayan butondur.
Öneri listesini beğenmediğinizde veya özel bir durum olduğunda kullanılır. Atama öncesinde çakışma kontrolü yapılır.

⚙️ Çarkçı Kayıtları
Çarkçı adı, soyadı, bağlı olduğu gemi, vardiyası ve vardiya günleri girilir.

Sorunlu yağcı seçilerek, o yağcı hakkında sorun/not yazılabilir. Bu notlar NLP analizine tabi tutulur.

Puan kırma (0-5): Yağcının iş kalitesi puanı düşürülür ve performans geçmişine işlenir.

Çarkçı sorunu olan yağcılar öneri motorunda elenir.

📊 Bilgi
Amaç: Durum özeti, uyarılar, performans raporları ve yedekleme işlemleri.

💾 Yedekleme: Veritabanını manuel olarak yedekler klasörüne yedekler (son 10 yedek tutulur). Ayrıca veritabanını doğrudan indirme butonu vardır.

🧪 Test Verisi: Sistemi hızlıca test etmek için 4 gemi, 5 makine ve 8 personel oluşturur.

📄 PDF Raporları: Aylık personel özeti ve vardiya planı PDF olarak indirilebilir.

🕐 Son 24 Saat Atamaları: Son 24 saatte yapılan tüm vardiya atamalarını listeler.

🚨 Uyarılar:

Bugün izinli olan personel listesi

Fazla mesai yapan (son 7 günde 6+ gün çalışan) personel listesi

Yarın izne başlayacak personel listesi

🔊 Sesli uyarı: Uyarı metnini sesli okur. Gece modu açıksa 22:00-07:00 arası sesli okuma yapılmaz.

📅 Aylık Performans Özeti: Her personelin seçilen aydaki çalışma ve izin günlerini tablo ve çubuk grafikle gösterir.

📈 Performans Geçmişi: Seçilen personelin zaman içindeki puan değişimini çizgi grafikle gösterir. Otomatik ve manuel kayıtların ortalamasını da verir.

📊 Çarkçı Performans Raporu: En çok puan kırma işlemi yapan çarkçıları listeler.

📊 Gemi Bazında Ortalama İş Kalitesi: Her gemideki personelin ortalama iş kalitesini gösterir.

📥 Vardiya Planı Excel Çıktısı: Mevcut tüm vardiya planını Excel dosyası olarak indirir.

🧠 Öneri Motoru (Arka Plan)
Uygulamanın en önemli parçası olan öneri motoru, bir pozisyona en uygun personeli bulurken şunları değerlendirir:

Kontrol	Açıklama
Aktiflik	Sadece aktif=1 olan personel değerlendirilir.
Durum	Sadece "Gemide" veya "İskelede" olanlar önerilir.
İzin	İzinli olanlar elenir.
Çakışma	Aynı gün başka gemide veya aynı gün başka makinede çalışanlar elenir.
Makine bilgisi	Personelin o makine tipini bilmesi gerekir.
Sertifika	Geçerli sertifikası olmayanlar elenir.
Gemi yetkisi	Personelin o gemide çalışma yetkisi olmalıdır.
Çarkçı sorunu	Çarkçı tarafından sorunlu işaretlenenler elenir.
GECE kısıtlaması	GECE tipi personel sadece "Gecede" konumundaki gemilere atanır.
Vardiya-Konum eşleşmesi	TERSANE tipi sadece "Tersane" gemilerine, 8_5 tipi "Dışarıda" gemilerine atanır.
İş kalitesi	Düşük kalite (1-2) ağır ceza (-30), yüksek kalite (5) bonus (+20) alır.
NLP duygu analizi	performans_notu ve carkci_sorun_notu metinlerindeki olumlu/olumsuz kelimeler taranır. Olumlu yorumlar puanı artırır, olumsuz yorumlar düşürür. Ağır olumsuz yorumlar personeli tamamen eleyebilir.
Gece dinlenme	Dün gece çalışan bir personel bugün önerilirse -30 ceza alır.
Peş peşe aynı gemi	Dün aynı gemide çalışan personel -15 ceza alır (rotasyon teşviki).
Fazla mesai	Son 7 günde 6+ gün çalışan personel -20 ceza alır.
Vardiya puanı	İZİNCİ (100) > GECE (105, sadece Gecede gemilerinde) > TERSANE (95) > GRUPÇU (80) > SABİT (60) > 8_5 (40)
🎨 Diğer Özellikler
🌓 Tema değiştirme: Koyu ve aydınlık tema arasında geçiş yapabilirsiniz. Başlığın yanındaki butona tıklamanız yeterli.

📱 Mobil uyum: Telefonda rahat kullanım için optimize edilmiştir. Safari/Chrome'dan ana ekrana kısayol eklenebilir.

🔄 Veri kalıcılığı: Tüm veriler ordino.db dosyasında saklanır. Uygulama kapansa da kaybolmaz. Aynı cihazda kullanıldığı sürece güvendedir.
flowchart TD
    A[Kullanıcı Girişi] --> B{Ana Menü}
    B --> C[🧩 Yapboz]
    B --> D[⚡ Acil Panel]
    B --> E[🚢 Gemiler]
    B --> F[👷 Personel & İzin]
    B --> G[✦ Öneri & Plan]
    B --> H[📊 Bilgi]

    
