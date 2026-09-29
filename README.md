# Kanban Proje Yönetim Sistemi

Yerel ağda (LAN) çalışan, **Python + Django** tabanlı, tek containerda deploy edilen web uygulaması. Jira Server / Data Center REST API'sine bağlanarak issue'ları okur (`READ-ONLY`), durum ve atama gibi durumları uygulama içinden yönetir. Kanban kartları uygulamanın kendi veritabanında takip edilir.

## Özellikler

- **5 seviye hiyerarşik rol** — Admin → Proje Yöneticisi → Proje Programcısı → Raportör → İzleyici.
- **Kendi auth sistemi** — admin-only kullanıcı kaydı, özel middleware ile seviye bazlı yetkilendirme (`@role_required`).
- **Jira entegrasyonu** (`READ-ONLY`) — issue bilgilerini çeker; durum/atama gibi yaz işlemleri uygulamanın eşleme tablosu üzerinden yönetilir.
- **Şifreli Jira credential yönetimi** — `EncryptedCharField` (Fernet) ile veritabanında şifreli saklanır.
- **Uygulama içi sprint yönetimi** — Jira tarafında sprint oluşturulmaz/güncellenmez; tamamen uygulama içinde yapılır.
- **Docker + Nginx + Postgres** — tek containerda, kolay LAN deploy.

## Teknoloji Stack

| Katman | Seçim |
|--------|-------|
| Backend | Django 5.2 (Python 3.13) |
| Veritabanı | PostgreSQL (Docker/LAN) / SQLite (yerel) |
| Frontend | Django Templates + HTMX + Chart.js (gelecek fazlar) |
| Jira | `jira` resmi SDK + `requests` (READ-ONLY) |
| Deploy | Docker Compose (Gunicorn + Nginx + Postgres) |

## Proje Yapısı

```
.
├── kanban/                 # Django projesi (settings, urls, wsgi)
├── kanbanapp/              # Uygulama: modeller, views, templates, middleware
│   ├── models.py           # Role, User, Project, Jira*, Kanban*
│   ├── fields.py           # EncryptedCharField (Fernet)
│   ├── middleware.py       # role_level + @role_required
│   ├── context_processors.py
│   ├── management/commands/seed_initial.py  # rol + admin seed
│   └── templates/          # base, login, register, dashboard, projects
├── nginx/                  # reverse proxy config
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
└── PLAN.md                 # tam proje planı
```

## Yerel Kurulum (SQLite)

1. Sanal ortam oluştur:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   ```

2. Bağımlılıkları kur:

   ```bash
   pip install -r requirements.txt
   ```

3. SQLite ile çalıştır (varsayılan: `POSTGRES_HOST` ayarlanmadığında):

   ```bash
   python manage.py migrate
   python manage.py seed_initial   # DJANGO_ADMIN_USER / DJANGO_ADMIN_PASSWORD varsa admin oluşturur
   ```

4. Yönetici paneli:

   ```bash
   python manage.py runserver
   ```

   → `http://localhost:8000/`

   **Not:** Yerel geliştirme için static dosyaları (`/static/...`) çalışması `DEBUG=True` gerekir. `.env` içinde `DEBUG=True` yapın (veya çalıştırırken `DEBUG=True python manage.py runserver`). Production (gunicorn + nginx) için `DEBUG=False` kalır; o zaman `collectstatic` çalışıp nginx static'ı servis eder.

## Docker / LAN Kurulumu

1. `.env` dosyasını kopyala ve düzenle:

   ```bash
   cp .env.example .env
   ```

2. **Şifre şifreleme anahtarını** üret (bir kez, sonra asla kaydetme):

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Çıktıyı `.env` içinde `ENCRYPTION_KEY=` satırına yapıştır.

3. İsteğe bağlı başlatıcı admin:

   ```bash
   DJANGO_ADMIN_USER=admin DJANGO_ADMIN_PASSWORD=admin12345 \
     docker compose up --build -d
   ```

   `.env` içinde `DJANGO_ADMIN_USER` / `DJANGO_ADMIN_PASSWORD` varsa, ilk çalışmada otomatik oluşturulur.

