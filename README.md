# Illy Specialty Coffee Shop Management System

### Daxili Nəzarət, Anbar İdarəetməsi, Əməliyyat Analitikası və İşçi Nəzarəti Sistemi

İtalyan üslublu (Illy konseptli) ixtisaslaşmış qəhvəxana filialı üçün hazırlanmış, lokal-ilk (local-first) arxitekturaya malik tam təhlükəsiz veb idarəetmə sistemi.

---

> [!IMPORTANT]
> **Qeyri-Fiskal Sistem (Non-Fiscal Scope)**:
> Bu sistem **fiskal kassa aparatı deyildir** və vergi/fiskal uyğunluq funksiyalarını icra etmir. Rəsmi fiskal çek və vergi əməliyyatları filialın mövcud rəsmi aparatına aiddir. Bu proqram təminatı yalnız:
>
> - Daxili nəzarət və operativ nəzarət
> - Xammal və anbar qalıqlarının dəqiq uçotu
> - Satışların və sifarişlərin izlənilməsi
> - Barista sürəti və işçi nəzarəti
> - Süni intellekt (ML) dəstəkli təchizat analitikası üçün nəzərdə tutulmuşdur.

---

## ☕ Əsas Xüsusiyyətlər

1. **GNOME Üslublu İstifadəçi Girişi**:
   - Vizual istifadəçi profil kartları (avatar, ad-soyad, vəzifə nişanı).
   - Admin profillərində xüsusi `Admin` nişanı.
   - **Təhlükəsizlik qaydası (D3)**: Developer hesabı ümumi siyahıda görünmür!
   - **"Digər" / "Other" seçimi (D4)**: Developer yalnız bu seçimdən istifadəçi adı və şifrə ilə daxil olur.
   - 30 dəqiqəlik hərəkətsizlikdən sonra avtomatik sessiya kilidlənməsi.

2. **Dəqiq Xammal Anbarı və Çoxkomponentli Reseptlər (E Bölməsi)**:
   - Sistem bitmiş içkiləri deyil, **xammal, süd, sirop və qablaşdırmanı** əsas anbar həqiqəti olaraq izləyir.
   - Hər bir məhsul variantının (məs: _Latte Böyük Takeaway_) limitsiz tərkibli resepti olur (məs: 22g qəhvə, 260ml süd, 1 böyük stəkan, 1 böyük qapaq).
   - Sifariş təsdiqləndikdə anbar qalıqları resept üzrə atomik silinir.

3. **Sürətli Barista Touch POS İnterfeysi (F Bölməsi)**:
   - Sancılan tez satış qısayolları (Shortcuts).
   - Ekran ölçüsünə uyğunlaşan dinamik adaptiv şəbəkə (az element olduqda böyük toxunma düymələri).
   - Çoxməhsullu səbət, endirim növləri (% və ya sabit ₼ məbləğ, Qonaq/Personal 100% statusu).
   - Ödəniş üsulları: Nağd, Kart, Qarışıq, Digər.
   - Daxili sifariş qəbzi (Operational kitchen ticket) çap formatı.

4. **Ləğv / Düzəliş və Qalıqların Bərpası (F3)**:
   - Səhv vurulmuş sifarişlər bazadan silinmir (soft-delete, status `cancelled`).
   - Məcburi ləğv səbəbi qeyd olunur və audit jurnalı yazılır.
   - Sifariş üzrə silinmiş xammal qalıqları **dəqiqliklə anbara geri qaytarılır**.

5. **Növbələr və Kassa Balansı (G Bölməsi)**:
   - Növbənin açılması (ilkin kassa ilə).
   - Növbənin bağlanması (faktiki kassa, gözlənilən kassa və kassa fərqinin hesablanması).

6. **İnventarizasiya və Faktiki Sayım (H Bölməsi)**:
   - Dövri sayım sessiyaları, sistem qalığı ilə faktiki sayımın müqayisəsi.
   - Kənarlaşmaların (tullantı, dağılma) təsdiqi və anbar jurnalının yenilənməsi.

7. **Süni İntellekt və Maşın Öyrənməsi (ML) Tövsiyələri (I Bölməsi)**:
   - Tükənmə ehtimalı yüksək olan xammalların qabaqcadan aşkarlanması.
   - Təchizat üçün tövsiyə olunan sifariş miqdarlarının biznes dilində təqdimatı.
   - Çarpaz satış və pik saatlar üzrə işçi planlaşdırma tövsiyələri.
   - **Qorunma Qaydası**: ML çəkiləri saxlanma siyasəti (retention) tərəfindən silinmir!

8. **Təhlükəsizlik və Demo / REAL Rejim (L & M Bölmələri)**:
   - 7 günlük sınaq Demo rejimi.
   - Anti-tamper vaxt qoruması (sistem saatını geriyə çəkməyə qarşı bloklanma).
   - Kriptoqrafik HMAC-SHA256 əsaslı REAL aktivasiya açarı.
   - Baza şifrələnməsi (AES-256-GCM) və GZ sıxılma seçimləri.
   - REAL rejimdə bazanın `.sql`, `.json` və `.txt` (ağac strukturu) formatlarında tam ixracı.
   - Uzaq mərkəzi server üçün avtonom Python API paketinin `.ZIP` olaraq endirilməsi.

---

## 🚀 Başlatma və Quraşdırma

Sistem Python 3.14 standart kitabxanaları ilə tam offline rejimdə dərhal işləyir.

