from django import forms

from .models import JiraConnection, Project


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
