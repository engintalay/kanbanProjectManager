import logging
import re

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import JsonResponse
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
    FIBONACCI_DIFFICULTIES,
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

logger = logging.getLogger(__name__)
User = get_user_model()

CLOSED_STATUS_NAMES = {
    "resolved",
    "closed",
    "ready",
    "done",
    "kapatıldı",
    "kapatildi",
    "kapalı",
    "kapali",
    "çözüldü",
    "cozuldu",
    "tamamlandı",
    "tamamlandi",
    "iptal",
    "cancelled",
    "canceled",
    "rejected",
    "bitti",
    "hazır",
    "hazir",
}

CLOSED_STATUS_PATTERNS = (
    "resolved",
    "closed",
    "ready",
    "done",
    "tamamlan",
    "kapatıl",
    "kapatil",
    "kapalı",
    "kapali",
    "çözül",
    "cozul",
    "bitti",
    "hazır",
    "hazir",
    "iptal",
    "cancel",
    "reject",
)


def is_issue_closed(issue_dict: dict) -> bool:
    """Return True if a Jira issue is resolved, closed, or ready."""
    # 1. statusCategory in Jira (e.g. 'done')
    cat = (issue_dict.get("status_category") or "").strip().lower()
    if cat in ("done", "closed"):
        return True

    # 2. resolution set
    if issue_dict.get("resolution"):
        return True

    # 3. status name matching closed / resolved / ready statuses (exact or pattern)
    status_name = (issue_dict.get("status_key") or "").strip().lower()
    if not status_name:
        return False

    if status_name in CLOSED_STATUS_NAMES:
        return True

    for pattern in CLOSED_STATUS_PATTERNS:
        if pattern in status_name:
            return True

    return False


def build_open_issues_jql(base_jql: str, project_key: str = "") -> str:
    """Construct a JQL query string ensuring resolved and closed issues are excluded.

    Uses standard Jira JQL fields (resolution and statusCategory) without hardcoding
    custom status names that may not exist on a given Jira instance.
    """
    jql = (base_jql or "").strip()
    if not jql and project_key:
        jql = f'project = "{project_key}"'

    order_by_clause = ""
    match = re.search(r"\bORDER\s+BY\b", jql, flags=re.IGNORECASE)
    if match:
        order_by_clause = jql[match.start():].strip()
        jql = jql[:match.start()].strip()

    # If user provided a standalone issue key (e.g. 'KONF-102')
    if jql and re.match(r"^[A-Za-z0-9_]+-[0-9]+$", jql):
        jql = f'issueKey = "{jql}"'
    elif jql and re.match(r"^[A-Za-z0-9_]+$", jql) and not any(k in jql.lower() for k in ["=", "in", "~", "is"]):
        jql = f'project = "{jql}"'

    closed_filter = "resolution is EMPTY AND statusCategory != Done"

    combined = f"({jql}) AND {closed_filter}" if jql else closed_filter

    if order_by_clause:
        return f"{combined} {order_by_clause}"
    return f"{combined} ORDER BY updated DESC"


def build_fallback_open_issues_jql(base_jql: str, project_key: str = "") -> str:
    """Fallback JQL without statusCategory in case Jira server doesn't support statusCategory."""
    jql = (base_jql or "").strip()
    if not jql and project_key:
        jql = f'project = "{project_key}"'

    order_by_clause = ""
    match = re.search(r"\bORDER\s+BY\b", jql, flags=re.IGNORECASE)
    if match:
        order_by_clause = jql[match.start():].strip()
        jql = jql[:match.start()].strip()

    if jql and re.match(r"^[A-Za-z0-9_]+-[0-9]+$", jql):
        jql = f'issueKey = "{jql}"'
    elif jql and re.match(r"^[A-Za-z0-9_]+$", jql) and not any(k in jql.lower() for k in ["=", "in", "~", "is"]):
        jql = f'project = "{jql}"'

    closed_filter = "resolution is EMPTY"

    combined = f"({jql}) AND {closed_filter}" if jql else closed_filter

    if order_by_clause:
        return f"{combined} {order_by_clause}"
    return f"{combined} ORDER BY updated DESC"




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
    from django.contrib.auth import get_user_model
    from .models import ensure_default_roles, Project, Role

    User = get_user_model()

    if Role.objects.count() == 0:
        ensure_default_roles()

    roles = Role.objects.all().order_by("level")
    projects = Project.objects.all().order_by("name")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")
        role_id = request.POST.get("role")
        project_id = request.POST.get("project")

        if password1 != password2:
            messages.error(request, "Şifreler eşleşmiyor.")
        elif not username or not email or not password1:
            messages.error(request, "Tüm zorunlu alanları (kullanıcı adı, email, şifre) doldurun.")
        elif not role_id:
            messages.error(request, "Lütfen bir rol seçin.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, f"'{username}' kullanıcı adı zaten kullanılıyor.")
        elif User.objects.filter(email=email).exists():
            messages.error(request, f"'{email}' e-posta adresi zaten kullanılıyor.")
        else:
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password1,
                    first_name=first_name,
                    last_name=last_name,
                )
                user.role_id = role_id
                if project_id:
                    user.project_id = project_id
                user.save()
                messages.success(request, f"'{username}' kullanıcısı başarıyla oluşturuldu.")
                return redirect("register")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f"Kullanıcı oluşturulurken bir hata oluştu: {exc}")

    return render(
        request,
        "kanbanapp/register.html",
        {"roles": roles, "projects": projects},
    )


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


def _user_has_project_access(user, project):
    """Check if a user has access to a project.
    Admins, reporters, viewers have global visibility.
    Project managers and programmers have access if:
    - they created the project
    - the project is assigned to them directly (user.project)
    - they are a member via ProjectMember
    """
    if not user or not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    if _role_level(user) in (4, 5):
        return True
    if project.created_by_id == user.id:
        return True
    if getattr(user, "project_id", None) == project.id:
        return True
    if project.project_members.filter(user_id=user.id).exists():
        return True
    return False


