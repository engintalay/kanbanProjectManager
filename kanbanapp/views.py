from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .forms import JiraConnectionForm, KanbanCardForm, KanbanColumnForm, ProjectForm
from .models import JiraConnection, JiraIssue, JiraStatus, KanbanCard, KanbanColumn, Project, RefreshLog, Role
from .services import JiraService


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
    return render(
        request,
        "kanbanapp/projects.html",
        {"projects": projects, "can_create_project": _can_create_project(request.user)},
    )


def _role_level(user):
    role = getattr(user, "role", None)
    if role is not None:
        return getattr(role, "level", 1)
    return 1


def _forbidden(request):
    from django.http import HttpResponse

    return HttpResponse("<h1>403</h1><p>Bu işlem için yetkiniz yok.</p>", status=403, content_type="text/html")


def _is_admin(user):
    return _role_level(user) <= 1


def _is_project_manager(user):
    return _role_level(user) <= 2


def _can_create_project(user):
    """Admin: any project. Project Manager: only projects they created."""
    if _is_admin(user):
        return True
    if _is_project_manager(user):
        return user.project is not None
    return False


def _can_manage_project(user, project):
    """Admin: any project. Project Manager: only their own. Others: no."""
    if _is_admin(user):
        return True
    if _is_project_manager(user):
        return project.created_by_id == user.id
    return False


def project_create_view(request):
    if not _can_create_project(request.user):
        return _forbidden(request)

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            messages.success(request, f"{project.name} projesi oluşturuldu.")
            return redirect("projects")
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = ProjectForm(initial={"created_by": request.user})
    return render(request, "kanbanapp/project_form.html", {"form": form, "mode": "create"})


def project_edit_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, f"{project.name} projesi güncellendi.")
            return redirect("projects")
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = ProjectForm(instance=project)
    return render(request, "kanbanapp/project_form.html", {"form": form, "mode": "edit", "project": project})


def project_delete_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        project.delete()
        messages.success(request, f"{project.name} projesi silindi.")
        return redirect("projects")
    return render(request, "kanbanapp/project_confirm_delete.html", {"project": project})


@login_required
def jira_connections(request):
    """List all Jira connections. Admin sees all, project managers see their own."""
    connections = JiraConnection.objects.all()
    if not _is_admin(request.user):
        connections = connections.filter(created_by=request.user)
    return render(
        request,
        "kanbanapp/jira_connections.html",
        {"connections": connections, "can_manage_jira": _can_manage_jira(request.user)},
    )


@login_required
def jira_connection_create(request):
    if not _can_manage_jira(request.user):
        return _forbidden(request)

    if request.method == "POST":
        form = JiraConnectionForm(request.POST)
        if form.is_valid():
            connection = form.save(commit=False)
            connection.created_by = request.user
            connection.save()
            messages.success(request, "Jira bağlantısı eklendi.")
            return redirect("jira_connections")
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = JiraConnectionForm()
    return render(request, "kanbanapp/jira_connection_form.html", {"form": form, "mode": "create"})


@login_required
def jira_connection_edit(request, connection_id):
    connection = get_object_or_404(JiraConnection, id=connection_id)
    if not _can_manage_jira(request.user):
        return _forbidden(request)

    if request.method == "POST":
        form = JiraConnectionForm(request.POST, instance=connection)
        if form.is_valid():
            form.save()
            messages.success(request, "Jira bağlantısı güncellendi.")
            return redirect("jira_connections")
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = JiraConnectionForm(instance=connection)
    return render(request, "kanbanapp/jira_connection_form.html", {"form": form, "mode": "edit", "connection": connection})


def _can_manage_jira(user):
    return _role_level(user) <= 2


@login_required
def jira_connection_delete(request, connection_id):
    connection = get_object_or_404(JiraConnection, id=connection_id)
    if not _can_manage_jira(request.user):
        return _forbidden(request)

    if request.method == "POST":
        connection.delete()
        messages.success(request, "Jira bağlantısı silindi.")
        return redirect("jira_connections")
    return render(request, "kanbanapp/connection_confirm_delete.html", {"connection": connection})


@login_required
def jira_test_connection(request, connection_id):
    connection = get_object_or_404(JiraConnection, id=connection_id)
    if not _can_manage_jira(request.user):
        return _forbidden(request)

    if not connection.is_valid:
        messages.error(request, "Bağlantı bilgileri eksik.")
        return redirect("jira_connections")

    service = JiraService()
    try:
        service.connect(connection)
        messages.success(request, "Jira bağlantısı başarılı.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Jira bağlantısı başarısız: {exc}")
    finally:
        service.close()
    return redirect("jira_connections")


