from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .models import Project, Role


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Giriş başarılı.")
            return redirect("dashboard")
        messages.error(request, "Kullanıcı adı veya şifre hatalı.")

    return render(request, "kanbanapp/login.html", {"error": None})


def logout_view(request):
    logout(request)
    messages.info(request, "Çıkış yapıldı.")
    return redirect("login")


def is_admin(user):
    if not user or not user.is_authenticated:
        return False
    role = getattr(user, "role", None)
    return role is not None and getattr(role, "level", 1) == 1


@user_passes_test(is_admin)
def register_view(request):
    """Only admins can create new users."""
    if request.method == "POST":
        from django.contrib.auth import get_user_model

        User = get_user_model()

        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")
        role_id = request.POST.get("role")

        if password1 != password2:
            messages.error(request, "Şifreler eşleşmiyor.")
        elif not username or not email or not password1:
            messages.error(request, "Tüm alanları doldurun.")
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                first_name=request.POST.get("first_name", ""),
                last_name=request.POST.get("last_name", ""),
            )
            if role_id:
                user.role_id = role_id
            user.save()
            messages.success(request, f"{username} kullanıcısı oluşturuldu.")
            return redirect("register")

    return render(request, "kanbanapp/register.html", {"error": None})


@login_required
def dashboard_view(request):
    """Home / dashboard showing projects the user may access."""
    projects = Project.objects.all()
    roles = Role.objects.all()
    return render(request, "kanbanapp/dashboard.html", {"projects": projects, "roles": roles})


@login_required
def project_list_view(request):
    projects = Project.objects.all()
    return render(request, "kanbanapp/projects.html", {"projects": projects})