def _can_manage_project(user, project):
    """Admin: any project. Project Manager: projects they created or are assigned to. Others: no."""
    if _is_admin(user):
        return True
    if _is_project_manager(user):
        return _user_has_project_access(user, project)
    return False


def _get_visible_projects(user):
    from django.db.models import Q
    level = _role_level(user)
    if level <= 1 or level in (4, 5):
        return Project.objects.all()
    # Level 2 (Project Manager) and Level 3 (Programmer)
    return Project.objects.filter(
        Q(created_by=user) |
        Q(id=getattr(user, "project_id", None)) |
        Q(project_members__user=user)
    ).distinct()


def _can_view_project(user, project):
    level = _role_level(user)
    if level <= 1 or level in (4, 5):
        return True
    return _user_has_project_access(user, project)


def _can_edit_cards(user, project):
    level = _role_level(user)
    if level <= 1:
        return True
    if level in (2, 3):
        return _user_has_project_access(user, project)
    return False


@login_required
def dashboard_view(request):
    """Personalized role-based dashboard (PLAN.md §8)."""
    user = request.user
    level = _role_level(user)
    projects = _get_visible_projects(user)

    my_cards = []
    available_cards = []
    pending_requests = []
    active_sprints = []

    if level == 3:
        # Programmer: My assigned cards + available unassigned cards (PLAN.md §8)
        my_cards = KanbanCard.objects.filter(assignee=user).select_related("project", "column", "sprint")
        available_cards = KanbanCard.objects.filter(
            project__in=projects, assignee__isnull=True
        ).select_related("project", "column")[:15]
        active_sprints = Sprint.objects.filter(project__in=projects, status=Sprint.STATUS_ACTIVE)
    else:
        # Admin / PM: Active sprints, pending requests, all visible projects
        active_sprints = Sprint.objects.filter(project__in=projects, status=Sprint.STATUS_ACTIVE)
        pending_requests = IssueRequest.objects.filter(project__in=projects, status=IssueRequest.STATUS_PENDING)[:10]

    return render(
        request,
        "kanbanapp/dashboard.html",
        {
            "projects": projects,
            "my_cards": my_cards,
            "available_cards": available_cards,
            "active_sprints": active_sprints,
            "pending_requests": pending_requests,
            "role_level": level,
        },
    )


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


