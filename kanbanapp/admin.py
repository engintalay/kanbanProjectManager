from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import JiraConnection, JiraCustomStatus, JiraIssue, JiraStatus, KanbanColumn, KanbanCard, Project, RefreshLog, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "level", "description")
    ordering = ("level",)
    search_fields = ("name", "slug")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "role", "project", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "role", "project")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("username", "email", "password")}),
        ("Kişisel Bilgiler", {"fields": ("first_name", "last_name")}),
        ("Roller ve Projeler", {"fields": ("role", "project", "is_active", "is_staff")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "role"),
        }),
    )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "jira_connection", "created_by", "created_at")
    search_fields = ("key", "name")
    list_filter = ("created_by",)


@admin.register(JiraConnection)
class JiraConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "username", "is_default", "created_by", "created_at")
    search_fields = ("name", "host", "username")
    list_filter = ("is_default",)


@admin.register(JiraIssue)
class JiraIssueAdmin(admin.ModelAdmin):
    list_display = ("jira_key", "project", "status_key", "assignee", "pulled_at")
    list_filter = ("project",)
    search_fields = ("jira_key", "summary")
    readonly_fields = ("jira_id", "jira_key", "status_id", "pulled_at")


@admin.register(JiraStatus)
class JiraStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "jira_status_key", "jira_id")
    search_fields = ("name", "jira_status_key")


@admin.register(JiraCustomStatus)
class JiraCustomStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "position")
    list_filter = ("project",)


@admin.register(KanbanColumn)
class KanbanColumnAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status_type", "position")
    list_filter = ("status_type", "project")


@admin.register(KanbanCard)
class KanbanCardAdmin(admin.ModelAdmin):
    list_display = ("title", "column", "project", "jira_key", "is_extra")
    list_filter = ("column", "project", "is_extra")
    search_fields = ("title", "jira_key")
    readonly_fields = ("jira_issue_id", "jira_key", "created_at", "updated_at")


@admin.register(RefreshLog)
class RefreshLogAdmin(admin.ModelAdmin):
    list_display = ("project", "jira_connection", "status", "pulled_count", "timestamp")
    list_filter = ("status", "project")
    search_fields = ("project__key", "error")
