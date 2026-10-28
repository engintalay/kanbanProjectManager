from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .fields import EncryptedCharField


class Role(models.Model):
    """A role with a hierarchical level (1 = admin = most power)."""

    LEVEL_ADMIN = 1
    LEVEL_PROJECT_MANAGER = 2
    LEVEL_PROGRAMMER = 3
    LEVEL_REPORTER = 4
    LEVEL_VIEWER = 5

    ADMIN = LEVEL_ADMIN
    PROJECT_MANAGER = LEVEL_PROJECT_MANAGER
    PROGRAMMER = LEVEL_PROGRAMMER
    REPORTER = LEVEL_REPORTER
    VIEWER = LEVEL_VIEWER

    level_choices = [
        (ADMIN, "Admin"),
        (PROJECT_MANAGER, "Proje Yöneticisi"),
        (PROGRAMMER, "Proje Programcısı"),
        (REPORTER, "Raportör"),
        (VIEWER, "İzleyici"),
    ]

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    level = models.SmallIntegerField(choices=level_choices, default=LEVEL_ADMIN)
    description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.name


def ensure_default_roles():
    """Ensure default roles exist in the database."""
    default_roles = [
        ("Admin", "admin", Role.LEVEL_ADMIN, "Tam yetkili sistem yöneticisi"),
        ("Proje Yöneticisi", "proje-yoneticisi", Role.LEVEL_PROJECT_MANAGER, "Proje ve sprint yönetimi"),
        ("Proje Programcısı", "proje-programcisi", Role.LEVEL_PROGRAMMER, "Kart atama ve geliştirme"),
        ("Raportör", "raportor", Role.LEVEL_REPORTER, "İzleme ve rapor oluşturma"),
        ("İzleyici", "izleyici", Role.LEVEL_VIEWER, "Salt okunur izleme"),
    ]
    for name, slug, level, desc in default_roles:
        Role.objects.get_or_create(
            name=name,
            defaults={"slug": slug, "level": level, "description": desc},
        )


class User(AbstractUser):
    # Required when extending the built-in auth.User model.
    parent_link = True

    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, related_name="users", default=None, blank=True, null=True
    )
    project = models.ForeignKey(
        "Project", on_delete=models.SET_NULL, related_name="members",
        blank=True, null=True, default=None,
    )
    theme = models.ForeignKey(
        "Theme", on_delete=models.SET_NULL, related_name="users",
        blank=True, null=True, default=None,
    )
    is_active = models.BooleanField(default=True)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_level(self):
        if getattr(self, "is_superuser", False):
            return Role.ADMIN
        if self.role_id:
            return self.role.level
        return Role.ADMIN

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.project_id:
            try:
                self.project_memberships.get_or_create(project_id=self.project_id)
            except Exception:
                pass


