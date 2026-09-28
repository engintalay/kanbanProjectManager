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
    is_default = models.BooleanField(default=False)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


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
