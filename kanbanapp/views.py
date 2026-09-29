from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    IssueRequestForm,
    JiraConnectionForm,
    KanbanCardForm,
    KanbanColumnForm,
    ProjectForm,
    SprintForm,
    StatusMappingForm,
    SubTaskForm,
)
from .middleware import role_level
from .models import (
    IssueRequest,
    JiraConnection,
    JiraIssue,
    JiraStatus,
    KanbanCard,
    KanbanColumn,
    Project,
    ProjectMember,
    RefreshLog,
    Role,
    Sprint,
    StatusMapping,
)
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
    return _role_level(user) <= 1


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


def _role_level(user):
    return role_level(user)


def _forbidden(request):
    from django.http import HttpResponse

    return HttpResponse("<h1>403</h1><p>Bu işlem için yetkiniz yok.</p>", status=403, content_type="text/html")


def _is_admin(user):
    return _role_level(user) <= 1


def _is_project_manager(user):
    return _role_level(user) <= 2


def _can_create_project(user):
    """Admin and Project Manager can create projects."""
    return _role_level(user) <= 2


def _can_manage_project(user, project):
    """Admin: any project. Project Manager: only their own. Others: no."""
    if _is_admin(user):
        return True
    if _is_project_manager(user):
        return project.created_by_id == user.id
    return False


def _get_visible_projects(user):
    from django.db.models import Q
    level = _role_level(user)
    if level <= 1 or level in (4, 5):
        return Project.objects.all()
    if level == 2:
        return Project.objects.filter(created_by=user)
    if level == 3:
        return Project.objects.filter(Q(id=getattr(user, "project_id", None)) | Q(created_by=user))
    return Project.objects.none()


def _can_view_project(user, project):
    level = _role_level(user)
    if level <= 1 or level in (4, 5):
        return True
    if level == 2:
        return project.created_by_id == user.id
    if level == 3:
        return user.project_id == project.id or project.created_by_id == user.id
    return False


def _can_edit_cards(user, project):
    level = _role_level(user)
    if level <= 1:
        return True
    if level == 2 and project.created_by_id == user.id:
        return True
    if level == 3 and (user.project_id == project.id or project.created_by_id == user.id):
        return True
    return False


@login_required
def dashboard_view(request):
    """Home / dashboard showing projects the user may access."""
    projects = _get_visible_projects(request.user)
    roles = Role.objects.all()
    return render(request, "kanbanapp/dashboard.html", {"projects": projects, "roles": roles})


