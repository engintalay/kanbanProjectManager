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
    is_active = models.BooleanField(default=True)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_level(self):
        if self.role_id:
            return self.role.level
        return Role.ADMIN


class Project(models.Model):
    name = models.CharField(max_length=200)
    key = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, default="")
    jira_connection = models.ForeignKey(
        "JiraConnection", on_delete=models.SET_NULL, related_name="projects",
        blank=True, null=True, default=None,
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


class JiraCustomStatus(models.Model):
    """A custom status defined within this application (per project)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="custom_statuses"
    )
    name = models.CharField(max_length=200)
    color = models.JSONField(default=dict, blank=True)
    position = models.IntegerField(default=0)
    parent_status = models.ForeignKey(
        JiraStatus, on_delete=models.SET_NULL, related_name="custom_children",
        null=True, blank=True, default=None,
    )

    class Meta:
        ordering = ["position", "name"]

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
    def default_capacity(self):
        """Average difficulty of previous completed sprints in this project, or default 40."""
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


class KanbanCard(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="cards"
    )
    column = models.ForeignKey(
        KanbanColumn, on_delete=models.PROTECT, related_name="cards"
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
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Durum Eşlemesi"
        verbose_name_plural = "Durum Eşlemeleri"
        constraints = [
            models.UniqueConstraint(fields=["app_status"], name="unique_app_status"),
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
