from django import forms

from .models import (
    FIBONACCI_DIFFICULTIES,
    IssueRequest,
    JiraConnection,
    JiraIssue,
    JiraStatus,
    KanbanCard,
    KanbanColumn,
    Project,
    Sprint,
    StatusMapping,
    User,
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "key", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "key": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_key(self):
        key = self.cleaned_data.get("key", "").strip()
        qs = Project.objects.filter(key=key)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu proje anahtarı zaten kullanılıyor.")
        return key


class JiraConnectionForm(forms.ModelForm):
    class Meta:
        model = JiraConnection
        fields = ["name", "host", "username", "password", "disable_proxy", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "host": forms.TextInput(attrs={"class": "form-control", "placeholder": "https://jira.example.com"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "password": forms.PasswordInput(attrs={"class": "form-control"}, render_value=False),
            "disable_proxy": forms.CheckboxInput(),
            "is_default": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["password"].required = False
            self.fields["password"].help_text = "Mevcut şifreyi/token'ı korumak için boş bırakın."

    def clean_password(self):
        pw = self.cleaned_data.get("password")
        if not pw and self.instance and self.instance.pk:
            return self.instance.password
        return pw

    def clean_host(self):
        host = self.cleaned_data.get("host", "").rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            raise forms.ValidationError("Host bir URL olmalı (https://... ile başlatın).")
        return host


class KanbanColumnForm(forms.ModelForm):
    class Meta:
        model = KanbanColumn
        fields = ["name", "status_type", "color", "position"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "status_type": forms.Select(attrs={"class": "form-control"}),
            "color": forms.HiddenInput(),
            "position": forms.NumberInput(attrs={"class": "form-control"}),
        }

ADMIN_PM_DIFFICULTIES = [
    ("", "--- Zorluk Seçin ---"),
    (1, "1 - Çok Kolay"),
    (2, "2 - Kolay"),
    (3, "3 - Orta (3)"),
    (5, "5 - Orta (5)"),
    (8, "8 - Zor"),
    (13, "13 - Çok Zor"),
    (21, "21 - Aşırı Zor"),
    (34, "34 - Kritik (Uyarı: Bölünmeli)"),
]


class KanbanCardForm(forms.ModelForm):
    """Kanban card with Fibonacci difficulty, assignee, and sprint linking."""

    class Meta:
        model = KanbanCard
        fields = [
            "column",
            "title",
            "description",
            "difficulty_level",
            "assignee",
            "sprint",
            "jira_key",
            "developer_assessment",
            "is_extra",
        ]
        widgets = {
            "column": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "difficulty_level": forms.Select(choices=ADMIN_PM_DIFFICULTIES, attrs={"class": "form-control"}),
            "assignee": forms.Select(attrs={"class": "form-control"}),
            "sprint": forms.Select(attrs={"class": "form-control"}),
            "jira_key": forms.TextInput(attrs={"class": "form-control", "placeholder": "PROJ-123 (isteğe bağlı)"}),
            "developer_assessment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "is_extra": forms.CheckboxInput(),
        }

    def __init__(self, *args, project=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        proj = project or getattr(self.instance, "project", None)
        if proj:
            self.fields["column"].queryset = proj.columns.all().order_by("position", "name")
            self.fields["sprint"].queryset = proj.sprints.all().order_by("position", "-created_at")
            # Assignees: members of this project or superusers
            from django.db.models import Q
            self.fields["assignee"].queryset = User.objects.filter(
                Q(project=proj) | Q(created_projects=proj) | Q(is_superuser=True)
            ).distinct().order_by("username")

        # Programmer restrictions (PLAN.md §8):
        if user and getattr(user, "role_level", 1) == 3:
            # Programmer can't reassign already assigned card
            if self.instance.pk and self.instance.assignee and self.instance.assignee != user:
                self.fields["assignee"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        diff = cleaned_data.get("difficulty_level")
        # Enforce initial_difficulty_level preservation
        if diff and not self.instance.initial_difficulty_level:
            self.instance.initial_difficulty_level = diff

        # If adding to a sprint, zorluk derecesi zorunlu (PLAN.md §6.5)
        sprint = cleaned_data.get("sprint")
        if sprint and not diff:
            raise forms.ValidationError("Sprint'e eklenecek bir kartın zorluk derecesi (Fibonacci) girilmesi zorunludur.")

        return cleaned_data

    def clean_jira_key(self):
        jira_key = self.cleaned_data.get("jira_key") or ""
        if jira_key:
            jira_key = jira_key.strip()
            proj = getattr(self.instance, "project", None)
            if proj:
                issue = JiraIssue.objects.filter(project=proj, jira_key=jira_key).first()
                if issue is None and proj.jira_connection:
                    from .services import JiraService

                    service = JiraService()
                    try:
                        issue_data = service.get_project_issue(proj, jira_key)
                        issue, _ = JiraIssue.objects.update_or_create(
                            project=proj,
                            jira_id=issue_data["id"],
                            defaults={
                                "jira_key": issue_data["key"],
                                "summary": issue_data.get("summary", ""),
                                "description": issue_data.get("description", ""),
                                "status_id": issue_data.get("status_id"),
                                "status_key": issue_data.get("status_key"),
                                "assignee": issue_data.get("assignee"),
                                "reporter": issue_data.get("reporter"),
                                "created": issue_data.get("created", ""),
                                "updated": issue_data.get("updated", ""),
                                "sprint": issue_data.get("sprint"),
                                "epic_key": issue_data.get("epic_key"),
                                "blocks": issue_data.get("blocks", []),
                                "blocked_by": issue_data.get("blocked_by", []),
                            },
                        )
                    except Exception:
                        pass
                    finally:
                        service.close()

                if issue is None:
                    raise forms.ValidationError("Bu projede böyle bir Jira issue yok.")
                self.instance.jira_issue_id = int(issue.jira_id) if str(issue.jira_id).isdigit() else None
        return jira_key


class SprintForm(forms.ModelForm):
    class Meta:
        model = Sprint
        fields = ["name", "start_date", "duration", "team_members", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True, "placeholder": "Sprint 1"}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "duration": forms.Select(attrs={"class": "form-control"}),
            "team_members": forms.SelectMultiple(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            from django.db.models import Q
            self.fields["team_members"].queryset = User.objects.filter(
                Q(project=project) | Q(created_projects=project) | Q(is_superuser=True)
            ).distinct().order_by("username")


class IssueRequestForm(forms.ModelForm):
    """Programmer difficulty change or split request (PLAN.md §7)."""

    class Meta:
        model = IssueRequest
        fields = ["type", "reason", "requested_difficulty", "description"]
        widgets = {
            "type": forms.Select(attrs={"class": "form-control"}),
            "reason": forms.Select(attrs={"class": "form-control"}),
            "requested_difficulty": forms.Select(choices=FIBONACCI_DIFFICULTIES, attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Talep gerekçesi..."}),
        }


class SubTaskForm(forms.ModelForm):
    """Sub-task creation when splitting a card (PLAN.md §7)."""

    class Meta:
        model = KanbanCard
        fields = ["title", "description", "difficulty_level", "assignee"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "autofocus": True, "placeholder": "Alt Görev Başlığı"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "difficulty_level": forms.Select(choices=ADMIN_PM_DIFFICULTIES, attrs={"class": "form-control"}),
            "assignee": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            from django.db.models import Q
            self.fields["assignee"].queryset = User.objects.filter(
                Q(project=project) | Q(created_projects=project) | Q(is_superuser=True)
            ).distinct().order_by("username")


class StatusMappingForm(forms.ModelForm):
    """Maps a KanbanColumn (app status) to a Jira status (optional)."""

    class Meta:
        model = StatusMapping
        fields = ["jira_status", "position"]
        widgets = {
            "jira_status": forms.Select(attrs={"class": "form-control"}),
            "position": forms.NumberInput(attrs={"class": "form-control"}),
        }