class Project(models.Model):
    name = models.CharField(max_length=200)
    key = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, default="")
    jira_connection = models.ForeignKey(
        "JiraConnection", on_delete=models.SET_NULL, related_name="projects",
        blank=True, null=True, default=None,
    )
    sync_jira_status = models.BooleanField(
        default=True,
        verbose_name="Jira Statü Aktarımı",
        help_text="Kart hareketlerinde Jira üzerindeki statünün de güncellenmesini sağlar. Kapatılırsa durum Jira'ya aktarılmaz.",
    )
    hidden_jira_statuses = models.ManyToManyField(
        "JiraStatus",
        blank=True,
        related_name="hidden_in_projects",
        verbose_name="Gizlenen Jira Statüleri",
        help_text="Bu proje için kullanılmayan ve gizlenen Jira statüleri.",
    )
    default_jql = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Varsayılan JQL Sorgusu",
        help_text="Yeni kart ekleme/arama ekranında otomatik çalıştırılacak varsayılan JQL sorgusu. Boş bırakılırsa 'project = \"KEY\"' kullanılır.",
    )
    jql_max_results = models.PositiveIntegerField(
        default=100,
        verbose_name="Maksimum JQL Kayıt Sayısı",
        help_text="JQL aramasında Jira'dan çekilecek maksimum kayıt sayısı (varsayılan: 100).",
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="created_projects",
        blank=True, null=True, default=None,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        verbose_name_plural = "projects"

    def __str__(self):
        return f"{self.key} - {self.name}"

    def get_default_jql(self):
        query = (self.default_jql or "").strip()
        if query:
            return query
        return f'project = "{self.key}"' if self.key else ""

    def get_effective_max_results(self):
        try:
            val = int(self.jql_max_results)
            if val > 0:
                return min(val, 500)
        except (ValueError, TypeError):
            pass
        return 100

    def has_member(self, user):
        if not user or not user.is_authenticated:
            return False
        if self.created_by_id == user.id:
            return True
        if getattr(user, "project_id", None) == self.id:
            return True
        return self.project_members.filter(user_id=user.id).exists()

    def delete(self, *args, **kwargs):
        from django.db import transaction

        with transaction.atomic():
            self.cards.all().delete()
            self.status_mappings.all().delete()
            self.columns.all().delete()
            return super().delete(*args, **kwargs)


class JiraConnection(models.Model):
    name = models.CharField(max_length=200)
    host = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    password = EncryptedCharField(max_length=512, default="")
    disable_proxy = models.BooleanField(
        default=True,
        verbose_name="Proxy Devre Dışı",
        help_text="Yerel ağ veya doğrudan bağlantılar için proxy kullanımını kapatır.",
    )
    is_default = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="created_jira_connections",
        blank=True, null=True, default=None,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.host})"

    @property
    def is_valid(self):
        return bool(self.host) and bool(self.username) and bool(self.password)


class JiraStatus(models.Model):
    """A status imported from Jira."""

    jira_status_key = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=200)
    color = models.JSONField(default=dict, blank=True)
    jira_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.name


class KanbanColumn(models.Model):
    """A column (status) on the kanban board.

    status_type: 'jira' = derived from Jira, 'custom' = app-defined extra status.
    """

    JIRA = "jira"
    CUSTOM = "custom"

    status_type = models.CharField(max_length=10, choices=[(JIRA, "Jira"), (CUSTOM, "Custom")])
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="columns"
    )
    name = models.CharField(max_length=200)
    color = models.JSONField(default=dict, blank=True)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


FIBONACCI_DIFFICULTIES = [
    (1, "1 - Çok Kolay"),
    (2, "2 - Kolay"),
    (3, "3 - Orta (3)"),
    (5, "5 - Orta (5)"),
    (8, "8 - Zor"),
    (13, "13 - Çok Zor"),
    (21, "21 - Aşırı Zor"),
    (34, "34 - Kritik (Bölünmeli)"),
    (55, "55 - Programcı Talebi (55)"),
    (89, "89 - Programcı Talebi (89)"),
]

DIFFICULTY_COLORS = {
    1: "#10b981",
    2: "#10b981",
    3: "#f59e0b",
    5: "#ea580c",
    8: "#ef4444",
    13: "#b91c1c",
    21: "#8b5cf6",
    34: "#18181b",
    55: "#4c1d95",
    89: "#09090b",
}

DIFFICULTY_LABELS = {
    1: "Çok Kolay",
    2: "Kolay",
    3: "Orta",
    5: "Orta",
    8: "Zor",
    13: "Çok Zor",
    21: "Aşırı Zor",
    34: "Kritik",
    55: "Aşırı Zor (55)",
    89: "Aşırı Zor (89)",
}


