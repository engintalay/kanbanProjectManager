# Kanban Proje Yönetim Sistemi — Plan

Durum: **Faz 1–4 tamamlandı.** Faz 5 (dokümantasyon/cilalama) kısmen. Bu dosya hem hedef spec hem mevcut durumdur.

## 1. Özet

Yerel ağda (LAN) çalışan, **Python + Django** tabanlı web uygulaması. Jira Server/Data Center REST API'sine bağlanır:

- **READ:** issue çekme, JQL import, durum senkronu, kart yenileme.
- **WRITE (sınırlı):** kolon taşımasında, proje `sync_jira_status` + mapping `transfer_to_jira` açıksa Jira **durum geçişi** (`transition_issue`).
- **Yerel kalanlar:** atama, yorum, sprint — Jira'ya yazılmaz.
- **Yapılmaz:** Jira'da issue oluşturma, Jira sprint yönetimi.

Kanban kartları uygulamanın kendi veritabanında takip edilir.

Deploy: Docker Compose — **üç servis** (`nginx` + `web`/Gunicorn + `postgres`). Tek container değildir.

## 2. Teknoloji Stack

| Katman | Seçim | Durum |
|--------|-------|-------|
| Backend | **Django 5.2** (Python 3.13) | ✅ |
| DB | PostgreSQL (Docker/LAN) / SQLite (yerel) | ✅ |
| Frontend | Django Templates + Chart.js | ✅ Chart.js. **HTMX yok** (planlanmıştı, kullanılmadı) |
| Jira SDK | `jira` + `requests` | ✅ okuma + opsiyonel durum geçişi |
| Deploy | Docker Compose (Gunicorn + Nginx + Postgres) | ✅ 3 servis, host `:8008` |

## 3. Veritabanı Şeması

### 3.1 Uygulanan modeller

