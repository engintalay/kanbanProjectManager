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