class Sprint(models.Model):
    DURATION_1_WEEK = "1_hafta"
    DURATION_2_WEEKS = "2_hafta"
    DURATION_3_WEEKS = "3_hafta"
    DURATION_4_WEEKS = "4_hafta"
    DURATION_FREE = "serbest"

    DURATION_CHOICES = [
        (DURATION_1_WEEK, "1 Hafta"),
        (DURATION_2_WEEKS, "2 Hafta"),
        (DURATION_3_WEEKS, "3 Hafta"),
        (DURATION_4_WEEKS, "4 Hafta"),
        (DURATION_FREE, "Serbest"),
    ]

    STATUS_PLANNING = "planning"
    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_PLANNING, "Planlama"),
        (STATUS_ACTIVE, "Aktif"),
        (STATUS_COMPLETED, "Tamamlandı"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES, default=DURATION_2_WEEKS)
    capacity = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Kapasite (Puan)",
        help_text="Sprint için hedeflenen toplam kapasite / hacim puanı (boş bırakılırsa geçmiş ortalama baz alınır)",
    )
    team_members = models.ManyToManyField(User, blank=True, related_name="sprints")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNING)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "-created_at"]

    def __str__(self):
        return f"{self.project.key} - {self.name} ({self.get_status_display()})"

    @property
    def total_difficulty(self):
        """Sum of difficulty_level for all cards in this sprint."""
        cards = self.cards.all()
        return sum(c.difficulty_level or 0 for c in cards)

    @property
    def has_custom_capacity(self):
        """Returns True if this sprint has an explicitly set numerical capacity."""
        return bool(self.capacity is not None and self.capacity > 0)

    @property
    def default_capacity(self):
        """Kapasite hedefi: Manuel kapasite girilmişse doğrudan o değer, girilmemişse geçmiş tamamlanan sprintlerin ortalaması veya 40."""
        if self.capacity is not None and self.capacity > 0:
            return self.capacity
        prev = Sprint.objects.filter(project=self.project, status=Sprint.STATUS_COMPLETED).exclude(id=self.id)
        if prev.exists():
            totals = [s.total_difficulty for s in prev if s.total_difficulty > 0]
            if totals:
                return round(sum(totals) / len(totals))
        return 40

    @property
    def capacity_percentage(self):
        cap = self.default_capacity
        if cap <= 0:
            return 0
        return round((self.total_difficulty / cap) * 100)

    @property
    def is_under_capacity(self):
        return self.capacity_percentage < 75

    @property
    def is_over_capacity(self):
        return self.capacity_percentage > 100

    @property
    def completed_cards(self):
        """Cards in this sprint whose column signifies completion."""
        done_keywords = ("done", "tamamlandı", "tamamlandi", "bitti", "closed", "kapalı", "kapali", "resolved", "çözüldü", "cozuldu")
        return [c for c in self.cards.select_related("column") if any(k in c.column.name.lower() for k in done_keywords)]

    @property
    def completed_cards_count(self):
        return len(self.completed_cards)

    @property
    def total_cards_count(self):
        return self.cards.count()

    @property
    def completed_difficulty(self):
        """Sum of difficulty_level for completed cards in this sprint."""
        return sum(c.difficulty_level or 0 for c in self.completed_cards)

    @property
    def completion_percentage(self):
        """Bitme / Tamamlanma Oranı (0 - 100)."""
        if self.total_difficulty > 0:
            return round((self.completed_difficulty / self.total_difficulty) * 100)
        if self.total_cards_count > 0:
            return round((self.completed_cards_count / self.total_cards_count) * 100)
        return 0

    @property
    def load_progress_class(self):
        """Doluluk oranı için CSS sınıfı: Yeşil ASLA kullanılmaz (Mavi/Sarı/Kırmızı)."""
        if self.is_over_capacity:
            return "progress-load-danger"
        elif self.is_under_capacity:
            return "progress-load-warn"
        return "progress-load-normal"


