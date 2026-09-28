# Kanban Proje Yönetim Sistemi — Plan

## 1. Özet

Yerel ağda (LAN) çalışan, **Python + Django** tabanlı, tek containerda deploy edilen web uygulaması. Jira Server/Data Center REST API'sine **READ-WRITE** olarak bağlanır: issue bilgileri çekilir (READ) ve **durum değiştirme, atama, yorum ekleme** gibi işlemler yapılır (WRITE). Kanban kartları uygulamanın kendi veritabanında takip edilir.

## 2. Teknoloji Stack

| Katman | Seçim | Neden |
|--------|-------|-------|
| Backend | **Django 5.x** (Python 3.12+) | Hazır auth, admin, ORM; hızlı CRUD |
| DB | PostgreSQL | İlişkisel veri, Jira referansları, JSON kolon desteği |
| Frontend | Django Templates + HTMX + Chart.js | Server-render, minimal JS, tek container |
| Jira SDK | `jira` resmi kütüphane + `requests` | REST API okuma (READ-ONLY) |
| Deploy | Docker + docker-compose (Gunicorn + Nginx + Postgres) | LAN deploy kolay |

## 3. Veritabanı Şeması

- **users** — id, name, email, password, role, project(optional), timestamps
- **roles** — id, name, slug, level(1-5), permissions
- **projects** — id, name, key, description, jira_connection(optional), created_by (uygulama projesi, Jira projesinden bağımsız)
- **project_issues** — id, project, jira_issue_id, jira_key (JQL sorgusu / issue ID'den seçilen issue'lar)
- **project_members** — id, project, user, timestamps (proje erişimi; tek kullanıcı projeleri için)
- **project_groups** — id, project, group, position (grup bazlı proje dahil etme)
- **jira_connections** — id, project(optional), host, username, password(enc), is_default
- **jira_statuses** — id, jira_status_key, name, color, jira_id
- **jira_custom_statuses** — id, project, name, color, position
- **kanban_columns** — id, project, name, position, color, status_type(enum: jira/custom)
- **status_mappings** — id, project, app_status_id(kanban_columns), jira_status_id(jira_statuses), position (admin + proje yöneticisi tarafından)
- **kanban_cards** — id, project, column, title, description, jira_issue_id(optional), jira_key(optional), is_extra(bool), position, difficulty_level(admin/yönetici belirler, Fibonacci: 1/2/3/5/8/13/21/34/55/89; admin/yönetici **1-34** arası, programcı talep ile 55/89), initial_difficulty_level(atanan zorluk — kaydetme zorunlu), requested_difficulty_level(programcı talebi — kaydetme zorunlu), developer_assessment(geliştirici görüşü), parent_card_id(optional, sub_task için ana iş referansı), is_sub_task(bool), sprint_id(optional, uygulama içi sprint), timestamps
- **issue_requests** — id, project, card, type(enum: difficulty_change/split/reassign), reason(enum: too_hard/too_easy, difficulty_change için), description, status(enum: pending/approved/rejected), requested_by(geliştirici), assigned_to(yönetici/admin), timestamp
- **sprints** — id, project, name, position, start_date, duration(enum: 1_hafta/2_hafta/3_hafta/4_hafta/serbest), team_members(JSON, sprint dahil ekip), default_capacity(önceki sprint ortalama toplam zorluk), status, timestamps (uygulama içi sprint yönetimi)
- **sprint_assignments** — id, project, sprint, card, position (kartların uygulama içi sprint dağılımı)
- **refresh_logs** — id, project, status, pulled_count, error(optional), timestamp

## 4. Kimlik Doğrulama & Rol Yönetimi

**5 seviye hiyerarşik rol** (üst rol alt rol yetkilerini kapsar):

| Seviye | Rol | Yetkiler |
|--------|-----|----------|
| 1 | **Admin** | Tüm yetkiler (rol/proje/Jira bağlantısı/rapor) |
| 2 | **Proje Yöneticisi** | Kendi projesi: kart, kolon, durum, Jira yenileme, rapor |
| 3 | **Proje Programcısı** | Kendi projesi: kart oluşturma/düzenleme, görüntüleme |
| 4 | **Raportör** | Rapor/dashboard görüntüleme (tüm projeler), kart düzenleme YOK |
| 5 | **İzleyici** | Sadece görüntüleme |

**Proje Görünürlüğü (Erişim):**
- **Admin**: tüm projeleri görür.
- **Proje Yöneticisi**: kendisi oluşturduğu projeleri görür.
- **Kullanıcı (Programcı)**: sadece **tek kişilik** (yalnız kendisinin üyesi olduğu) projeleri görür.
- **Grup bazlı erişim**: kullanıcılar grup ile yönetilir; bir gruba verilen proje yetkisi, grup içindeki **tüm kullanıcıyı** ilgili projeye dahil eder (project_groups).

- **Kullanıcı kaydı SADECE admin** tarafından (Django admin + custom view).
- Django `Permission`/`Group` + custom middleware ile seviye bazlı kontrol.

## 5. Jira Entegrasyonu (READ-WRITE)

