"""Seed default roles and an initial admin superuser (one-time).

Usage:
    python manage.py seed_initial

The initial superuser is created from environment variables:
    DJANGO_ADMIN_USER   (required)
    DJANGO_ADMIN_PASSWORD  (required)
"""
import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from kanbanapp.models import Role

Role = Role
User = get_user_model()


class Command(BaseCommand):
    help = "Seed default roles and create the initial admin superuser."

    def handle(self, *args, **options):
        self._seed_roles()
        self._seed_admin()

    def _seed_roles(self):
        levels = {
            "Admin": Role.LEVEL_ADMIN,
            "Proje Yöneticisi": Role.LEVEL_PROJECT_MANAGER,
            "Proje Programcısı": Role.LEVEL_PROGRAMMER,
            "Raportör": Role.LEVEL_REPORTER,
            "İzleyici": Role.LEVEL_VIEWER,
        }
        for name, level in levels.items():
            if not Role.objects.filter(name=name).exists():
                Role.objects.create(name=name, level=level, slug=name.lower().replace(" ", "-"))
                print(f"  [role] {name} (seviye {level})")

        # Create a group per role name for convenience (login sonrası group'a eklenir).
        for role in Role.objects.all():
            Group.objects.get_or_create(name=role.name)

    def _seed_admin(self):
        admin_user = os.environ.get("DJANGO_ADMIN_USER")
        admin_password = os.environ.get("DJANGO_ADMIN_PASSWORD")
        if not admin_user or not admin_password:
            print("  [skip] DJANGO_ADMIN_USER / DJANGO_ADMIN_PASSWORD ayarlanmadı.")
            return

        if User.objects.filter(username=admin_user).exists():
            print(f"  [skip] {admin_user} zaten mevcut.")
            return

        admin_role = Role.objects.get(name="Admin")
        admin = User.objects.create_superuser(
            username=admin_user,
            email="admin@local",
            password=admin_password,
            role=admin_role,
        )
        print(f"  [admin] {admin_user} oluşturuldu (admin panel: /admin/)")