@login_required
def project_list_view(request):
    projects = _get_visible_projects(request.user)
    return render(
        request,
        "kanbanapp/projects.html",
        {"projects": projects, "can_create_project": _can_create_project(request.user)},
    )


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
    """Kanban board for a project: columns grouped, cards within each column."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    columns = KanbanColumn.objects.filter(project=project).order_by("position", "id")
    status_mappings = StatusMapping.objects.filter(project=project).order_by("position", "id")
    sprints = Sprint.objects.filter(project=project)
    active_sprint = sprints.filter(status=Sprint.STATUS_ACTIVE).first()
    pending_requests_count = IssueRequest.objects.filter(project=project, status=IssueRequest.STATUS_PENDING).count()

    selected_sprint_id = request.GET.get("sprint")
    selected_sprint = None
    if selected_sprint_id:
        selected_sprint = sprints.filter(id=selected_sprint_id).first()

    return render(
        request,
        "kanbanapp/board.html",
        {
            "project": project,
            "columns": columns,
            "status_mappings": status_mappings,
            "sprints": sprints,
            "active_sprint": active_sprint,
            "selected_sprint": selected_sprint,
            "pending_requests_count": pending_requests_count,
            "can_manage_project": _can_manage_project(request.user, project),
            "can_edit_cards": _can_edit_cards(request.user, project),
        },
    )


@login_required
def status_mapping_create_view(request, project_id, column_id):
    project = get_object_or_404(Project, id=project_id)
    column = get_object_or_404(KanbanColumn, id=column_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = StatusMappingForm(request.POST)
        if form.is_valid():
            mapping = form.save(commit=False)
            mapping.project = project
            mapping.app_status = column
            if StatusMapping.objects.filter(project=project, app_status=column).exclude(pk=mapping.pk).exists():
                form.add_error(None, "Bu durum için zaten bir eşleme var.")
            else:
                mapping.save()
            if form.is_valid():
                messages.success(request, "Durum eşlemesi kaydedildi.")
                return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = StatusMappingForm()
    return render(
        request,
        "kanbanapp/status_mapping_form.html",
        {"form": form, "project": project, "mode": "create", "column": column},
    )


@login_required
def status_mapping_edit_view(request, project_id, mapping_id):
    project = get_object_or_404(Project, id=project_id)
    mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = StatusMappingForm(request.POST, instance=mapping)
        if form.is_valid():
            form.save()
            messages.success(request, "Durum eşlemesi güncellendi.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = StatusMappingForm(instance=mapping)
    return render(
        request,
        "kanbanapp/status_mapping_form.html",
        {
            "form": form,
            "project": project,
            "mode": "edit",
            "mapping": mapping,
            "column": mapping.app_status,
        },
    )


@login_required
def status_mapping_delete_view(request, project_id, mapping_id):
    project = get_object_or_404(Project, id=project_id)
    mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        mapping.delete()
        messages.success(request, "Durum eşlemesi silindi.")
        return redirect("board", project_id=project.id)
    return render(
        request,
        "kanbanapp/status_mapping_confirm_delete.html",
        {"mapping": mapping, "project": project},
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
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanCardForm(request.POST, project=project)
        form.instance.project = project
        if form.is_valid():
            card = form.save(commit=False)
            card.project = project
            card.save()
            messages.success(request, f"'{card.title}' kartı oluşturuldu.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanCardForm(project=project)
    return render(request, "kanbanapp/kanban_card_form.html", {"form": form, "project": project, "mode": "create"})


@login_required
def kanban_card_edit_view(request, project_id, card_id):
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = KanbanCardForm(request.POST, instance=card, project=project)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{card.title}' kartı güncellendi.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = KanbanCardForm(instance=card, project=project)
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


@login_required
def kanban_card_move_view(request, project_id, card_id):
    """Move a card to another column, and sync status to Jira if mapped (PLAN.md §5 & §7)."""
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        target_col_id = request.POST.get("column_id")
        target_column = get_object_or_404(KanbanColumn, id=target_col_id, project=project)

        old_column = card.column
        card.column = target_column
        card.save()

        # Jira Transition (READ-WRITE) if card is linked and mapping exists
        if card.jira_key and project.jira_connection:
            mapping = StatusMapping.objects.filter(project=project, app_status=target_column).first()
            if mapping and mapping.jira_status:
                service = JiraService()
                try:
                    service.transition_issue(project, card.jira_key, mapping.jira_status.name)
                    messages.success(request, f"Kart '{target_column.name}' durumuna taşındı ve Jira güncellendi ({mapping.jira_status.name}).")
                except Exception as exc:  # noqa: BLE001
                    messages.warning(request, f"Kart taşındı fakat Jira geçişi başarısız: {exc}")
                finally:
                    service.close()
            else:
                messages.info(request, f"Kart '{target_column.name}' durumuna taşındı (Jira durum eşlemesi yok).")
        else:
            messages.success(request, f"Kart '{target_column.name}' durumuna taşındı.")

    next_url = request.POST.get("next") or request.GET.get("next")
    return redirect(next_url or "board", project_id=project.id)


@login_required
def kanban_card_assign_view(request, project_id, card_id):
    """Model A (PM assign) and Model B (Programmer self-assign) (PLAN.md §6.5 & §8)."""
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        lvl = _role_level(request.user)
        # Programmer: can self-assign if unassigned (PLAN.md §8)
        if lvl == 3:
            if not card.assignee:
                card.assignee = request.user
                card.save()
                messages.success(request, f"'{card.title}' işini üstünüze aldınız.")
            elif card.assignee == request.user:
                messages.error(request, "İşi aldıysanız bırakamazsınız. Bırakma yetkisi sadece yöneticiye aittir.")
            else:
                messages.error(request, "Bu iş başka bir geliştiriciye atanmış.")
        # Admin / PM: can assign to anyone or unassign
        elif _can_manage_project(request.user, project):
            user_id = request.POST.get("assignee_id")
            if user_id:
                assignee_user = get_object_or_404(User, id=user_id)
                card.assignee = assignee_user
                messages.success(request, f"Kart {assignee_user.username} kullanıcısına atandı.")
            else:
                card.assignee = None
                messages.success(request, "Kart ataması kaldırıldı.")
            card.save()

    return redirect("board", project_id=project.id)


@login_required
def card_request_create_view(request, project_id, card_id):
    """Programmer difficulty change / split / reassign request (PLAN.md §7)."""
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = IssueRequestForm(request.POST)
        if form.is_valid():
            req_obj = form.save(commit=False)
            req_obj.project = project
            req_obj.card = card
            req_obj.requested_by = request.user
            req_obj.status = IssueRequest.STATUS_PENDING
            req_obj.save()
            messages.success(request, "Talebiniz proje yöneticisine iletildi.")
            return redirect("board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = IssueRequestForm(initial={"type": IssueRequest.TYPE_DIFFICULTY})

    return render(
        request,
        "kanbanapp/issue_request_form.html",
        {"form": form, "project": project, "card": card},
    )


@login_required
def issue_request_list_view(request, project_id):
    """List pending and past issue requests for a project (PLAN.md §7)."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    requests_list = IssueRequest.objects.filter(project=project).order_by("-created_at")
    return render(
        request,
        "kanbanapp/issue_requests.html",
        {"project": project, "requests": requests_list},
    )