- **Uygulama projeleri Jira projelerinden bağımsızdır.** Uygulama içi projelere Jira issue'ları dahil edilir.
- **İş dahil etme**: Jira issue ID veya **JQL sorgusu** sonucu gelen kayıtlar arasında 1 ya da daha fazla seçim → seçilen issue'lar uygulamaya dahil edilir (project_issues).
- **Bir Jira issue birden fazla uygulama projesinde** olabilir.
- Credential yönetimi: **admin + proje yöneticisi**.
- **Çekim sadece manuel** ("Yenile" butonu) → seçili projenin Jira bağlantısı → issue'ları çeker.
- **Çekilen veriler**: issueKey, summary, description, status, assignee, reporter, created, updated, sprint, epicLink, **blocks, blocked_by** (bağlantı/ bağımlılık ilişkileri).
- **Sprint yönetimi yalnızca uygulama içindedir** — Jira tarafında sprint oluşturma/güncelleme/yenileme **YAPILMAZ**.
- **Jira READ-WRITE** — durum değiştirme, atama, yorum ekleme gibi yaz işlemleri de yapılır.
- Credential'lar veritabanında şifreli.
- **Yenileme logları** tutulur.

## 6. Kanban Durumları (Kolonlar)

- Uygulama **kendi durumlarını** takip eder (kanban_columns).
- Proje bazlı yeni durumlar eklenebilir (sadece **admin + proje yöneticisi**).
- Her yeni uygulama durumu için **Jira eşleme tablosu (status_mappings)** oluşturulur: uygulamanın kendi durumu ↔ Jira durumu eşleşmesi takibi yapılır.
- Uygulama kendi durumlarıyla takip ederken, Jira tarafındaki eşlenik durumu da bu eşleme üzerinden yönetir.

## 6.5. Sprint Yönetimi (Uygulama İçi)