@login_required
def project_delete_view(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not (_is_admin(request.user) or project.created_by_id == request.user.id):
        return _forbidden(request)

    if request.method == "POST":
        name = project.name
        try:
            from django.db import transaction

            with transaction.atomic():
                project.delete()
            messages.success(request, f"'{name}' projesi ve bağlı tüm veriler başarıyla silindi.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Proje silme hatası: %s", exc)
            messages.error(request, f"Proje silinirken hata oluştu: {exc}")
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
        messages.error(request, "Bağlantı bilgileri eksik (host, kullanıcı adı veya şifre boş).")
        return redirect("jira_connections")

    service = JiraService()
    try:
        user_info = service.test_connection(connection)
        display_name = ""
        if isinstance(user_info, dict):
            display_name = user_info.get("displayName") or user_info.get("name") or ""
        user_str = f" ({display_name})" if display_name else ""
        messages.success(request, f"Jira bağlantısı başarılı! Giriş yapılan kullanıcı: {connection.username}{user_str}")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Jira bağlantı hatası: {exc}")
    finally:
        service.close()
    return redirect("jira_connections")


@login_required
def jira_sync_statuses(request, connection_id):
    """Sync all statuses from a Jira connection into local JiraStatus table."""
    connection = get_object_or_404(JiraConnection, id=connection_id)
    if not _can_manage_jira(request.user):
        return _forbidden(request)

    if not connection.is_valid:
        messages.error(request, "Bağlantı bilgileri eksik (host, kullanıcı adı veya şifre boş).")
        return redirect("jira_connections")

    service = JiraService()
    try:
        count = service.sync_statuses(connection)
        messages.success(request, f"Jira'dan {count} adet statü başarıyla çekildi ve güncellendi.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Jira statüleri çekilirken hata oluştu: {exc}")
    finally:
        service.close()

    next_url = request.GET.get("next") or request.POST.get("next")
    return redirect(next_url or "jira_connections")


@login_required
def project_jira_sync_statuses(request, project_id):
    """Sync statuses for a project's configured Jira connection."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    if not project.jira_connection:
        messages.error(request, "Bu projeye atanmış bir Jira bağlantısı bulunmuyor.")
        return redirect("board", project_id=project.id)

    service = JiraService()
    try:
        count = service.sync_statuses(project.jira_connection)
        messages.success(request, f"Jira'dan {count} adet statü başarıyla çekildi ve güncellendi.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Jira statüleri çekilirken hata oluştu: {exc}")
    finally:
        service.close()

    next_url = request.GET.get("next") or request.POST.get("next")
    return redirect(next_url or "project_status_mappings", project_id=project.id)


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
            try:
                service.sync_statuses(project.jira_connection)
            except Exception as status_exc:  # noqa: BLE001
                logger.warning("Proje yenilenirken statü senkronizasyonu hatası: %s", status_exc)

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
                    # Update contents and column of existing cards from Jira
                    for card in project.cards.filter(jira_key=issue["key"]):
                        card.title = issue["summary"] or card.title
                        card.description = issue["description"] or ""
                        if issue.get("id") and str(issue["id"]).isdigit():
                            card.jira_issue_id = int(issue["id"])
                        if project.sync_jira_status:
                            status_key = issue.get("status_key")
                            if status_key:
                                mappings = StatusMapping.objects.filter(
                                    project=project, jira_status__isnull=False
                                ).filter(
                                    Q(jira_status__name__iexact=status_key)
                                    | Q(jira_status__jira_status_key__iexact=status_key)
                                )
                                # If card is already in one of the columns mapped to this Jira status, keep it!
                                already_in_mapped_column = mappings.filter(app_status=card.column).exists()
                                if not already_in_mapped_column:
                                    primary_mapping = (
                                        mappings.filter(transfer_to_jira=True)
                                        .order_by("-is_primary", "position", "id")
                                        .first()
                                    ) or mappings.order_by("-is_primary", "position", "id").first()
                                    if primary_mapping and primary_mapping.app_status:
                                        card.column = primary_mapping.app_status
                        card.save()
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

    columns = KanbanColumn.objects.filter(project=project).prefetch_related("status_mappings__jira_status").order_by("position", "id")
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

    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        form = StatusMappingForm(request.POST, project=project)
        if form.is_valid():
            mapping = form.save(commit=False)
            mapping.project = project
            mapping.app_status = column
            if mapping.jira_status and StatusMapping.objects.filter(project=project, app_status=column, jira_status=mapping.jira_status).exclude(pk=mapping.pk).exists():
                form.add_error("jira_status", "Bu kolon ve Jira statüsü için zaten bir eşleme tanımlanmış.")
            else:
                existing = StatusMapping.objects.filter(project=project, app_status=column).exclude(pk=mapping.pk)
                if mapping.is_primary:
                    existing.update(is_primary=False)
                elif not existing.exists():
                    mapping.is_primary = True
                mapping.save()
                messages.success(request, "Durum eşlemesi kaydedildi.")
                return redirect(next_url or "board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = StatusMappingForm(project=project)
    return render(
        request,
        "kanbanapp/status_mapping_form.html",
        {"form": form, "project": project, "mode": "create", "column": column, "next_url": next_url},
    )


@login_required
def status_mapping_edit_view(request, project_id, mapping_id):
    project = get_object_or_404(Project, id=project_id)
    mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        form = StatusMappingForm(request.POST, instance=mapping, project=project)
        if form.is_valid():
            mapping = form.save(commit=False)
            if mapping.jira_status and StatusMapping.objects.filter(project=project, app_status=mapping.app_status, jira_status=mapping.jira_status).exclude(pk=mapping.pk).exists():
                form.add_error("jira_status", "Bu kolon ve Jira statüsü için zaten bir eşleme tanımlanmış.")
            else:
                if mapping.is_primary:
                    StatusMapping.objects.filter(project=project, app_status=mapping.app_status).exclude(pk=mapping.pk).update(is_primary=False)
                mapping.save()
                messages.success(request, "Durum eşlemesi güncellendi.")
                return redirect(next_url or "board", project_id=project.id)
        messages.error(request, "Formdaki hataları düzeltin.")
    else:
        form = StatusMappingForm(instance=mapping, project=project)
    return render(
        request,
        "kanbanapp/status_mapping_form.html",
        {
            "form": form,
            "project": project,
            "mode": "edit",
            "mapping": mapping,
            "column": mapping.app_status,
            "next_url": next_url,
        },
    )


@login_required
def status_mapping_delete_view(request, project_id, mapping_id):
    project = get_object_or_404(Project, id=project_id)
    mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
    if not _can_manage_project(request.user, project):
        return _forbidden(request)

    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        col = mapping.app_status
        was_primary = mapping.is_primary
        mapping.delete()
        if was_primary:
            first_remain = StatusMapping.objects.filter(project=project, app_status=col).first()
            if first_remain:
                first_remain.is_primary = True
                first_remain.save(update_fields=["is_primary"])
        messages.success(request, "Durum eşlemesi silindi.")
        return redirect(next_url or "board", project_id=project.id)
    return render(
        request,
        "kanbanapp/status_mapping_confirm_delete.html",
        {"mapping": mapping, "project": project, "next_url": next_url},
    )


@login_required
def project_status_mappings_view(request, project_id):
    """Dedicated management and sync screen for a project's Jira status mappings.

    Supports:
    - Pulling / syncing Jira statuses from the connected Jira server
    - Mapping multiple Jira statuses to an application status (KanbanColumn)
    - Toggling Jira status transfer per mapping
    - Setting primary target Jira status for card moves
    - Auto-matching columns to Jira statuses by name / synonym similarity
    - Toggling project-wide Jira status sync
    """
    project = get_object_or_404(Project, id=project_id)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    can_manage = _can_manage_project(request.user, project)

    if request.method == "POST":
        if not can_manage:
            return _forbidden(request)

        action = request.POST.get("action")

        # 1. Pull statuses from Jira
        if action == "pull_jira_statuses":
            if not project.jira_connection:
                messages.error(request, "Bu projeye atanmış bir Jira bağlantısı bulunmuyor.")
            else:
                service = JiraService()
                try:
                    count = service.sync_statuses(project.jira_connection)
                    messages.success(request, f"Jira'dan {count} adet statü başarıyla çekildi ve güncellendi.")
                except Exception as exc:  # noqa: BLE001
                    messages.error(request, f"Jira statüleri çekilirken hata oluştu: {exc}")
                finally:
                    service.close()
            return redirect("project_status_mappings", project_id=project.id)

        # 2. Toggle project-wide Jira status sync
        elif action == "toggle_project_sync":
            project.sync_jira_status = not project.sync_jira_status
            project.save(update_fields=["sync_jira_status"])
            status_text = "aktif edildi" if project.sync_jira_status else "devre dışı bırakıldı (kapatıldı)"
            messages.success(request, f"Proje genelinde Jira statü aktarımı {status_text}.")
            return redirect("project_status_mappings", project_id=project.id)

        # 3. Add mapping
        elif action == "add_mapping":
            column_id = request.POST.get("column_id")
            jira_status_id = request.POST.get("jira_status_id")
            transfer_to_jira = request.POST.get("transfer_to_jira") == "1"
            is_primary = request.POST.get("is_primary") == "1"

            column = get_object_or_404(KanbanColumn, id=column_id, project=project)
            jira_status = get_object_or_404(JiraStatus, id=jira_status_id) if jira_status_id else None

            if not jira_status:
                messages.error(request, "Lütfen geçerli bir Jira statüsü seçin.")
                return redirect("project_status_mappings", project_id=project.id)

            if StatusMapping.objects.filter(project=project, app_status=column, jira_status=jira_status).exists():
                messages.warning(request, f"'{column.name}' durumu ile '{jira_status.name}' Jira statüsü zaten eşlenmiş.")
                return redirect("project_status_mappings", project_id=project.id)

            existing_mappings = StatusMapping.objects.filter(project=project, app_status=column)
            if not existing_mappings.exists():
                is_primary = True
            elif is_primary:
                existing_mappings.update(is_primary=False)

            StatusMapping.objects.create(
                project=project,
                app_status=column,
                jira_status=jira_status,
                transfer_to_jira=transfer_to_jira,
                is_primary=is_primary,
                position=existing_mappings.count(),
            )
            messages.success(request, f"'{column.name}' durumu '{jira_status.name}' Jira statüsü ile eşlendi.")
            return redirect("project_status_mappings", project_id=project.id)

        # 4. Delete mapping
        elif action == "delete_mapping":
            mapping_id = request.POST.get("mapping_id")
            mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
            col = mapping.app_status
            was_primary = mapping.is_primary
            mapping_title = str(mapping)
            mapping.delete()

            if was_primary:
                next_primary = StatusMapping.objects.filter(project=project, app_status=col).first()
                if next_primary:
                    next_primary.is_primary = True
                    next_primary.save(update_fields=["is_primary"])

            messages.success(request, f"'{mapping_title}' eşlemesi silindi.")
            return redirect("project_status_mappings", project_id=project.id)

        # 5. Move mapping (drag and drop between columns)
        elif action == "move_mapping":
            mapping_id = request.POST.get("mapping_id")
            target_col_id = request.POST.get("target_column_id")
            mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
            target_column = get_object_or_404(KanbanColumn, id=target_col_id, project=project)
            old_col = mapping.app_status
            was_primary = mapping.is_primary

            if old_col.id != target_column.id:
                existing = StatusMapping.objects.filter(
                    project=project, app_status=target_column, jira_status=mapping.jira_status
                ).first()
                if existing:
                    mapping.delete()
                    messages.info(request, f"'{mapping.jira_status.name}' statüsü zaten '{target_column.name}' durumunda eşliydi.")
                else:
                    has_target_primary = StatusMapping.objects.filter(
                        project=project, app_status=target_column, is_primary=True
                    ).exists()
                    mapping.app_status = target_column
                    if not has_target_primary:
                        mapping.is_primary = True
                    mapping.save(update_fields=["app_status", "is_primary"])
                    messages.success(
                        request,
                        f"'{mapping.jira_status.name}' statüsü '{old_col.name}' durumundan '{target_column.name}' durumuna taşındı."
                    )

                if was_primary:
                    next_primary = StatusMapping.objects.filter(project=project, app_status=old_col).first()
                    if next_primary:
                        next_primary.is_primary = True
                        next_primary.save(update_fields=["is_primary"])

            return redirect("project_status_mappings", project_id=project.id)

        # 6. Toggle transfer_to_jira
        elif action == "toggle_transfer":
            mapping_id = request.POST.get("mapping_id")
            mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
            mapping.transfer_to_jira = not mapping.transfer_to_jira
            mapping.save(update_fields=["transfer_to_jira"])
            status_text = "açıldı" if mapping.transfer_to_jira else "kapatıldı"
            messages.success(request, f"'{mapping}' için Jira aktarımı {status_text}.")
            return redirect("project_status_mappings", project_id=project.id)

        # 6. Set primary
        elif action == "set_primary":
            mapping_id = request.POST.get("mapping_id")
            mapping = get_object_or_404(StatusMapping, id=mapping_id, project=project)
            StatusMapping.objects.filter(project=project, app_status=mapping.app_status).exclude(id=mapping.id).update(is_primary=False)
            mapping.is_primary = True
            mapping.save(update_fields=["is_primary"])
            messages.success(request, f"'{mapping.jira_status.name if mapping.jira_status else ''}', '{mapping.app_status.name}' için birincil Jira statüsü yapıldı.")
            return redirect("project_status_mappings", project_id=project.id)

        # 7. Auto-map
        elif action == "auto_map":
            synced_count = 0
            hidden_ids = set(project.hidden_jira_statuses.values_list("id", flat=True))
            all_jira_statuses = list(JiraStatus.objects.exclude(id__in=hidden_ids))
            columns = KanbanColumn.objects.filter(project=project)

            synonyms = {
                "to do": ["to do", "yapılacak", "open", "açık", "backlog", "yeni"],
                "yapılacak": ["to do", "yapılacak", "open", "açık", "backlog", "yeni"],
                "in progress": ["in progress", "devam ediyor", "geliştiriliyor", "işlemde", "çalışılıyor"],
                "devam ediyor": ["in progress", "devam ediyor", "geliştiriliyor", "işlemde", "çalışılıyor"],
                "geliştiriliyor": ["in progress", "devam ediyor", "geliştiriliyor", "işlemde", "çalışılıyor"],
                "code review": ["code review", "review", "inceleme", "kod inceleme", "peer review"],
                "inceleme": ["code review", "review", "inceleme", "kod inceleme", "peer review"],
                "test": ["test", "testing", "qa", "test ediliyor", "kalite kontrol"],
                "tamamlandı": ["done", "tamamlandı", "bitti", "closed", "kapalı", "resolved"],
                "done": ["done", "tamamlandı", "bitti", "closed", "kapalı", "resolved"],
            }

            for col in columns:
                col_name_lower = col.name.strip().lower()
                target_js = None

                for js in all_jira_statuses:
                    if js.name.strip().lower() == col_name_lower:
                        target_js = js
                        break

                if not target_js:
                    accepted_terms = synonyms.get(col_name_lower, [])
                    for js in all_jira_statuses:
                        js_name_lower = js.name.strip().lower()
                        if js_name_lower in accepted_terms or any(term in js_name_lower for term in accepted_terms):
                            target_js = js
                            break

                if target_js:
                    if not StatusMapping.objects.filter(project=project, app_status=col, jira_status=target_js).exists():
                        is_first = not StatusMapping.objects.filter(project=project, app_status=col).exists()
                        StatusMapping.objects.create(
                            project=project,
                            app_status=col,
                            jira_status=target_js,
                            transfer_to_jira=True,
                            is_primary=is_first,
                        )
                        synced_count += 1

            if synced_count > 0:
                messages.success(request, f"{synced_count} adet yeni durum eşlemesi otomatik olarak oluşturuldu.")
            else:
                messages.info(request, "Eşleşen yeni bir Jira statüsü bulunamadı veya tüm durumlar zaten eşlenmiş.")
            return redirect("project_status_mappings", project_id=project.id)

        # 8. Toggle Jira Status Visibility (Hide / Unhide for this project)
        elif action == "toggle_jira_status_visibility":
            jira_status_id = request.POST.get("jira_status_id")
            js = get_object_or_404(JiraStatus, id=jira_status_id)
            if project.hidden_jira_statuses.filter(id=js.id).exists():
                project.hidden_jira_statuses.remove(js)
                messages.success(request, f"'{js.name}' Jira statüsü bu proje için yeniden görünür yapıldı.")
            else:
                mapped_cols = StatusMapping.objects.filter(project=project, jira_status=js)
                if mapped_cols.exists():
                    col_names = ", ".join(f"'{m.app_status.name}'" for m in mapped_cols)
                    messages.warning(
                        request,
                        f"'{js.name}' statüsü şu anda {col_names} durumuna eşlenmiş. Gizlemeden önce eşlemeyi kaldırmalısınız."
                    )
                else:
                    project.hidden_jira_statuses.add(js)
                    messages.success(request, f"'{js.name}' Jira statüsü bu proje için gizlendi.")
            return redirect("project_status_mappings", project_id=project.id)

        # 9. Bulk update hidden statuses
        elif action == "bulk_update_hidden_statuses":
            hidden_ids = [int(x) for x in request.POST.getlist("hidden_status_ids") if x.isdigit()]
            mapped_js_ids = set(
                StatusMapping.objects.filter(project=project, jira_status__isnull=False).values_list("jira_status_id", flat=True)
            )
            safe_hidden_ids = [hid for hid in hidden_ids if hid not in mapped_js_ids]
            project.hidden_jira_statuses.set(safe_hidden_ids)
            messages.success(request, "Jira statü görünürlük ayarları kaydedildi.")
            return redirect("project_status_mappings", project_id=project.id)

    # GET
    columns = (
        KanbanColumn.objects.filter(project=project)
        .prefetch_related("status_mappings__jira_status")
        .order_by("position", "id")
    )
    hidden_status_ids = set(project.hidden_jira_statuses.values_list("id", flat=True))
    all_jira_statuses = list(JiraStatus.objects.all().order_by("name"))
    visible_jira_statuses = [js for js in all_jira_statuses if js.id not in hidden_status_ids]
    mappings = list(StatusMapping.objects.filter(project=project).select_related("app_status", "jira_status"))

    columns_data = []
    for col in columns:
        col_mappings = [m for m in mappings if m.app_status_id == col.id]
        col_mapped_js_ids = {m.jira_status_id for m in col_mappings if m.jira_status_id}
        available_js = [js for js in visible_jira_statuses if js.id not in col_mapped_js_ids]
        columns_data.append({
            "column": col,
            "mappings": col_mappings,
            "available_jira_statuses": available_js,
            "has_primary": any(m.is_primary for m in col_mappings),
        })

    jira_statuses_data = []
    for js in all_jira_statuses:
        mapped_cols = [m.app_status for m in mappings if m.jira_status_id == js.id]
        jira_statuses_data.append({
            "status": js,
            "mapped_columns": mapped_cols,
            "is_mapped": len(mapped_cols) > 0,
            "is_hidden": js.id in hidden_status_ids,
        })

    return render(
        request,
        "kanbanapp/project_status_sync.html",
        {
            "project": project,
            "can_manage_project": can_manage,
            "columns_data": columns_data,
            "jira_statuses_data": jira_statuses_data,
            "total_columns": columns.count(),
            "total_mappings": len(mappings),
            "total_jira_statuses": len(all_jira_statuses),
            "hidden_jira_count": len(hidden_status_ids),
            "visible_jira_count": len(visible_jira_statuses),
            "unmapped_jira_count": len([j for j in jira_statuses_data if not j["is_mapped"] and not j["is_hidden"]]),
        },
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
        if column.cards.exists():
            messages.error(
                request,
                f"'{column.name}' kolonu içinde kartlar bulunmaktadır. Kolonu silmeden önce lütfen kartları başka bir kolona taşıyın.",
            )
            return redirect("board", project_id=project.id)
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
def kanban_card_import_jira_view(request, project_id):
    """Import issue(s) directly from Jira into the project's Kanban board.

    Supports:
    - Searching open Jira issues using custom or default JQL queries.
    - Strictly filtering out closed / resolved issues (resolved, closed, done).
    - Automatically cleaning out issues that are already added as cards to the project.
    - Listing filtered issues and manually adding single or multiple issues to the board.
    """
    project = get_object_or_404(Project, id=project_id)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if not project.jira_connection:
        messages.error(
            request,
            "Bu projede tanımlı bir Jira bağlantısı bulunmuyor. Önce projeyi bir Jira bağlantısıyla ilişkilendirin."
        )
        return redirect("board", project_id=project.id)

    columns = project.columns.all().order_by("position", "name")
    if not columns.exists():
        messages.error(request, "Projeye ait hiçbir kolon bulunmuyor. Lütfen önce panoda bir kolon oluşturun.")
        return redirect("board", project_id=project.id)

    sprints = project.sprints.all().order_by("position", "-created_at")
    members = User.objects.filter(
        Q(project=project) | Q(created_projects=project) | Q(is_superuser=True)
    ).distinct().order_by("username")

    existing_keys = set(
        KanbanCard.objects.filter(project=project, jira_key__isnull=False).values_list("jira_key", flat=True)
    )

    default_jql = f'project = "{project.key}"' if project.key else ""
    user_jql = request.GET.get("jql", "").strip() or request.POST.get("jql", "").strip()
    search_jql = user_jql if user_jql else default_jql
    action = request.POST.get("action", "")

    # Handle POST for adding card(s)
    if request.method == "POST" and action != "search":
        keys_to_import = []
        selected = request.POST.getlist("selected_keys")
        if selected:
            keys_to_import.extend([k.strip() for k in selected if k.strip()])
        direct_key = request.POST.get("jira_key", "").strip()
        if direct_key and direct_key not in keys_to_import:
            keys_to_import.append(direct_key)

        if not keys_to_import:
            messages.error(request, "Lütfen panoya eklenecek en az bir Jira işi seçin veya anahtarını girin.")
            return redirect(f"{request.path}?jql={search_jql}")

        column_id = request.POST.get("column_id")
        difficulty_level = request.POST.get("difficulty_level")
        assignee_id = request.POST.get("assignee_id")
        sprint_id = request.POST.get("sprint_id")
        sync_status = request.POST.get("sync_jira_status") != "0"

        target_column_override = columns.filter(id=column_id).first() if column_id else None
        target_sprint_override = sprints.filter(id=sprint_id).first() if sprint_id else None
        target_assignee_override = members.filter(id=assignee_id).first() if assignee_id else None
        diff_override = None
        if difficulty_level:
            try:
                diff_override = int(difficulty_level)
            except (ValueError, TypeError):
                diff_override = None

        service = JiraService()
        imported_count = 0
        updated_count = 0

        try:
            for issue_key in keys_to_import:
                issue_data = None
                try:
                    issue_data = service.get_project_issue(project, issue_key)
                except Exception as exc:
                    logger.warning("Jira canlı çekim yapılamadı (%s): %s", issue_key, exc)
                    local = JiraIssue.objects.filter(project=project, jira_key=issue_key).first()
                    if local:
                        issue_data = {
                            "id": local.jira_id,
                            "key": local.jira_key,
                            "summary": local.summary,
                            "description": local.description,
                            "status_key": local.status_key,
                            "status_id": local.status_id,
                            "assignee": local.assignee,
                            "reporter": local.reporter,
                            "created": local.created,
                            "updated": local.updated,
                            "sprint": local.sprint,
                            "epic_key": local.epic_key,
                            "blocks": local.blocks,
                            "blocked_by": local.blocked_by,
                        }
                    else:
                        messages.error(request, f"'{issue_key}' Jira'dan çekilemedi: {exc}")
                        continue

                # Strict filter: Closed/resolved issues must NEVER be imported
                if is_issue_closed(issue_data):
                    messages.error(
                        request,
                        f"'{issue_key}' işi kapalı veya çözülmüş durumda (Durum: {issue_data.get('status_key')}). Kapalı işler panoya eklenemez."
                    )
                    continue

                JiraIssue.objects.update_or_create(
                    project=project,
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

                target_col = target_column_override
                if not target_col and sync_status and project.sync_jira_status:
                    status_key = issue_data.get("status_key")
                    if status_key:
                        mappings = StatusMapping.objects.filter(
                            project=project, jira_status__isnull=False
                        ).filter(
                            Q(jira_status__name__iexact=status_key)
                            | Q(jira_status__jira_status_key__iexact=status_key)
                        )
                        primary_m = (
                            mappings.filter(transfer_to_jira=True)
                            .order_by("-is_primary", "position", "id")
                            .first()
                        ) or mappings.order_by("-is_primary", "position", "id").first()
                        if primary_m and primary_m.app_status:
                            target_col = primary_m.app_status
                if not target_col:
                    target_col = columns.first()

                target_sp = target_sprint_override
                if not target_sp and issue_data.get("sprint"):
                    target_sp = sprints.filter(name__iexact=issue_data["sprint"]).first()

                target_ass = target_assignee_override
                if not target_ass and issue_data.get("assignee"):
                    raw_a = issue_data["assignee"].strip()
                    target_ass = members.filter(
                        Q(username__iexact=raw_a) | Q(first_name__icontains=raw_a) | Q(last_name__icontains=raw_a)
                    ).first()

                existing_card = KanbanCard.objects.filter(project=project, jira_key=issue_data["key"]).first()
                if existing_card:
                    existing_card.title = issue_data.get("summary") or existing_card.title
                    existing_card.description = issue_data.get("description") or existing_card.description
                    if issue_data.get("id") and str(issue_data["id"]).isdigit():
                        existing_card.jira_issue_id = int(issue_data["id"])
                    if target_col:
                        existing_card.column = target_col
                    if diff_override is not None:
                        existing_card.difficulty_level = diff_override
                    if target_sp:
                        existing_card.sprint = target_sp
                    if target_ass:
                        existing_card.assignee = target_ass
                    existing_card.save()
                    updated_count += 1
                else:
                    KanbanCard.objects.create(
                        project=project,
                        column=target_col,
                        title=issue_data.get("summary") or issue_data["key"],
                        description=issue_data.get("description") or "",
                        jira_key=issue_data["key"],
                        jira_issue_id=int(issue_data["id"]) if issue_data.get("id") and str(issue_data["id"]).isdigit() else None,
                        difficulty_level=diff_override,
                        initial_difficulty_level=diff_override,
                        assignee=target_ass,
                        sprint=target_sp,
                        is_extra=False,
                    )
                    imported_count += 1
        finally:
            service.close()

        if imported_count == 1 and updated_count == 0:
            messages.success(request, f"'{keys_to_import[0]}' işi Jira'dan başarıyla panoya eklendi.")
        elif imported_count > 1:
            messages.success(request, f"{imported_count} adet Jira işi başarıyla panoya eklendi.")
        if updated_count > 0:
            messages.info(request, f"{updated_count} adet iş zaten panoda mevcuttu ve güncellendi.")

        return redirect("board", project_id=project.id)

    # Search & Listing execution
    raw_issues = []
    search_error = ""

    if project.jira_connection and project.jira_connection.is_valid:
        service = JiraService()
        try:
            jql_query = build_open_issues_jql(search_jql, project.key)
            try:
                raw_issues = service.pull_project_issues(project, jql_query, max_results=100)
            except Exception as exc:
                err_str = str(exc).lower()
                if any(x in err_str for x in ["connection", "timeout", "unreachable", "dns", "refused", "name or service not known", "401", "403"]):
                    raise exc
                logger.info("JQL primary query (%s) başarısız oldu: %s, fallback deneniyor", jql_query, exc)
                fallback_jql = build_fallback_open_issues_jql(search_jql, project.key)
                try:
                    raw_issues = service.pull_project_issues(project, fallback_jql, max_results=100)
                except Exception as exc2:
                    err_str2 = str(exc2).lower()
                    if any(x in err_str2 for x in ["connection", "timeout", "unreachable", "dns", "refused", "name or service not known", "401", "403"]):
                        raise exc2
                    logger.info("JQL fallback (%s) başarısız oldu: %s, yalın sorgu deneniyor", fallback_jql, exc2)
                    raw_jql = search_jql if search_jql else (f'project = "{project.key}"' if project.key else "")
                    if raw_jql:
                        raw_issues = service.pull_project_issues(project, raw_jql, max_results=100)
                    else:
                        raise exc2
        except Exception as exc:
            search_error = str(exc)
            logger.warning("Jira JQL araması başarısız (%s): %s", search_jql, exc)
            local_qs = JiraIssue.objects.filter(project=project)
            raw_issues = [
                {
                    "id": str(i.jira_id),
                    "key": i.jira_key,
                    "summary": i.summary,
                    "description": i.description,
                    "status_key": i.status_key,
                    "status_id": i.status_id,
                    "assignee": i.assignee,
                    "reporter": i.reporter,
                    "created": i.created,
                    "updated": i.updated,
                    "sprint": i.sprint,
                    "epic_key": i.epic_key,
                    "blocks": i.blocks,
                    "blocked_by": i.blocked_by,
                }
                for i in local_qs
            ]
        finally:
            service.close()

    # Filter out closed issues and already added cards
    filtered_issues = []
    for issue in raw_issues:
        # 1. Closed issues MUST NEVER appear
        if is_issue_closed(issue):
            continue
        # 2. Already added issues MUST BE CLEANED OUT
        if issue.get("key") in existing_keys:
            continue
        filtered_issues.append(issue)

    return render(
        request,
        "kanbanapp/kanban_card_import_jira.html",
        {
            "project": project,
            "columns": columns,
            "sprints": sprints,
            "members": members,
            "issues": filtered_issues,
            "current_jql": search_jql,
            "default_jql": default_jql,
            "search_error": search_error,
            "existing_cards_count": len(existing_keys),
            "fibonacci_choices": FIBONACCI_DIFFICULTIES,
        },
    )


@login_required
def kanban_card_jira_refresh_view(request, project_id, card_id):
    """Pull latest summary, description, and status from Jira for an existing card."""
    project = get_object_or_404(Project, id=project_id)
    card = get_object_or_404(KanbanCard, id=card_id, project=project)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if not card.jira_key:
        messages.error(request, "Bu kart bir Jira işine bağlı değil.")
        return redirect("board", project_id=project.id)

    if not project.jira_connection:
        messages.error(request, "Bu projeye atanmış bir Jira bağlantısı bulunmuyor.")
        return redirect("board", project_id=project.id)

    service = JiraService()
    try:
        issue_data = service.get_project_issue(project, card.jira_key)
        JiraIssue.objects.update_or_create(
            project=project,
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
        card.title = issue_data.get("summary") or card.title
        card.description = issue_data.get("description") or card.description
        if issue_data.get("id") and str(issue_data["id"]).isdigit():
            card.jira_issue_id = int(issue_data["id"])

        if project.sync_jira_status:
            status_key = issue_data.get("status_key")
            if status_key:
                mappings = StatusMapping.objects.filter(
                    project=project, jira_status__isnull=False
                ).filter(
                    Q(jira_status__name__iexact=status_key)
                    | Q(jira_status__jira_status_key__iexact=status_key)
                )
                already_in_mapped_column = mappings.filter(app_status=card.column).exists()
                if not already_in_mapped_column:
                    primary_mapping = (
                        mappings.filter(transfer_to_jira=True)
                        .order_by("-is_primary", "position", "id")
                        .first()
                    ) or mappings.order_by("-is_primary", "position", "id").first()
                    if primary_mapping and primary_mapping.app_status:
                        card.column = primary_mapping.app_status

        card.save()
        messages.success(request, f"'{card.jira_key}' detayları Jira'dan güncellendi (Durum: {status_key or 'Belirtilmedi'}).")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Jira'dan detaylar çekilirken hata oluştu: {exc}")
    finally:
        service.close()

    next_url = request.GET.get("next") or request.POST.get("next")
    return redirect(next_url or "board", project_id=project.id)


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
        next_url = request.POST.get("next") or request.GET.get("next")
        return redirect(next_url or "board", project_id=project.id)
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
        target_pos = request.POST.get("position")

        old_column = card.column
        card.column = target_column
        if target_pos is not None and str(target_pos).isdigit():
            card.position = int(target_pos)
        card.save()

        # Jira Transition (READ-WRITE) if card is linked and mapping exists
        skip_jira = (
            not project.sync_jira_status
            or request.POST.get("skip_jira_sync") == "1"
            or request.POST.get("sync_jira") == "0"
        )
        if card.jira_key and project.jira_connection:
            mapping = (
                StatusMapping.objects.filter(project=project, app_status=target_column, jira_status__isnull=False)
                .order_by("-is_primary", "position", "id")
                .first()
            )
            if mapping and mapping.jira_status:
                if not skip_jira and mapping.transfer_to_jira:
                    service = JiraService()
                    try:
                        service.transition_issue(project, card.jira_key, mapping.jira_status.name)
                        messages.success(request, f"Kart '{target_column.name}' durumuna taşındı ve Jira güncellendi ({mapping.jira_status.name}).")
                    except Exception as exc:  # noqa: BLE001
                        messages.warning(request, f"Kart taşındı fakat Jira geçişi başarısız: {exc}")
                    finally:
                        service.close()
                else:
                    messages.info(request, f"Kart '{target_column.name}' durumuna taşındı (Jira statü aktarımı yapılmadı).")
            else:
                messages.info(request, f"Kart '{target_column.name}' durumuna taşındı (Jira durum eşlemesi yok).")
        else:
            messages.success(request, f"Kart '{target_column.name}' durumuna taşındı.")

    next_url = request.POST.get("next") or request.GET.get("next")
    return redirect(next_url or "board", project_id=project.id)


@login_required
def kanban_cards_reorder_view(request, project_id):
    """Reorder cards within a column via mouse drag-and-drop (PLAN.md §7)."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_edit_cards(request.user, project):
        return _forbidden(request)

    if request.method == "POST":
        import json

        data = {}
        if request.content_type == "application/json" and request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}
        if not data:
            data = request.POST

        column_id = data.get("column_id")
        card_ids = data.get("card_ids")

        if not column_id or not card_ids:
            return JsonResponse({"status": "error", "message": "Eksik parametreler (column_id, card_ids)."}, status=400)

        column = get_object_or_404(KanbanColumn, id=column_id, project=project)

        if isinstance(card_ids, str):
            try:
                card_ids = json.loads(card_ids)
            except Exception:
                card_ids = [int(x.strip()) for x in card_ids.split(",") if x.strip().isdigit()]

        from django.db import transaction

        with transaction.atomic():
            for position, card_id in enumerate(card_ids):
                try:
                    cid = int(card_id)
                    KanbanCard.objects.filter(project=project, id=cid).update(
                        column=column,
                        position=position,
                    )
                except (ValueError, TypeError):
                    continue

        return JsonResponse({"status": "ok", "message": "Kart sıralaması güncellendi."})

    return JsonResponse({"status": "error", "message": "Sadece POST metodu desteklenir."}, status=405)