@login_required
def issue_request_action_view(request, project_id, request_id, action):
    """PM/Admin approves or rejects an issue request (PLAN.md §7)."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    req_obj = get_object_or_404(IssueRequest, id=request_id, project=project)
    if request.method == "POST":
        if action == "approve":
            req_obj.status = IssueRequest.STATUS_APPROVED
            req_obj.assigned_to = request.user
            req_obj.save()

            card = req_obj.card
            if req_obj.type == IssueRequest.TYPE_DIFFICULTY and req_obj.requested_difficulty:
                card.requested_difficulty_level = req_obj.requested_difficulty
                card.difficulty_level = req_obj.requested_difficulty
                card.save()
                messages.success(request, f"Zorluk derecesi {req_obj.requested_difficulty} olarak güncellendi.")
            elif req_obj.type == IssueRequest.TYPE_REASSIGN:
                card.assignee = None
                card.save()
                messages.success(request, "İş boşa çıkarıldı, yeniden atanabilir.")
            elif req_obj.type == IssueRequest.TYPE_SPLIT:
                messages.success(request, "İş bölme talebi onaylandı. Alt görevleri ekleyin.")
                return redirect("card_split", project_id=project.id, card_id=card.id)

        elif action == "reject":
            req_obj.status = IssueRequest.STATUS_REJECTED
            req_obj.assigned_to = request.user
            req_obj.save()
            messages.info(request, "Talep reddedildi.")

    return redirect("issue_requests", project_id=project.id)


@login_required
def card_split_view(request, project_id, card_id):
    """Split a card into sub-tasks (PLAN.md §7). Sets parent difficulty to 0."""
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = SubTaskForm(request.POST, project=project)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.project = project
            sub.column = card.column
            sub.parent_card = card
            sub.is_sub_task = True
            sub.is_extra = card.is_extra
            sub.save()

            # Reduce parent card difficulty to 0 (PLAN.md §7)
            card.difficulty_level = 0
            card.save()

            messages.success(request, f"'{sub.title}' alt görevi eklendi. Ana iş zorluğu 0'a çekildi.")
            return redirect("card_split", project_id=project.id, card_id=card.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = SubTaskForm(project=project)

    sub_tasks = card.sub_tasks.all()
    return render(
        request,
        "kanbanapp/card_split.html",
        {"project": project, "card": card, "form": form, "sub_tasks": sub_tasks},
    )


@login_required
def sprint_list_view(request, project_id):
    """Sprint list with capacity meters (PLAN.md §6.5 & §6.6)."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    sprints = project.sprints.all()
    return render(
        request,
        "kanbanapp/sprints.html",
        {
            "project": project,
            "sprints": sprints,
            "can_manage_project": _can_manage_project(request.user, project),
        },
    )