- Sprint yönetimi **yalnızca uygulama içinde** yapılır (**sprints**, **sprint_assignments**). Jira tarafında sprint güncellemesi/eklemesi **yapılmaz**.
- Sprint detayları: **başlangıç tarihi**, **süre** (1/2/3/4 hafta veya serbest), **ekip** (sprint'e dahil üyeler).
- Kartlar uygulama içi sprinte eklenebilir. Kartların Jira sprint alanı dokunulmaz.
- **Sprint atama modelleri** (sprint başlatıldıktan sonra):
  - **Model A**: yönetici/admin, işleri programcılara atar (assign).
  - **Model B**: yetkili programcılar, istedikleri işleri **kendileri** alır (self-assign).
- **Bağımlılık uyarısı (blocks/blocked_by)**: iş gösterilirken blocks/blocked_by ilişkileri dikkate alınır; iş planlamasında uyarı verilir.
- **Bloklu iş uyarısı**: bir iş **blocked_by** ise ve bloklayan (blocks) iş tamamlanmamışsa, **sprint giriş aşamasında uyarı** verilir.
- **Onay zorunluluğu**: onaylanmadan **sprint girişine izin verilmez**. Onaydan sonra kart sprinte eklenir.
- Zorluk değeri olmayan bir karta sprinte eklenirken **zorunlu zorluk girişi** yapılır.

## 6.6. Sprint Kapasitesi & Zorluk Hesaplama

- **Varsayılan kapasite (önceki sprint ortalama)**: önceki sprintlerin toplam zorluk ortalamasına göre varsayılan toplam zorluk seviyesi gösterilir. Örnek: 10 adet zorluk 8'lik iş yapılmışsa varsayılan seviye **80** gösterilir.
- **Zorluk hesapla**: yan tarafta toplam zorluk hesaplanır; hem **grafiksel** (progress bar / kolay→zor ölçeği) hem **rakamsal** gösterim.
- **Renk değişimi**: seviye doldukça renkte değişir (boş → yeşil, doluğa yaklaşınca kırmızı).
- **Aşım uyarısı**: varsayılan seviyeyi aşmasına **izin verilir**; ancak **kaydetme sırasında uyarı** gösterilir.
- **Boş sprint uyarısı**: varsayılan seviyenin **%75 altında** kalınırsa uyarı verilir (sprint boş/eksik olduğu için).

## 7. Kartlar

- **1 kart = 1 Jira issue** (jira_issue_id + jira_key referanslı) — **zorunlu**.
- **Ek kartlar (Jira'dan bağımsız)** — **isteğe bağlı (must-not)**; Jira bağlantısı olmadan kart oluşturma. Geliştirme sonraya kalacak.
- **Yeni kart ile birlikte Jira'da issue açma** — **isteğe bağlı (must-not)**; uygulama içinden kart oluştururken Jira tarafında da yeni iş açılması. Geliştirme sonraya kalacak.
- Kartlar uygulamanın kendi **column_id**'sine göre konumlanır.
- **Kart sıralama (kanban ekranı)**: kartların ekran üzerinde yerlerini değiştirilebilir (drag). İşlem bittiğinde **kaydetmek isteyip istemediğini sorar**. Kaydet derse o zaman Jira tarafında gerekli işlemleri yapar (eşleme tablosu üzerinden durum/yaz güncellemesi). İşlemler tamamlandığında **özet rapor** verilir; **hatalar kırmızı ile işaretlenir**.
- **Zorluk Derecesi (Fibonacci)**: zorluk seviyeleri Fibonacci sayılarıdır — **1, 2, 3, 5, 8, 13, 21, 34** (admin/yönetici için en fazla 34, programcı talebiyle 55/89 dahil). Her seviyeye uygun renk atanır:

  | Zorluk | Renk | Kategori |
  |--------|------|----------|
  | 1 | Yeşil | Çok Kolay |
  | 2 | Yeşil | Kolay |
  | 3 | Açık Turuncu | Orta |
  | 5 | Turuncu | Orta |
  | 8 | Kırmızı | Zor |
  | 13 | Koyu Kırmızı | Çok Zor |
  | 21 | Mor | Aşırı Zor |
  | 34 | Siyah | Kritik |

  - **34 seçimi uyarı ister** — 34'lük işlerin nadiren olacağı için seçilirken uyarı gösterilir.
  - **34'lük işler bölünmeli** — yönetici/admin, 34 seviyesindeki işi birden fazla parçaya bölebilir.
- **Zorluk Değişikliği Talebi (programcı → yönetici/admin)**:
  - Programcı, atanmış zorluk seviyesi kendisi için **zor ya da kolay** geldiğinde değişiklik talep edebilir (issue_requests).
  - **Zor geldiğinde** Fibonacci 2 basamak daha yüksek seçenekler sunulur — **55 ve 89** (sadece programcı için).
  - **55 ve 89 seçenekleri proje yöneticisi/admin tarafından doğrudan belirlenemez** (seçenekler arasında yer almaz).
  - Talep geldiğinde **proje yöneticisi bilgilendirilir** (değerlendirme için); ana ekranda **uyarı** olarak görünür.
  - Değerlendirmeden sonra yönetici **iş başka bir programcıya aktarabilir** veya **işin parçalanmasını** talep edebilir.
  - **initial_difficulty_level** ve **requested_difficulty_level** kayıtlı tutulur; ileride yönetici/üstü seviye raporlarına dahil edilir. Diğer kullanıcılar bu detaya **erişemez**.
- **İş Bölme (Sub-task)**:
  - İş bölme durumunda (issue_requests: split) yeni işler **sub_task** olarak eklenir.
  - **Sub_task'ı olan bir ana iş, dağıtılacak işler listesinde yer almaz.**
  - Takip **sadece en alt seviye (yaprak/sub_task) işlerle** yapılır; sub_task'ı olmayan bir iş varsa bu iş üzerinden takip edilir.
  - Ana iş **taşınırken sub_tasklar da onunla birlikte taşınır**.
  - **Durum değişikliği uyarısı tüm sub_tasklar için** verilir.
  - Hem sub_task hem de ana iş için **kod geliştirmesi olamaz**.
  - Ana işin zorluk seviyesi bölünürken **0'a** düşürülür.

## 8. Kişiye Özel Dashboard

- Her kullanıcı için bir dashboard; **kullanıcı seviyesine göre farklı tasarım ve yetkilendirme**.

**Yetkilendirme matrisi:**
- **Proje Yöneticisi**: (yetki dahilinde) **tüm projeleri** görür, **bitme durumlarını** takip eder.
- **Programcı**:
  - Sadece **atanmış işler** üzerinde işlem yapar.
  - **Ataması yapılmamış işleri** üstüne alıp işlem yapabilir.
  - **İşi aldıysa bırakamaz** — işi bırakma yetkisi **sadece yönetici**'ye aittir.
  - Proje geneli **göremez**; **gelecek sprintler** hakkında bilgiye **ulaşamaz**.
- **Yönetici (Admin) ve üstü**:
  - **Gelecek sprintleri** görebilir.
  - İş atama/bırakma yetkisine sahiptir.

**Sprint görünürlüğü:**
- Programcı: sadece **başlatılmış sprintleri** görebilir.

**Raporlama**: daha sonra tasarlanacak.

## 9. Deploy (LAN)

- **Docker + docker-compose**, tek container (Nginx + Gunicorn + Postgres).
- `.env` ile host/port ayarı, LAN'da `http://<ip>:8000`.
- DB + credential yedekleme.

## 10. Uygulama Fazları (Django)

**Faz 1 — Temel**
- Django iskelet, Docker setup, migration
- Auth (login/admin-only), 5 rol + permission

**Faz 2 — Proje & Jira**
- Proje CRUD
- Jira bağlantısı (admin + yönetici), credential şifreleme
- Jira READ-ONLY çekme + yenile butonu

**Faz 3 — Kanban Core**
- Durum (Jira türevi + custom)
- Kolon, kart CRUD (Jira issue + ek kart)

**Faz 4 — Raporlama**
- Filtreli raporlar, CSV export, Chart.js

**Faz 5 — Polishing**
- Hata yönetimi, loglar, dokümantasyon