class KanbanCard(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="cards"
    )
    column = models.ForeignKey(
        KanbanColumn, on_delete=models.CASCADE, related_name="cards"
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default="")
    jira_issue_id = models.IntegerField(null=True, blank=True, db_index=True)
    jira_key = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    is_extra = models.BooleanField(default=False, help_text="Jira issue'ye bağlı olmayan kart")
    position = models.IntegerField(default=0)

    # Fibonacci Zorluk Seviyeleri (PLAN.md §7)
    difficulty_level = models.IntegerField(null=True, blank=True, choices=FIBONACCI_DIFFICULTIES)
    initial_difficulty_level = models.IntegerField(null=True, blank=True)
    requested_difficulty_level = models.IntegerField(null=True, blank=True)
    developer_assessment = models.TextField(blank=True, default="")

    # Sub-task yönetimi (PLAN.md §7)
    parent_card = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="sub_tasks"
    )
    is_sub_task = models.BooleanField(default=False)

    # Atama ve Sprint (PLAN.md §6.5 & §8)
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_cards"
    )
    sprint = models.ForeignKey(
        Sprint, on_delete=models.SET_NULL, null=True, blank=True, related_name="cards"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title

    @property
    def difficulty_color(self):
        if self.difficulty_level:
            return DIFFICULTY_COLORS.get(self.difficulty_level, "#6b7280")
        return "#9ca3af"

    @property
    def difficulty_label(self):
        if self.difficulty_level:
            return DIFFICULTY_LABELS.get(self.difficulty_level, str(self.difficulty_level))
        return "Belirlenmedi"

    @property
    def has_sub_tasks(self):
        return self.sub_tasks.exists()

    @property
    def completed_sub_tasks_count(self):
        done_keywords = ("done", "tamamlandı", "tamamlandi", "bitti", "closed", "kapalı", "kapali", "resolved", "çözüldü", "cozuldu")
        return sum(1 for s in self.sub_tasks.all() if any(k in s.column.name.lower() for k in done_keywords))

    def clean(self):
        super().clean()
        if self.sprint and self.project_id and self.sprint.project_id != self.project_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("Sprint kartın projesine ait olmalıdır.")

    def save(self, *args, **kwargs):
        if self.sprint_id and self.project_id and self.sprint.project_id != self.project_id:
            from django.core.exceptions import ValidationError
            raise ValidationError("Sprint kartın projesine ait olmalıdır.")
        if self.parent_card_id:
            self.is_sub_task = True
        super().save(*args, **kwargs)
        # Eğer bu bir ana iş ise ve alt görevleri varsa, sprint atamasını alt görevlere de aktar
        if not self.is_sub_task and self.id:
            sub_tasks_to_sync = self.sub_tasks.exclude(sprint_id=self.sprint_id)
            if sub_tasks_to_sync.exists():
                sub_tasks_to_sync.update(sprint=self.sprint)


class CardComment(models.Model):
    """Jira işleri / Kanban kartları altında birden fazla değerlendirme ve yorum."""

    card = models.ForeignKey(KanbanCard, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="card_comments")
    comment = models.TextField(verbose_name="Değerlendirme / Yorum")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Kart Değerlendirmesi / Yorumu"
        verbose_name_plural = "Kart Değerlendirmeleri / Yorumları"

    def __str__(self):
        return f"{self.author.username} - {self.card.title} ({self.created_at:%Y-%m-%d %H:%M})"

    def can_edit(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        if self.author_id == user.id:
            return True
        # Yöneticiler (Admin veya Proje Yöneticisi: role_level <= 2)
        if getattr(user, "role_level", 99) <= 2:
            return True
        return False

    def can_delete(self, user):
        return self.can_edit(user)


class IssueRequest(models.Model):
    TYPE_DIFFICULTY = "difficulty_change"
    TYPE_SPLIT = "split"
    TYPE_REASSIGN = "reassign"

    TYPE_CHOICES = [
        (TYPE_DIFFICULTY, "Zorluk Değişikliği"),
        (TYPE_SPLIT, "İş Bölme (Sub-task)"),
        (TYPE_REASSIGN, "Yeniden Atama"),
    ]

    REASON_TOO_HARD = "too_hard"
    REASON_TOO_EASY = "too_easy"

    REASON_CHOICES = [
        (REASON_TOO_HARD, "Çok Zor Geldi"),
        (REASON_TOO_EASY, "Çok Kolay Geldi"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Bekliyor"),
        (STATUS_APPROVED, "Onaylandı"),
        (STATUS_REJECTED, "Reddedildi"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="issue_requests")
    card = models.ForeignKey(KanbanCard, on_delete=models.CASCADE, related_name="requests")
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_DIFFICULTY)
    reason = models.CharField(max_length=30, blank=True, choices=REASON_CHOICES)
    requested_difficulty = models.IntegerField(null=True, blank=True, choices=FIBONACCI_DIFFICULTIES)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_requests")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="handled_requests")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.card.title} - {self.get_type_display()} ({self.get_status_display()})"


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="project_members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_user_member"),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.project.key}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.user_id and not getattr(self.user, "project_id", None):
            User.objects.filter(id=self.user_id, project__isnull=True).update(project=self.project)


class StatusMapping(models.Model):
    """Maps an application KanbanColumn (app status) to a Jira status.

    Created by admin / project manager (PLAN.md §6). For 'jira'-type columns the
    jira_status is expected; for 'custom' columns it is optional.
    """

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="status_mappings"
    )
    app_status = models.ForeignKey(
        KanbanColumn, on_delete=models.CASCADE, related_name="status_mappings"
    )
    jira_status = models.ForeignKey(
        JiraStatus, on_delete=models.SET_NULL, related_name="app_mappings",
        null=True, blank=True, default=None,
    )
    transfer_to_jira = models.BooleanField(
        default=True,
        verbose_name="Jira'ya Statü Aktar",
        help_text="Kart bu kolona taşındığında Jira'da ilgili statüye geçiş yapılır. Kapatılırsa bu kolon için Jira statüsü aktarılmaz.",
    )
    is_primary = models.BooleanField(
        default=True,
        verbose_name="Birincil Geçiş Statüsü",
        help_text="Kart bu kolona taşındığında Jira'da geçilecek birincil durum.",
    )
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Durum Eşlemesi"
        verbose_name_plural = "Durum Eşlemeleri"
        constraints = [
            models.UniqueConstraint(fields=["app_status", "jira_status"], name="unique_app_jira_status"),
        ]

    def __str__(self):
        jira = self.jira_status.name if self.jira_status else "(mape edilmemiş)"
        return f"{self.app_status.name} → {jira}"