4. Uygulamaya bağlan (`.env` üzerinden):

   ```
   http://<lan-ip>:8008/
   ```

   Container yapısı: `nginx:8008` → `web:8000` (Gunicorn) → `db:5432` (PostgreSQL).

## Rol ve Yetkilendirme

| Seviye | Rol | Yetkiler |
|--------|-----|----------|
| 1 | Admin | Tüm yetkiler (rol/proje/Jira bağlantısı/rapor) |
| 2 | Proje Yöneticisi | Kendi projesi: kart, kolon, durum, Jira yenileme, rapor |
| 3 | Proje Programcısı | Kendi projesi: kart oluşturma/düzenleme, görüntüleme |
| 4 | Raportör | Rapor/dashboard görüntüleme (kart düzenleme yok) |
| 5 | İzleyici | Sadece görüntüleme |

Kullanıcı kaydı **sadece Admin** tarafından yapılabilir. Yetki seviyesi, `RoleLevelMiddleware` her isteğe `request.role_level` olarak aktarır; `@role_required(level)` dekoratörü ile korunan yollar tanımlanır.

## Jira Entegrasyonu (`READ-ONLY`)

- Uygulama projeleri Jira projelerinden bağımsızdır; Jira issue'ları uygulamaya dahil edilir.
- Credential'lar veritabanında şifreli saklanır (admin + proje yöneticisi yönetir).
- Çekim **yalnızca manuel** ("Yenile" butonu) yapılır; `RefreshLog` tutulur.
- **Sprint yönetimi yalnızca uygulama içindedir** — Jira tarafında sprint değiştirilmez.
- Durum değiştirme, atama gibi yaz işlemleri uygulamanın Jira durum eşleme tablosu üzerinden yapılır.

## Veritabanı Şeması (Faz 1)

`kanbanapp/migrations/0001_initial.py`:

- **Role** — id, name, slug, level, description
- **User** (`AbstractUser`) — role, project, email, `parent_link`
- **Project** — name, key, description, jira_connection, created_by
- **JiraConnection** — name, host, username, password (şifreli), is_default
- **JiraStatus** — jira_status_key, name, color, jira_id
- **JiraCustomStatus** — project, name, color, position, parent_status
- **KanbanColumn** — status_type, project, name, color, position
- **KanbanCard** — project, column, title, description, jira_issue_id, jira_key, is_extra, position
- **RefreshLog** — project, jira_connection, status, pulled_count, error, timestamp

## Yönetici Paneli

Django admin hazır gelir (`/admin/`). `seed_initial` komutu, ilk çalışmada 5 rolü ve (ortam değişkenlerinden) başlatıcı admin superuser'ı oluşturur.

## Fazlar

Detaylı yol haritası için **[PLAN.md](PLAN.md)**'ye bakın.

- **Faz 1 — Temel** ✅ Bu commit: Django iskelet, Docker kurulumu, migration, auth (login/admin-only), 5 rol + permission.
- **Faz 2 — Proje & Jira** — Proje CRUD, Jira bağlantısı (admin + yönetici), credential şifreleme, Jira READ-ONLY çekme + yenile butonu.
- **Faz 3 — Kanban Core** — Durum (Jira türevi + custom), kolon, kart CRUD.
- **Faz 4 — Raporlama** — Filtreli raporlar, CSV export, Chart.js.
- **Faz 5 — Polishing** — Hata yönetimi, loglar, dokümantasyon.

## Güvenlik Notu

- `.env`, Jira credential'ları ve `.venv/` **git tarafından yoksayılır** (`.gitignore`).
- `ENCRYPTION_KEY` bir Fernet anahtarıdır; **asla git'e yüklenmemeli** ve production'da her ortamda aynı gizli değerde tutulmalıdır.