@login_required
def kanban_columns_reorder_view(request, project_id):
    """Reorder columns on the kanban board via mouse drag-and-drop."""
    project = get_object_or_404(Project, id=project_id)
    if not (_can_manage_project(request.user, project) or _can_edit_cards(request.user, project)):
        return _forbidden(request)

    if request.method == "POST":
        import json

        data = {}
        if request.content_type == "application/json" and request.body:
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}
        if not data:
            data = request.POST

        column_ids = data.get("column_ids")
        if not column_ids:
            return JsonResponse({"status": "error", "message": "Eksik parametre (column_ids)."}, status=400)

        if isinstance(column_ids, str):
            try:
                column_ids = json.loads(column_ids)
            except Exception:
                column_ids = [int(x.strip()) for x in column_ids.split(",") if x.strip().isdigit()]

        from django.db import transaction

        with transaction.atomic():
            for position, col_id in enumerate(column_ids):
                try:
                    cid = int(col_id)
                    KanbanColumn.objects.filter(project=project, id=cid).update(position=position)
                except (ValueError, TypeError):
                    continue

        return JsonResponse({"status": "ok", "message": "Kolon sıralaması güncellendi."})

    return JsonResponse({"status": "error", "message": "Sadece POST metodu desteklenir."}, status=405)


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
            sub.is_extra = False
            sub.jira_key = f"{card.jira_key}-sub{card.sub_tasks.count() + 1}" if card.jira_key else ""
            sub.jira_issue_id = card.jira_issue_id
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