class JiraIssue(models.Model):
    """A Jira issue pulled into this application (READ-ONLY snapshot)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="jira_issues"
    )
    jira_id = models.CharField(max_length=50, db_index=True)
    jira_key = models.CharField(max_length=50, db_index=True)
    summary = models.CharField(max_length=1000, default="")
    description = models.TextField(blank=True, default="")
    status_id = models.IntegerField(null=True, blank=True, db_index=True)
    status_key = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    assignee = models.CharField(max_length=255, null=True, blank=True)
    reporter = models.CharField(max_length=255, null=True, blank=True)
    created = models.CharField(max_length=100, null=True, blank=True)
    updated = models.CharField(max_length=100, null=True, blank=True)
    sprint = models.CharField(max_length=255, null=True, blank=True)
    epic_key = models.CharField(max_length=100, null=True, blank=True)
    blocks = models.JSONField(default=list, blank=True)
    blocked_by = models.JSONField(default=list, blank=True)
    pulled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["jira_key"]
        constraints = [
            models.UniqueConstraint(fields=["project", "jira_id"], name="unique_project_jira_id"),
        ]

    def __str__(self):
        return f"{self.project.key}:{self.jira_key}"


class RefreshLog(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="refresh_logs"
    )
    jira_connection = models.ForeignKey(
        JiraConnection, on_delete=models.SET_NULL, related_name="refresh_logs",
        null=True, blank=True, default=None,
    )
    status = models.CharField(max_length=20, choices=[
        ("success", "Başarılı"),
        ("failed", "Başarısız"),
    ])
    pulled_count = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.project.key} - {self.status} @ {self.timestamp:%Y-%m-%d %H:%M}"


class ProjectTicket(models.Model):
    """Hata bildirimi (bug) veya yeni geliştirme isteği (feature request)."""

    TYPE_BUG = "bug"
    TYPE_FEATURE = "feature"
    TYPE_IMPROVEMENT = "improvement"

    TYPE_CHOICES = [
        (TYPE_BUG, "Hata Bildirimi (Bug)"),
        (TYPE_FEATURE, "Yeni Geliştirme İsteği (Feature)"),
        (TYPE_IMPROVEMENT, "İyileştirme / Revizyon"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Düşük"),
        (PRIORITY_MEDIUM, "Normal"),
        (PRIORITY_HIGH, "Yüksek"),
        (PRIORITY_URGENT, "Acil / Kritik"),
    ]

    STATUS_OPEN = "open"
    STATUS_INVESTIGATING = "investigating"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Açık"),
        (STATUS_INVESTIGATING, "İnceleniyor"),
        (STATUS_IN_PROGRESS, "Geliştirmede"),
        (STATUS_RESOLVED, "Çözüldü"),
        (STATUS_CLOSED, "Kapatıldı"),
        (STATUS_REJECTED, "Reddedildi"),
    ]

    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    ticket_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_BUG)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)

    # İşi Açan (Talep Sahibi)
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reported_tickets")
    # İşi Yapan / Geliştirici (Atanan Kişi)
    assignee = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets"
    )

    # İlgili Kanban Kartı (Geliştirme takibinin panodan izlenmesi için)
    card = models.ForeignKey(
        KanbanCard, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )

    resolution_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hata / Talep"
        verbose_name_plural = "Hatalar ve Talepler"

    def __str__(self):
        prefix = self.project.key if self.project else "KPM"
        return f"[{prefix}-T{self.id}] {self.title}"

    @property
    def ticket_code(self):
        prefix = self.project.key if self.project else "KPM"
        return f"{prefix}-T{self.id}"

    @property
    def is_bug(self):
        return self.ticket_type == self.TYPE_BUG

    @property
    def is_feature(self):
        return self.ticket_type == self.TYPE_FEATURE

    @property
    def is_closed_or_resolved(self):
        return self.status in (self.STATUS_RESOLVED, self.STATUS_CLOSED, self.STATUS_REJECTED)

    @property
    def priority_color(self):
        colors = {
            self.PRIORITY_LOW: "#10b981",
            self.PRIORITY_MEDIUM: "#3b82f6",
            self.PRIORITY_HIGH: "#f59e0b",
            self.PRIORITY_URGENT: "#ef4444",
        }
        return colors.get(self.priority, "#6b7280")

    @property
    def status_color(self):
        colors = {
            self.STATUS_OPEN: "#3b82f6",
            self.STATUS_INVESTIGATING: "#8b5cf6",
            self.STATUS_IN_PROGRESS: "#f59e0b",
            self.STATUS_RESOLVED: "#10b981",
            self.STATUS_CLOSED: "#6b7280",
            self.STATUS_REJECTED: "#ef4444",
        }
        return colors.get(self.status, "#6b7280")


class TicketAttachment(models.Model):
    """Talebe eklenen resim veya dosyalar."""

    ticket = models.ForeignKey(ProjectTicket, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="ticket_attachments/%Y/%m/")
    filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_ticket_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Talep Eki"
        verbose_name_plural = "Talep Ekleri"

    def __str__(self):
        return self.filename or str(self.file.name)

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            import os
            self.filename = os.path.basename(self.file.name)
        if self.file and hasattr(self.file, "size"):
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def is_image(self):
        import os
        ext = os.path.splitext(self.filename or self.file.name)[1].lower()
        return ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"]

    @property
    def file_size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"


class TicketComment(models.Model):
    """Talebin altındaki yorumlar ve işi açan ile yapan arasındaki mesajlar."""

    ticket = models.ForeignKey(ProjectTicket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticket_comments")
    message = models.TextField()
    attachment = models.FileField(upload_to="ticket_comment_attachments/%Y/%m/", null=True, blank=True)
    is_system_note = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Talep Yorumu / Mesajı"
        verbose_name_plural = "Talep Yorumları / Mesajları"

    def __str__(self):
        return f"{self.author.username} - {self.ticket}"

    @property
    def is_reporter(self):
        return self.ticket.reporter_id == self.author_id

    @property
    def is_assignee(self):
        return self.ticket.assignee_id == self.author_id

    @property
    def author_badge_label(self):
        if self.is_system_note:
            return "Sistem Bildirimi"
        if self.is_reporter and self.is_assignee:
            return "İşi Açan & Yapan"
        if self.is_reporter:
            return "İşi Açan"
        if self.is_assignee:
            return "İşi Yapan / Geliştirici"
        if hasattr(self.author, "role") and self.author.role:
            return self.author.role.name
        return "Üye"

    @property
    def attachment_is_image(self):
        if not self.attachment:
            return False
        import os
        ext = os.path.splitext(self.attachment.name)[1].lower()
        return ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"]


class Theme(models.Model):
    name = models.CharField(max_length=100, verbose_name="Tema Adı")
    code = models.SlugField(max_length=50, unique=True, verbose_name="Tema Kodu")
    is_active = models.BooleanField(default=True, verbose_name="Aktif")
    is_default = models.BooleanField(default=False, verbose_name="Varsayılan Tema")

    # CSS Variables (hex / rgba)
    bg_color = models.CharField(max_length=30, default="#0f172a", verbose_name="Arka Plan (--bg)")
    bg_soft = models.CharField(max_length=30, default="#1e293b", verbose_name="Yumuşak Arka Plan (--bg-soft)")
    card_bg = models.CharField(max_length=30, default="#1e293b", verbose_name="Kart Arka Planı (--card)")
    card_hover = models.CharField(max_length=30, default="#243449", verbose_name="Kart Hover (--card-hover)")
    border_color = models.CharField(max_length=30, default="#334155", verbose_name="Kenarlık (--border)")
    text_color = models.CharField(max_length=30, default="#e2e8f0", verbose_name="Metin Rengi (--text)")
    text_muted = models.CharField(max_length=30, default="#94a3b8", verbose_name="Soluk Metin (--muted)")
    primary_color = models.CharField(max_length=30, default="#6366f1", verbose_name="Birincil Renk (--primary)")
    primary_hover = models.CharField(max_length=30, default="#4f46e5", verbose_name="Birincil Hover (--primary-hover)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name = "Tema"
        verbose_name_plural = "Temalar"

    def __str__(self):
        return f"{self.name}{' (Varsayılan)' if self.is_default else ''}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Theme.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


DEFAULT_THEMES = [
    {
        "name": "Karanlık (Varsayılan)",
        "code": "dark",
        "is_active": True,
        "is_default": True,
        "bg_color": "#0f172a",
        "bg_soft": "#1e293b",
        "card_bg": "#1e293b",
        "card_hover": "#243449",
        "border_color": "#334155",
        "text_color": "#e2e8f0",
        "text_muted": "#94a3b8",
        "primary_color": "#6366f1",
        "primary_hover": "#4f46e5",
    },
    {
        "name": "Açık Tema",
        "code": "light",
        "is_active": True,
        "is_default": False,
        "bg_color": "#f8fafc",
        "bg_soft": "#f1f5f9",
        "card_bg": "#ffffff",
        "card_hover": "#f1f5f9",
        "border_color": "#cbd5e1",
        "text_color": "#0f172a",
        "text_muted": "#64748b",
        "primary_color": "#4f46e5",
        "primary_hover": "#4338ca",
    },
    {
        "name": "Gece Mavisi",
        "code": "midnight",
        "is_active": True,
        "is_default": False,
        "bg_color": "#0b1120",
        "bg_soft": "#0f172a",
        "card_bg": "#172554",
        "card_hover": "#1e3a8a",
        "border_color": "#1e3a8a",
        "text_color": "#f8fafc",
        "text_muted": "#93c5fd",
        "primary_color": "#38bdf8",
        "primary_hover": "#0284c7",
    },
    {
        "name": "Zümrüt Yeşil",
        "code": "emerald",
        "is_active": True,
        "is_default": False,
        "bg_color": "#064e3b",
        "bg_soft": "#065f46",
        "card_bg": "#047857",
        "card_hover": "#059669",
        "border_color": "#059669",
        "text_color": "#ecfdf5",
        "text_muted": "#a7f3d0",
        "primary_color": "#10b981",
        "primary_hover": "#059669",
    },
]


def ensure_default_themes():
    """Ensure default themes exist in the database."""
    for theme_data in DEFAULT_THEMES:
        Theme.objects.get_or_create(
            code=theme_data["code"],
            defaults=theme_data,
        )