@login_required
def sprint_create_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = SprintForm(request.POST, project=project)
        if form.is_valid():
            sprint = form.save(commit=False)
            sprint.project = project
            sprint.save()
            form.save_m2m()
            messages.success(request, f"'{sprint.name}' sprinti oluşturuldu.")
            return redirect("sprints", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = SprintForm(project=project)
    return render(request, "kanbanapp/sprint_form.html", {"form": form, "project": project, "mode": "create"})


@login_required
def sprint_edit_view(request, project_id, sprint_id):
    project = get_object_or_404(Project, id=project_id)
    sprint = get_object_or_404(Sprint, id=sprint_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        form = SprintForm(request.POST, instance=sprint, project=project)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{sprint.name}' sprinti güncellendi.")
            return redirect("sprints", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = SprintForm(instance=sprint, project=project)
    return render(request, "kanbanapp/sprint_form.html", {"form": form, "project": project, "sprint": sprint, "mode": "edit"})


@login_required
def sprint_delete_view(request, project_id, sprint_id):
    project = get_object_or_404(Project, id=project_id)
    sprint = get_object_or_404(Sprint, id=sprint_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        sprint.delete()
        messages.success(request, f"'{sprint.name}' sprinti silindi.")
        return redirect("sprints", project_id=project.id)
    return render(request, "kanbanapp/sprint_confirm_delete.html", {"sprint": sprint, "project": project})


@login_required
def sprint_board_view(request, project_id, sprint_id):
    """Dedicated kanban board for a sprint with capacity progress and dependency check."""
    project = get_object_or_404(Project, id=project_id)
    sprint = get_object_or_404(Sprint, id=sprint_id, project=project)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    columns = KanbanColumn.objects.filter(project=project).order_by("position", "id")
    sprint_cards = sprint.cards.all()

    # Dependency / blocked check (PLAN.md §6.5)
    blocked_cards = []
    for card in sprint_cards:
        if card.jira_key:
            issue = JiraIssue.objects.filter(project=project, jira_key=card.jira_key).first()
            if issue and issue.blocked_by:
                # Check if blocking issues are incomplete
                blocking_keys = issue.blocked_by
                blocking_cards = KanbanCard.objects.filter(project=project, jira_key__in=blocking_keys)
                incomplete_blocking = [b for b in blocking_cards if b.column.name.lower() not in ("done", "tamamlandı", "bitti")]
                if incomplete_blocking:
                    blocked_cards.append({
                        "card": card,
                        "blocked_by": [b.jira_key for b in incomplete_blocking],
                    })

    return render(
        request,
        "kanbanapp/sprint_board.html",
        {
            "project": project,
            "sprint": sprint,
            "columns": columns,
            "blocked_cards": blocked_cards,
            "can_manage_project": _can_manage_project(request.user, project),
            "can_edit_cards": _can_edit_cards(request.user, project),
        },
    )