@login_required
def report_view(request, project_id):
    """Reports & metrics view with Chart.js and difficulty tracking (PLAN.md §4 & §7)."""
    project = get_object_or_404(Project, id=project_id)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    from django.db.models import Q

    cards = project.cards.all()
    columns = project.columns.all().order_by("position")
    sprints = project.sprints.all().order_by("-created_at")

    status_data = []
    for col in columns:
        status_data.append({
            "name": col.name,
            "count": cards.filter(column=col).count(),
        })

    sprint_data = []
    for s in sprints:
        sprint_data.append({
            "name": s.name,
            "total_difficulty": s.total_difficulty,
            "default_capacity": s.default_capacity,
        })

    can_view_drift = _can_manage_project(request.user, project)
    drift_cards = []
    if can_view_drift:
        drift_cards = cards.filter(
            Q(requested_difficulty_level__isnull=False) | Q(initial_difficulty_level__isnull=False)
        ).select_related("assignee", "column")

    return render(
        request,
        "kanbanapp/reports.html",
        {
            "project": project,
            "status_data": status_data,
            "sprint_data": sprint_data,
            "drift_cards": drift_cards,
            "can_view_drift": can_view_drift,
            "total_cards": cards.count(),
            "can_manage_project": _can_manage_project(request.user, project),
        },
    )


@login_required
def export_cards_csv(request, project_id):
    """CSV export of cards (PLAN.md §10 Faz 4)."""
    import csv
    from django.http import HttpResponse

    project = get_object_or_404(Project, id=project_id)
    if not _can_view_project(request.user, project):
        return _forbidden(request)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{project.key}_cards.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "ID", "Jira Key", "Başlık", "Kolon", "Zorluk", "Atanan", "Sprint", "Oluşturulma"
    ])

    for card in project.cards.all().select_related("column", "assignee", "sprint"):
        writer.writerow([
            card.id,
            card.jira_key or "",
            card.title,
            card.column.name,
            card.difficulty_level or "",
            card.assignee.username if card.assignee else "",
            card.sprint.name if card.sprint else "",
            card.created_at.strftime("%Y-%m-%d %H:%M"),
        ])

    return response