- **roles** — id, name, slug, level(1-5), description
- **users** — AbstractUser + role, project(optional), theme(optional), email unique
- **projects** — id, name, key, description, jira_connection(optional), created_by, sync_jira_status, hidden_jira_statuses(M2M), default_jql, jql_max_results
- **project_members** — id, project, user (unique)
- **jira_connections** — id, name, host, username, password(enc), is_default, created_by, disable_proxy
- **jira_statuses** — id, jira_status_key, name, color, jira_id
- **jira_custom_statuses** — id, project, name, color, position, parent_status *(model var, views/forms kullanmıyor; custom kolonlar `kanban_columns.status_type=custom`)*
- **kanban_columns** — id, project, name, position, color, status_type(jira/custom)
- **status_mappings** — id, project, app_status, jira_status(nullable), position, transfer_to_jira, is_primary — bir kolona birden fazla Jira durumu
- **jira_issues** — Jira snapshot (PLAN'daki `project_issues` yerine): project, jira_id, jira_key, summary, description, status, assignee, reporter, created, updated, sprint, epic_key, blocks/blocked_by JSON, pulled_at
- **kanban_cards** — project, column, title, description, jira_issue_id, jira_key, is_extra, position, difficulty_level / initial_difficulty_level / requested_difficulty_level (Fibonacci), developer_assessment, parent_card, is_sub_task, assignee, **sprint FK**, timestamps
- **card_comments** — card, author, comment *(PLAN dışı, uygulandı)*
- **issue_requests** — project, card, type(difficulty_change/split/reassign), reason(too_hard/too_easy), requested_difficulty, description, status(pending/approved/rejected), requested_by, assigned_to
- **sprints** — project, name, start_date, duration(1/2/3/4 hafta/serbest), team_members(**M2M User**, JSON değil), status(planning/active/completed), position, capacity(optional int)
- **refresh_logs** — project, jira_connection, status, pulled_count, error, timestamp
- **themes** — name, code, is_active, is_default, CSS değişkenleri *(PLAN dışı)*
- **project_tickets** — project(nullable), ticket_type, title, description, priority, status, reporter, assignee, card, resolution_notes *(PLAN dışı: Hata & Talepler)*
- **ticket_attachments** / **ticket_comments**

### 3.2 Planlanan, uygulanmayan

- **project_groups** — grup bazlı proje ACL yok. Django `Group` sadece rol adı seed.
- **sprint_assignments** — yok; kart `sprint` FK ile bağlı.
- Role `permissions` JSON — yok; yetki `role.level` + view `_can_*` helper'ları.

## 4. Kimlik Doğrulama & Rol Yönetimi ✅

**5 seviye** (üst rol alt yetkileri kapsar):

| Seviye | Rol | Yetkiler |
|--------|-----|----------|
| 1 | **Admin** | Tüm yetkiler (rol/proje/Jira bağlantısı/rapor/tema) |
| 2 | **Proje Yöneticisi** | Kendi projesi: kart, kolon, durum, Jira yenileme, rapor |
| 3 | **Proje Programcısı** | Kendi projesi: kart oluşturma/düzenleme, görüntüleme |
| 4 | **Raportör** | Rapor/dashboard görüntüleme (tüm projeler), kart düzenleme YOK |
| 5 | **İzleyici** | Sadece görüntüleme |

**Proje görünürlüğü (mevcut):**
- **Admin / Raportör / İzleyici:** tüm projeler.
- **Proje Yöneticisi / Programcı:** oluşturduğu + `user.project` + `ProjectMember` üyelikleri.

**Kalan farklar:**
- PLAN'daki “programcı sadece tek kişilik projeleri görür” **uygulanmadı** — üyelik yeter.
- Grup bazlı erişim (`project_groups`) **yok**.
- Kullanıcı kaydı **sadece admin** (`/register/`). ✅
- Middleware `request.role_level` set eder; view'lar `@role_required` yerine `_can_*` kullanır.

## 5. Jira Entegrasyonu (READ + opsiyonel durum geçişi) ✅

- Uygulama projeleri Jira projelerinden bağımsız.
- **İş dahil etme:** Jira issue ID / **JQL** ile arama, kapalı issue filtre, toplu import (`kanban_card_import_jira`). Proje `default_jql` + `jql_max_results`.
- Bir Jira issue birden fazla uygulama projesinde olabilir.
- Credential: **admin + proje yöneticisi**, Fernet şifreli, `disable_proxy`.
- Çekim **manuel**: proje yenile, kart yenile, durum senkronu. `RefreshLog` tutulur.
- Çekilen: issueKey, summary, description, status, assignee, reporter, created, updated, sprint, epicLink, **blocks, blocked_by**.
- **Sprint yalnızca uygulama içi** — Jira sprint yazılmaz.
- **WRITE:** sadece kolon taşımasında, `sync_jira_status` + `transfer_to_jira` açıksa `transition_issue`.
- **Yazılmaz:** Jira atama, Jira yorum, Jira issue create (must-not / sonra).

## 6. Kanban Durumları (Kolonlar) ✅

- Uygulama kendi kolonlarını tutar (`kanban_columns`).
- Yeni durum: **admin + proje yöneticisi**.
- Eşleme ekranı (`/projects/<id>/statuses/`): çoklu map, primary, transfer toggle, gizli Jira durumları, isimle otomatik eşle, kolon sürükle-sırala.

## 6.5. Sprint Yönetimi (Uygulama İçi) ✅

- `sprints` + kart `sprint` FK. Jira sprint alanı sadece snapshot.
- Detay: başlangıç, süre, ekip (M2M), status planning/active/completed.
- **Model A:** yönetici atar. **Model B:** programcı self-assign. Programcı işi **bırakamaz**.
- Sprint board'da **blocked_by** uyarısı (tamamlanmamış bloklayan iş).
- Zorluk yoksa sprinte eklerken uyarı (form sprint seçiliyse zorluk zorunlu).
- **Kalan:** “onay olmadan sprint girişine izin yok” kapısı yok — kart doğrudan eklenebiliyor.

## 6.6. Sprint Kapasitesi & Zorluk Hesaplama ✅

- Kapasite: sprint `capacity` veya önceki completed sprint ortalaması (yoksa 40).
- Grafik + rakam; %75 altı uyarı, %100 üstü danger.
- Aşıma izin var, kaydetmede uyarı.

## 7. Kartlar ✅

- **1 kart = 1 Jira issue** — formda `jira_key` zorunlu (sub-task hariç).
- **Ek kart (Jira'sız):** genel formda yok. İstisna: ticket → kart dönüşümü `is_extra=True`.
- **Jira'da issue açma:** yok (must-not).
- Kartlar `column_id` ile konumlanır; kolon içi sürükle-sırala anında JSON kaydeder.
- Kolon taşıma: Jira transition (koşullu) + Django messages. PLAN'daki “kaydetmeden önce sor + kırmızı hatalı özet rapor” **kısmi**.
- **Fibonacci:** 1, 2, 3, 5, 8, 13, 21, 34 (admin/PM max 34). Programcı talebiyle 55/89.
  - 34 seçimi etiket uyarısı (modal yok).
- **Zorluk talebi / split / reassign** (`issue_requests`) ✅ — onayda zorluk uygulanır / unassign / split ekranına gider.
- **Sub-task:** yerel çocuk kartlar; parent zorluk 0; sprint parent ile senkron. Gerçek Jira sub-task değil (`{parent}-subN` sentetik key).
- **CardComment:** yerel kart yorumu (yazar veya level ≤ 2 düzenler/siler).

## 8. Kişiye Özel Dashboard ✅

- Programcı: atanmış + atanmamış işler, **aktif** sprintler.
- Diğerleri: projeler, aktif/planning sprintler, bekleyen talepler.
- **Kalan:** PLAN “programcı gelecek/planning sprint göremez” — dashboard hâlâ planning sprint sorguluyor.

**Raporlama:** ✅ proje + sprint Chart.js, CSV export, yöneticiye difficulty drift.

## 8.5 PLAN dışı uygulanan özellikler

- **Temalar** — admin CRUD, header'dan kullanıcı seçimi, CSS değişkenleri (`base.html`).
- **Hata & Talepler** — global/proje ticket, yorum, ek, durum, atama, ticket → kanban kart.
- **Dashboard özeti & son aktiviteler** — üst özet şeridi (toplam iş / aktif sprint / tamamlanan / devam eden / geciken) + `ActivityLog` tabanlı saatli akış (ticket #4, #5).
- **Sprint tarihleri** — `start_date` + süre → `end_date` / `days_left` / `is_overdue`, kartlarda "kalan gün / gecikme" rozeti (ticket #6).
- **Kart sayaçları** — proje ve sprint kartlarında toplam / tamamlanan / devam eden / yapılacak dağılımı (`classify_card_counts`) (ticket #7).
- **Jira wiki markup** — `kanbanapp/templatetags/jira_filters.py`.
- **Favicon** — `kanbanapp/static/favicon.ico`.

## 9. Deploy (LAN) ✅

- Docker Compose: `db` (postgres:16), `web` (gunicorn:8000), `nginx` (1.27, host **8008**).
- `.env` ile host/port. Yerel: SQLite + `DEBUG=True`.
- Credential yedekleme: Jira şifreleri DB'de Fernet; key `ENCRYPTION_KEY`.

## 10. Uygulama Fazları

**Faz 1 — Temel** ✅
- Django iskelet, Docker, migration
- Auth (login / admin-only register), 5 rol

**Faz 2 — Proje & Jira** ✅
- Proje CRUD, üyelik
- Jira bağlantısı + şifreleme, test, durum senkronu
- Manuel yenile + JQL import + kart yenile
- Opsiyonel Jira durum geçişi

**Faz 3 — Kanban Core** ✅
- Kolon, eşleme konsolu, kart CRUD
- Sprint, Fibonacci, issue request, split/sub-task, atama
- Kart yorumu

**Faz 4 — Raporlama** ✅
- Proje/sprint Chart.js, CSV
- Filtreler hafif (proje/sprint kapsamı; zengin filtre UI yok)

**Faz 5 — Polishing** 🟡 kısmi
- Birim testleri var (`kanbanapp/tests.py`)
- Yapıldı: doküman senkronu (README/AGENTS/footer “READ-ONLY”/“Faz 2+” ifadeleri giderildi), gunicorn `requirements.txt`'e eklendi, `JiraCustomStatus` ölü modeli kaldırıldı (0017)
- Kalan: HTMX yok (bkz. §11), ayrı JS dosyası yok (inline script), `JiraCustomStatus` hariç ölü `RefreshLog`/`IssueRequest` tabloları

## 11. Bilinen sapmalar / sonraki iş

| Konu | Plan | Gerçek | Aksiyon |
|------|------|--------|---------|
| Jira WRITE | durum + atama + yorum | sadece transition | Spec'i mevcut davranışa kilitle veya atama/yorum yaz |
| project_groups | grup ACL | yok | İstenirse Faz 5+ |
| Extra kart / Jira issue create | must-not | extra sadece ticket→kart | Bilinçli istisna |
| Sprint onay kapısı | zorunlu | yok | İstenirse ekle |
| Programcı planning sprint | göremez | dashboard'da görünüyor | Filtrele |
| HTMX | stack'te | kullanılmıyor | Çıkar veya ekle |
| Tek container | evet | 3 servis | Spec güncellendi |
| `@role_required` | middleware dekoratör | view `_can_*` | Belgeyi koda uydur |
| Favicon | — | `kanbanapp/static/favicon.ico` | ✅ |