### 1. Verilənlər Bazasını İlkin Məlumatlarla Doldurmaq (Seed):

```bash
python3 seed.py
```

### 2. Veb Serveri Başlatmaq:

```bash
python3 run.py --port 8000
```

Server lokal olaraq `127.0.0.1` ünvanına bağlanır. Uzaq giriş yalnız HTTPS reverse proxy
və ya SMTP reset göndərişi üçün ayrıca, 15 dəqiqəlik Bore tuneli aktivləşdirildikdə istifadə
olunmalıdır. Demo rejimində əlavə key konfiqurasiyası tələb olunmur. İstəyə görə
`COFFEE_APP_SECRET` bütün imza və lisenziya secret-larını vahid mənbədən idarə edir;
`DEV_MASTER_PASSWORD` isə developer şifrəsini dəyişmək üçündür.

Server işə düşdükdən sonra brauzerinizdə daxil olun:
👉 **`http://localhost:8000`**

---

## 👥 İstifadəçi Hesabları və Rollar

| Rol           | İstifadəçi Adı  | Şifrə                   | Təyinatı                                                                             |
| ------------- | --------------- | ----------------------- | ------------------------------------------------------------------------------------ |
| **Developer** | `developer`     | İlk inkişaf başlatmasında konsola yalnız bir dəfə yazılan təsadüfi şifrə | Yalnız "Digər" panelindən daxil olur. Texniki tənzimləmələr, REAL aktivasiya, ixrac. Şifrə developer panelindən cari şifrə təsdiqi ilə dəyişdirilə bilər. |
| **Admin**     | `admin`         | `admin123!`             | Biznes idarəetməsi, anbar mədaxili, reseptlər, hesabatlar, sayım, növbələr.          |
| **Barista 1** | `barista_elvin` | `barista123!`           | POS kassa, sürətli sifariş, səbət, çek çapı, ləğvetmə.                               |
| **Barista 2** | `barista_nigar` | `barista123!`           | POS kassa, sürətli sifariş, növbə idarəetməsi.                                       |

> [!NOTE]
> İnkişaf mühitində developer şifrəsi ilk işə salınmada `data/.developer_password` faylında (0600) yaradılır və konsola bir dəfə göstərilir. İstehsalda `DEV_MASTER_PASSWORD` mühit dəyişəni tələb olunur. Developer şifrəsini yalnız developer özü cari şifrəni təsdiqləməklə dəyişə bilər; dəyişiklik audit jurnalına yazılır.

---

## 🧪 Avtomatlaşdırılmış Testləri İcra Etmək

Bütün autentifikasiya, resept silinmələri, anbar bərpası, lisenziya və ixrac testləri:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

Bütün 16 test tam uğurla (`OK`) tamamlanır.

---

## 📁 Layihə Strukturu

```
coffe_shop/
├── app/
│   ├── auth/            # JWT avtorizasiya və GNOME profil xidməti
│   ├── core/            # Konfiqurasiya, SQLite WAL bazası, audit və saxlama siyasəti
│   ├── developer/       # REAL ixrac (.sql, .json, .txt), texniki diaqnostika
│   ├── inventory/       # Faktiki sayım və kənarlaşma audit jurnalı
│   ├── ml/              # Tələbat proqnozu və qorunan ML çəkiləri
│   ├── orders/          # Səbət, endirimlər, ləğv/bərpa və qısayollar
│   ├── products/        # Məhsullar və variantlar
│   ├── recipes/         # Çoxkomponentli xammal reseptləri
│   ├── reports/         # Satış qrafikləri, pik saatlar və heyət analitikası
│   ├── security/        # Kriptoqrafik aktivasiya, anti-tamper və AES-256
│   ├── shifts/          # Növbələr və kassa balansı
│   ├── static/          # Touch POS interfeysi, CSS və JS skriptləri
│   ├── stock/           # Əsas xammal anbarı və silinmə mühərriki
│   ├── sync/            # Offline-ilk sinxronizasiya və remote ZIP generatoru
│   ├── users/           # Heyət iyerarxiyası və profil idarəetməsi
│   └── main.py          # Flask tətbiq fabriki və bütün API marşrutları
├── tests/               # 16 ədəd avtomatlaşdırılmış inteqrasiya və vahid testi
├── seed.py              # Real Illy menyusu və nümunə məlumatlar
├── run.py               # Əsas server işəsalma skripti
└── README.md            # Sənədləşmə
```

## 📦 Pip və Docker ilə quraşdırma

Python 3.12+ üçün təcrid olunmuş mühitdə pinned asılılıqları quraşdırın:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python run.py --init-db
python run.py --seed  # istəyə görə demo məlumatları
python run.py --host 127.0.0.1 --port 8000
```

Docker Compose istifadə edərkən `.env` faylında ən azı `COFFEE_APP_SECRET` və `DEV_MASTER_PASSWORD` təyin edin, sonra:

```bash
docker compose up -d --build
curl http://localhost:8000/api/health
docker compose logs -f coffee-shop
```

Compose `coffee_data` volume-u ilə `data/` qovluğunu saxlayır. Uzaq giriş üçün HTTPS reverse proxy istifadə edin və `.env` faylını repozitoriyaya əlavə etməyin.

### Sənədlər

- [API reference](docs/API.md)
- [Database and ER diagram](docs/DATABASE.md)
- [Deployment runbook](docs/DEPLOYMENT.md)
# coffe-shop-automation
