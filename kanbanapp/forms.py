from django import forms

from .models import JiraConnection, JiraIssue, JiraStatus, KanbanColumn, KanbanCard, Project, StatusMapping


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
        if Project.objects.filter(key=key).exists():
            raise forms.ValidationError("Bu proje anahtarı zaten kullanılıyor.")
        return key


class JiraConnectionForm(forms.ModelForm):
    class Meta:
        model = JiraConnection
        fields = ["name", "host", "username", "password", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "host": forms.TextInput(attrs={"class": "form-control", "placeholder": "https://jira.example.com"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "password": forms.PasswordInput(attrs={"class": "form-control"}),
            "is_default": forms.CheckboxInput(),
        }

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


class KanbanCardForm(forms.ModelForm):
    """Kanban card. Optionally link to a Jira issue via its key."""

    class Meta:
        model = KanbanCard
        fields = ["column", "title", "description", "jira_key", "is_extra"]
        widgets = {
            "column": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "jira_key": forms.TextInput(attrs={"class": "form-control", "placeholder": "PROJ-123 (isteğe bağlı)"}),
            "is_extra": forms.CheckboxInput(),
        }

    def clean_jira_key(self):
        jira_key = self.cleaned_data.get("jira_key") or ""
        if jira_key:
            jira_key = jira_key.strip()
            issue = JiraIssue.objects.filter(project=self.instance.project, jira_key=jira_key).first()
            if issue is None:
                raise forms.ValidationError("Bu projede böyle bir Jira issue yok.")
            self.instance.jira_issue_id = issue.jira_id
        return jira_key


class StatusMappingForm(forms.ModelForm):
    """Maps a KanbanColumn (app status) to a Jira status (optional)."""

    class Meta:
        model = StatusMapping
        fields = ["jira_status", "position"]
        widgets = {
            "jira_status": forms.Select(attrs={"class": "form-control"}),
            "position": forms.NumberInput(attrs={"class": "form-control"}),
        }