@login_required
def refresh_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if not project.jira_connection:
        messages.error(request, "Bu projeye bir Jira bağlantısı tanımlı değil.")
        return redirect("projects")

    if request.method == "POST":
        service = JiraService()
        log = RefreshLog.objects.create(
            project=project, jira_connection=project.jira_connection, status="success", pulled_count=0
        )
        try:
            count = service.pull_project_issues(project, "project = %s" % (project.key or ""), max_results=500)
            if count:
                for issue in count:
                    JiraIssue.objects.update_or_create(
                        project=project, jira_id=issue["id"],
                        defaults={
                            "jira_key": issue["key"], "summary": issue["summary"],
                            "description": issue["description"], "status_id": issue["status_id"],
                            "status_key": issue["status_key"], "assignee": issue["assignee"],
                            "reporter": issue["reporter"], "created": issue["created"],
                            "updated": issue["updated"], "sprint": issue["sprint"],
                            "epic_key": issue["epic_key"], "blocks": issue.get("blocks", []),
                             "blocked_by": issue.get("blocked_by", []),
                         },
                     )
                log.pulled_count = len(count)
                log.status = "success"
                messages.success(request, f"{len(count)} issue başarıyla çekildi.")
            else:
                messages.info(request, "İssue bulunamadı.")
        except Exception as exc:  # noqa: BLE001
            log.status = "failed"
            log.error = str(exc)
            messages.error(request, f"Çekim başarısız: {exc}")
        finally:
            service.close()
        return redirect("projects")

    return render(request, "kanbanapp/refresh_confirm.html", {"project": project})


@login_required
def board_view(request, project_id):
    """Read-only kanban board for a project: columns grouped, cards within each column."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method != "GET":
        return _forbidden(request)

    columns = KanbanColumn.objects.filter(project=project).order_by("position", "id")
    return render(
        request,
        "kanbanapp/board.html",
        {"project": project, "columns": columns, "can_manage_project": _can_manage_project(request.user, project)},
    )


def _next_position(model, project, exclude=None):
    """Return the next position value for a new column/card in this project."""
    exclude = exclude or []
    max_pos = model.objects.filter(project=project, id__notin=exclude).values_list("position", flat=True)
    return max(max_pos) + 1 if max_pos else 0


@login_required
def kanban_column_create_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanColumnForm(request.POST)
        if form.is_valid():
            column = form.save(commit=False)
            column.project = project
            column.save()
            messages.success(request, f"{column.name} kolonu oluşturuldu.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanColumnForm()
    return render(request, "kanbanapp/kanban_column_form.html", {"form": form, "project": project, "mode": "create"})


@login_required
def kanban_column_edit_view(request, project_id, column_id):
    project = get_object_or_404(Project, id=project_id)
    column = get_object_or_404(KanbanColumn, id=column_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanColumnForm(request.POST, instance=column)
        if form.is_valid():
            form.save()
            messages.success(request, f"{column.name} kolonu güncellendi.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanColumnForm(instance=column)
    return render(request, "kanbanapp/kanban_column_form.html", {"form": form, "project": project, "mode": "edit", "column": column})


@login_required
def kanban_column_delete_view(request, project_id, column_id):
    project = get_object_or_404(Project, id=project_id)
    column = get_object_or_404(KanbanColumn, id=column_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        column.delete()
        messages.success(request, f"{column.name} kolonu silindi.")
        return redirect("board", project_id=project.id)
    return render(request, "kanbanapp/kanban_column_confirm_delete.html", {"column": column, "project": project})


@login_required
def kanban_card_create_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanCardForm(request.POST)
        form.instance.project = project
        if form.is_valid():
            card = form.save(commit=False)
            card.project = project
            card.save()
            messages.success(request, f"'{card.title}' kartı oluşturuldu.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanCardForm()
        form.fields["column"].queryset = project.columns.all()
    return render(request, "kanbanapp/kanban_card_form.html", {"form": form, "project": project, "mode": "create"})


@login_required
def kanban_card_edit_view(request, project_id, card_id):
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanCardForm(request.POST, instance=card)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{card.title}' kartı güncellendi.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanCardForm(instance=card)
    return render(request, "kanbanapp/kanban_card_form.html", {"form": form, "project": project, "mode": "edit", "card": card})


@login_required
def kanban_card_delete_view(request, project_id, card_id):
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        card.delete()
        messages.success(request, f"'{card.title}' kartı silindi.")
        return redirect("board", project_id=project.id)
    return render(request, "kanbanapp/kanban_card_confirm_delete.html", {"card": card, "project": project})
