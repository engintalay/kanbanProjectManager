from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import override_settings
from django.test.runner import TestCase
from django.urls import reverse

from .models import (
    JiraConnection,
    JiraIssue,
    JiraStatus,
    KanbanCard,
    KanbanColumn,
    Project,
    ProjectTicket,
    Role,
    StatusMapping,
    TicketAttachment,
    TicketComment,
)

User = get_user_model()


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class KanbanBoardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="badmin", password="pass12345")
        self.client = Client()
        self.client.force_login(self.user)
        self.project = Project.objects.create(key="BRD", name="Board Test", created_by=self.user)
        self.col = KanbanColumn.objects.create(project=self.project, name="To Do", status_type="custom", position=0)

    def test_board_view_renders_with_columns_and_cards(self):
        col = KanbanColumn.objects.create(project=self.project, name="To Do", status_type="custom", position=0)
        KanbanColumn.objects.create(project=self.project, name="Done", status_type="custom", position=1)
        KanbanCard.objects.create(project=self.project, column=col, title="First Task", is_extra=True)
        KanbanCard.objects.create(project=self.project, column=col, title="Second Task", is_extra=True)

        resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'class="board"', resp.content)
        self.assertIn(b"To Do", resp.content)
        self.assertIn(b"First Task", resp.content)
        self.assertIn(b"Second Task", resp.content)
        self.assertIn(b"Yeni Kart Ekle", resp.content)
        self.assertIn(b'draggable="true"', resp.content)
        self.assertIn(b"cardMoveModal", resp.content)
        self.assertIn(b"col-drag-handle", resp.content)
        self.assertIn(b"columns/reorder", resp.content)

    def test_column_and_card_crud_flow(self):
        col_resp = self.client.post(
            reverse("kanban_column_create", kwargs={"project_id": self.project.id}),
            {"name": "Backlog", "status_type": "custom", "position": 0},
        )
        self.assertEqual(col_resp.status_code, 302)
        col = KanbanColumn.objects.get(name="Backlog")

        JiraIssue.objects.create(project=self.project, jira_id="10001", jira_key="BRD-1", summary="Task One")
        self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": col.id, "jira_key": "BRD-1"},
        )
        self.assertEqual(KanbanCard.objects.count(), 1)
        self.assertEqual(KanbanCard.objects.first().jira_key, "BRD-1")
        self.assertEqual(KanbanCard.objects.first().title, "Task One")

        self.client.post(
            reverse("kanban_card_edit", kwargs={"project_id": self.project.id, "card_id": 1}),
            {"column": col.id, "jira_key": "BRD-1", "difficulty_level": 3},
        )
        self.assertEqual(KanbanCard.objects.first().difficulty_level, 3)

        self.client.post(
            reverse("kanban_card_delete", kwargs={"project_id": self.project.id, "card_id": 1}),
        )
        self.assertEqual(KanbanCard.objects.count(), 0)

        self.client.post(
            reverse("kanban_column_edit", kwargs={"project_id": self.project.id, "column_id": 1}),
            {"name": "Backlog Renamed", "status_type": "custom", "position": 0},
        )
        self.assertTrue(KanbanColumn.objects.filter(name="Backlog Renamed").exists())

        self.client.post(
            reverse("kanban_column_delete", kwargs={"project_id": self.project.id, "column_id": 1}),
        )
        self.assertFalse(KanbanColumn.objects.filter(name="Backlog Renamed").exists())

    def test_board_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_card_linked_to_jira_issue(self):
        issue = JiraIssue.objects.create(project=self.project, jira_id="10000", jira_key="BRD-1")
        resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col.id, "title": "Linked Task", "description": "d", "jira_key": "BRD-1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(KanbanCard.objects.count(), 1)
        card = KanbanCard.objects.first()
        self.assertEqual(card.jira_issue_id, int(issue.jira_id))
        self.assertEqual(card.jira_key, "BRD-1")

    def test_unknown_jira_key_rejected(self):
        resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col.id, "title": "Ghost", "description": "d", "jira_key": "NOPE-999"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bu projede böyle bir Jira issue yok.")
        self.assertEqual(KanbanCard.objects.count(), 0)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class StatusMappingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="badmin", password="pass12345")
        self.client = Client()
        self.client.force_login(self.user)
        self.project = Project.objects.create(key="BRD", name="Board Test", created_by=self.user)
        self.col = KanbanColumn.objects.create(project=self.project, name="To Do", status_type="custom", position=0)
        self.jira_status = JiraStatus.objects.create(jira_status_key="inprogress", name="In Progress")

    def test_create_status_mapping(self):
        resp = self.client.post(
            reverse("status_mapping_create", kwargs={"project_id": self.project.id, "column_id": self.col.id}),
            {"jira_status": self.jira_status.id, "position": 0},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("board", kwargs={"project_id": self.project.id}))
        mapping = StatusMapping.objects.get(app_status=self.col)
        self.assertEqual(mapping.jira_status_id, self.jira_status.id)

    def test_create_without_jira_status(self):
        resp = self.client.post(
            reverse("status_mapping_create", kwargs={"project_id": self.project.id, "column_id": self.col.id}),
            {"jira_status": "", "position": 0},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(StatusMapping.objects.filter(app_status=self.col, jira_status__isnull=True).exists())

    def test_edit_status_mapping(self):
        StatusMapping.objects.create(project=self.project, app_status=self.col, jira_status=self.jira_status)
        other = JiraStatus.objects.create(jira_status_key="done", name="Done")
        resp = self.client.post(
            reverse("status_mapping_edit", kwargs={"project_id": self.project.id, "mapping_id": 1}),
            {"jira_status": other.id, "position": 5},
        )
        self.assertEqual(resp.status_code, 302)
        mapping = StatusMapping.objects.get(app_status=self.col)
        self.assertEqual(mapping.jira_status_id, other.id)
        self.assertEqual(mapping.position, 5)

    def test_delete_status_mapping(self):
        StatusMapping.objects.create(project=self.project, app_status=self.col, jira_status=self.jira_status)
        resp = self.client.post(
            reverse("status_mapping_delete", kwargs={"project_id": self.project.id, "mapping_id": 1}),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(StatusMapping.objects.filter(app_status=self.col).exists())

    def test_board_shows_status_mapping(self):
        StatusMapping.objects.create(project=self.project, app_status=self.col, jira_status=self.jira_status)
        resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"In Progress", resp.content)

    def test_duplicate_mapping_rejected(self):
        StatusMapping.objects.create(project=self.project, app_status=self.col, jira_status=self.jira_status)
        resp = self.client.post(
            reverse("status_mapping_create", kwargs={"project_id": self.project.id, "column_id": self.col.id}),
            {"jira_status": self.jira_status.id, "position": 1},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "zaten bir eşleme")
        self.assertEqual(StatusMapping.objects.filter(app_status=self.col).count(), 1)

    def test_status_mapping_requires_permission(self):
        programmer_role, _ = Role.objects.get_or_create(
            name="Proje Programcısı", slug="programmer", level=Role.LEVEL_PROGRAMMER, defaults={"description": "test"}
        )
        programmer = User.objects.create_user(
            username="prog", password="pass12345", email="p@e.com", role=programmer_role
        )
        self.client.logout()
        self.client.force_login(programmer)
        resp = self.client.get(
            reverse("status_mapping_create", kwargs={"project_id": self.project.id, "column_id": self.col.id})
        )
        self.assertEqual(resp.status_code, 403)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class BugFixesAndPermissionsTests(TestCase):
    def setUp(self):
        self.admin_role = Role.objects.create(name="Admin", slug="admin", level=Role.LEVEL_ADMIN)
        self.pm_role = Role.objects.create(name="Proje Yöneticisi", slug="pm", level=Role.LEVEL_PROJECT_MANAGER)
        self.prog_role = Role.objects.create(name="Proje Programcısı", slug="prog", level=Role.LEVEL_PROGRAMMER)
        self.viewer_role = Role.objects.create(name="İzleyici", slug="viewer", level=Role.LEVEL_VIEWER)

        self.admin = User.objects.create_superuser(username="admin", password="p", email="a@e.com", role=self.admin_role)
        self.pm = User.objects.create_user(username="pm_user", password="p", email="pm@e.com", role=self.pm_role)
        self.project = Project.objects.create(key="PRJ", name="Project 1", created_by=self.pm)
        self.prog = User.objects.create_user(username="prog_user", password="p", email="pr@e.com", role=self.prog_role, project=self.project)
        self.viewer = User.objects.create_user(username="viewer_user", password="p", email="v@e.com", role=self.viewer_role)

        self.col = KanbanColumn.objects.create(project=self.project, name="Todo", status_type="custom", position=0)
        self.client = Client()

    def test_encrypted_char_field_roundtrip(self):
        from .models import JiraConnection
        conn = JiraConnection.objects.create(
            name="Test Jira", host="https://jira.example.com", username="admin", password="super_secret_password"
        )
        loaded = JiraConnection.objects.get(id=conn.id)
        self.assertEqual(loaded.password, "super_secret_password")

    def test_project_edit_preserves_key(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("project_edit", kwargs={"project_id": self.project.id}),
            {"name": "Project 1 Updated", "key": "PRJ", "description": "new desc"},
        )
        self.assertEqual(resp.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Project 1 Updated")

    def test_project_create_and_edit_with_jira_connection(self):
        from .models import JiraConnection

        conn = JiraConnection.objects.create(name="Dev Jira", host="https://jira.dev.lan", username="u", password="p")
        self.client.force_login(self.admin)
        create_resp = self.client.post(
            reverse("project_create"),
            {"name": "New Jira Project", "key": "NJP", "description": "desc", "jira_connection": conn.id},
        )
        self.assertEqual(create_resp.status_code, 302)
        njp = Project.objects.get(key="NJP")
        self.assertEqual(njp.jira_connection_id, conn.id)

        # Edit and remove / switch connection
        edit_resp = self.client.post(
            reverse("project_edit", kwargs={"project_id": njp.id}),
            {"name": "New Jira Project", "key": "NJP", "description": "desc", "jira_connection": ""},
        )
        self.assertEqual(edit_resp.status_code, 302)
        njp.refresh_from_db()
        self.assertIsNone(njp.jira_connection)

        # View board of project without jira: banner is displayed
        board_resp = self.client.get(reverse("board", kwargs={"project_id": njp.id}))
        self.assertEqual(board_resp.status_code, 200)
        self.assertContains(board_resp, "Bu Projeye Bağlı Bir Jira Bulunmuyor")

    def test_context_processor_current_user_no_crash(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Verify current_user renders without lambda argument error
        self.assertTrue(resp.context["is_admin"])
        self.assertTrue(resp.context["can_manage_jira"])
        self.assertEqual(resp.context["role_level"], 1)

    def test_programmer_can_view_board_and_create_card(self):
        self.client.force_login(self.prog)
        resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Yeni Kart Ekle", resp.content)

        JiraIssue.objects.create(project=self.project, jira_id="99001", jira_key="PRJ-1", summary="Prog Task")
        card_resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col.id, "jira_key": "PRJ-1"},
        )
        self.assertEqual(card_resp.status_code, 302)
        self.assertEqual(KanbanCard.objects.filter(jira_key="PRJ-1").count(), 1)

    def test_viewer_can_view_board_but_cannot_create_card(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"Yeni Kart Ekle", resp.content)

        card_resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col.id, "title": "Unauthorized Task", "description": "d", "is_extra": True},
        )
        self.assertEqual(card_resp.status_code, 403)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class SprintAndCardWorkflowTests(TestCase):
    def setUp(self):
        self.admin_role = Role.objects.create(name="Admin", slug="admin", level=Role.LEVEL_ADMIN)
        self.pm_role = Role.objects.create(name="Proje Yöneticisi", slug="pm", level=Role.LEVEL_PROJECT_MANAGER)
        self.prog_role = Role.objects.create(name="Proje Programcısı", slug="prog", level=Role.LEVEL_PROGRAMMER)

        self.pm = User.objects.create_user(username="pm_lead", password="p", email="pm@e.com", role=self.pm_role)
        self.project = Project.objects.create(key="SPR", name="Sprint Project", created_by=self.pm)
        self.prog = User.objects.create_user(username="prog_dev", password="p", email="dev@e.com", role=self.prog_role, project=self.project)

        self.col_todo = KanbanColumn.objects.create(project=self.project, name="To Do", status_type="custom", position=0)
        self.col_done = KanbanColumn.objects.create(project=self.project, name="Done", status_type="custom", position=1)

        self.client = Client()

    def test_sprint_crud_and_capacity(self):
        self.client.force_login(self.pm)
        create_resp = self.client.post(
            reverse("sprint_create", kwargs={"project_id": self.project.id}),
            {"name": "Sprint 1", "duration": "2_hafta", "status": "planning"},
        )
        self.assertEqual(create_resp.status_code, 302)
        from .models import Sprint
        sprint = Sprint.objects.get(name="Sprint 1")
        self.assertEqual(sprint.duration, "2_hafta")

        # Add cards to sprint
        card1 = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Task 1", difficulty_level=8, sprint=sprint)
        card2 = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Task 2", difficulty_level=13, sprint=sprint)

        self.assertEqual(sprint.total_difficulty, 21)
        self.assertEqual(sprint.default_capacity, 40)
        self.assertTrue(sprint.is_under_capacity)  # 21/40 = 52% < 75%

        # Sprint board view
        board_resp = self.client.get(reverse("sprint_board", kwargs={"project_id": self.project.id, "sprint_id": sprint.id}))
        self.assertEqual(board_resp.status_code, 200)
        self.assertIn(b"Sprint 1", board_resp.content)
        self.assertIn(b"Task 1", board_resp.content)
        self.assertIn(b"container-fluid", board_resp.content)

        # Standard board view
        kanban_resp = self.client.get(reverse("board", kwargs={"project_id": self.project.id}))
        self.assertEqual(kanban_resp.status_code, 200)
        self.assertIn(b"container-fluid", kanban_resp.content)

    def test_card_move_between_columns(self):
        card = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Movable Task")
        self.client.force_login(self.prog)
        move_resp = self.client.post(
            reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": card.id}),
            {"column_id": self.col_done.id},
        )
        self.assertEqual(move_resp.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.column_id, self.col_done.id)

    def test_programmer_self_assign_and_cannot_unassign(self):
        card = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Unassigned Task")
        self.client.force_login(self.prog)

        # Self-assign
        resp = self.client.post(reverse("kanban_card_assign", kwargs={"project_id": self.project.id, "card_id": card.id}))
        self.assertEqual(resp.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.assignee, self.prog)

        # Programmer cannot unassign
        resp2 = self.client.post(reverse("kanban_card_assign", kwargs={"project_id": self.project.id, "card_id": card.id}))
        card.refresh_from_db()
        self.assertEqual(card.assignee, self.prog)  # still assigned

    def test_issue_request_and_pm_approval(self):
        from .models import IssueRequest
        card = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Hard Task", difficulty_level=8, assignee=self.prog)
        self.client.force_login(self.prog)

        # Request difficulty change to 55 (PLAN.md §7: programmer only option)
        req_resp = self.client.post(
            reverse("card_request_create", kwargs={"project_id": self.project.id, "card_id": card.id}),
            {"type": IssueRequest.TYPE_DIFFICULTY, "reason": "too_hard", "requested_difficulty": 55, "description": "Too hard"},
        )
        self.assertEqual(req_resp.status_code, 302)
        req_obj = IssueRequest.objects.get(card=card)
        self.assertEqual(req_obj.requested_difficulty, 55)
        self.assertEqual(req_obj.status, IssueRequest.STATUS_PENDING)

        # PM approves request
        self.client.force_login(self.pm)
        action_resp = self.client.post(
            reverse("issue_request_action", kwargs={"project_id": self.project.id, "request_id": req_obj.id, "action": "approve"})
        )
        self.assertEqual(action_resp.status_code, 302)
        req_obj.refresh_from_db()
        self.assertEqual(req_obj.status, IssueRequest.STATUS_APPROVED)

        card.refresh_from_db()
        self.assertEqual(card.difficulty_level, 55)
        self.assertEqual(card.requested_difficulty_level, 55)

    def test_card_split_into_subtasks(self):
        card = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Big Feature", difficulty_level=34)
        self.client.force_login(self.pm)

        split_resp = self.client.post(
            reverse("card_split", kwargs={"project_id": self.project.id, "card_id": card.id}),
            {"title": "Subtask 1 - Frontend", "difficulty_level": 5, "description": "UI work"},
        )
        self.assertEqual(split_resp.status_code, 302)

        card.refresh_from_db()
        # PLAN.md §7: "Ana işin zorluk seviyesi bölünürken 0'a düşürülür."
        self.assertEqual(card.difficulty_level, 0)
        self.assertEqual(card.sub_tasks.count(), 1)
        sub = card.sub_tasks.first()
        self.assertEqual(sub.title, "Subtask 1 - Frontend")
        self.assertEqual(sub.difficulty_level, 5)
        self.assertTrue(sub.is_sub_task)

    def test_reports_view_and_csv_export(self):
        self.client.force_login(self.pm)
        KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Card 1", difficulty_level=5, initial_difficulty_level=3)
        report_resp = self.client.get(reverse("project_reports", kwargs={"project_id": self.project.id}))
        self.assertEqual(report_resp.status_code, 200)
        self.assertIn(b"Raporlar", report_resp.content)
        self.assertIn(b"Zorluk De\xc4\x9fi\xc5\x9fim & De\xc4\x9ferlendirme", report_resp.content)

        # CSV Export test
        csv_resp = self.client.get(reverse("export_cards_csv", kwargs={"project_id": self.project.id}))
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"Card 1", csv_resp.content)
        self.assertIn(b"SPR_cards.csv", csv_resp["Content-Disposition"].encode())

    def test_admin_and_app_static_files_served(self):
        admin_css = self.client.get("/static/admin/css/base.css")
        self.assertEqual(admin_css.status_code, 200)

        app_css = self.client.get("/static/css/style.css")
        self.assertEqual(app_css.status_code, 200)

        admin_login = self.client.get("/admin/login/")
        self.assertEqual(admin_login.status_code, 200)

    def test_is_local_host_and_normalize_no_proxy(self):
        from .services import is_local_host, normalize_no_proxy
        import os

        # Test local detection
        self.assertTrue(is_local_host("http://localhost:8000"))
        self.assertTrue(is_local_host("https://127.0.0.1:443"))
        self.assertTrue(is_local_host("https://10.150.1.20:8443"))
        self.assertTrue(is_local_host("https://192.168.1.50"))
        self.assertTrue(is_local_host("https://jira.gelirler.gov.tr"))
        self.assertTrue(is_local_host("https://myhost.gib.gov.tr"))
        self.assertFalse(is_local_host("https://jira.atlassian.net"))

        # Test normalize_no_proxy
        orig_np = os.environ.get("NO_PROXY", "")
        try:
            os.environ["NO_PROXY"] = "*.example.local,10.*"
            normalize_no_proxy()
            self.assertIn(".example.local", os.environ["NO_PROXY"])
            self.assertIn("example.local", os.environ["NO_PROXY"])
        finally:
            os.environ["NO_PROXY"] = orig_np

    def test_format_jira_error(self):
        from .services import format_jira_error
        import requests
        from unittest.mock import MagicMock
        from jira.exceptions import JIRAError

        # JIRAError with 401
        resp = MagicMock()
        resp.status_code = 401
        err_401 = JIRAError(text="<html><head><title>Unauthorized (401)</title></head><body>Basic Authentication Failure</body></html>", status_code=401, response=resp)
        formatted_401 = format_jira_error(err_401)
        self.assertIn("401", formatted_401)
        self.assertIn("Yetkilendirme", formatted_401)

        # Timeout
        t_err = requests.exceptions.ReadTimeout("Connection timed out")
        self.assertIn("Zaman aşımı", format_jira_error(t_err))

        # Proxy error
        p_err = requests.exceptions.ProxyError("Cannot connect to proxy")
        self.assertIn("Proxy", format_jira_error(p_err))

    def test_jira_connection_form_preserves_password(self):
        from .models import JiraConnection
        from .forms import JiraConnectionForm

        conn = JiraConnection.objects.create(
            name="Jira Auth Test",
            host="https://jira.gelirler.gov.tr",
            username="testuser",
            password="OriginalSecretPassword",
        )

        # Submit form with empty password
        form = JiraConnectionForm(
            data={"name": "Jira Auth Test Updated", "host": "https://jira.gelirler.gov.tr", "username": "testuser", "password": ""},
            instance=conn,
        )
        self.assertTrue(form.is_valid())
        updated = form.save()
        self.assertEqual(updated.password, "OriginalSecretPassword")

    def test_jira_test_connection_view_with_mock(self):
        from unittest.mock import patch
        from .models import JiraConnection

        conn = JiraConnection.objects.create(
            name="Mock Jira",
            host="https://jira.example.local",
            username="mockuser",
            password="mockpassword",
        )

        self.client.force_login(self.pm)

        # Test success flow
        with patch("kanbanapp.services.JiraClient.test_connection", return_value={"displayName": "Mock User", "name": "mockuser"}):
            resp = self.client.get(reverse("jira_test_connection", kwargs={"connection_id": conn.id}), follow=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Jira ba\xc4\x9flant\xc4\xb1s\xc4\xb1 ba\xc5\x9far\xc4\xb1l\xc4\xb1", resp.content)
            self.assertIn(b"Mock User", resp.content)

        # Test error flow
        with patch("kanbanapp.services.JiraClient.test_connection", side_effect=Exception("Sunucu bağlantısı koptu")):
            resp = self.client.get(reverse("jira_test_connection", kwargs={"connection_id": conn.id}), follow=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Jira ba\xc4\x9flant\xc4\xb1 hatas\xc4\xb1", resp.content)
            self.assertIn("Sunucu bağlantısı koptu".encode("utf-8"), resp.content)

    def test_register_view_roles_populated_and_user_created(self):
        admin = User.objects.create_user(username="admin_user_reg", password="p", email="adm_reg@e.com", role=self.admin_role)
        self.client.force_login(admin)

        # 1. GET /register/ - check roles in context and rendered HTML
        get_resp = self.client.get(reverse("register"))
        self.assertEqual(get_resp.status_code, 200)
        self.assertIn("roles", get_resp.context)
        self.assertTrue(len(get_resp.context["roles"]) > 0)
        self.assertIn(b"Proje Programc\xc4\xb1s\xc4\xb1", get_resp.content)

        # 2. POST /register/ - create user with role
        post_resp = self.client.post(
            reverse("register"),
            {
                "username": "new_developer",
                "email": "dev_new@example.com",
                "first_name": "Ahmet",
                "last_name": "Yılmaz",
                "password1": "SecurePass123",
                "password2": "SecurePass123",
                "role": str(self.prog_role.id),
            },
            follow=True,
        )
        self.assertEqual(post_resp.status_code, 200)
        created = User.objects.filter(username="new_developer").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.email, "dev_new@example.com")
        self.assertEqual(created.role_id, self.prog_role.id)
        self.assertEqual(created.first_name, "Ahmet")
        self.assertEqual(created.last_name, "Yılmaz")

    def test_project_delete_with_cards_and_columns_no_500(self):
        # Create a dedicated project with columns, cards, sprint, and status mapping
        p = Project.objects.create(name="Project To Delete", key="DELPRJ", created_by=self.pm)
        col1 = KanbanColumn.objects.create(project=p, name="Col1", position=0)
        col2 = KanbanColumn.objects.create(project=p, name="Col2", position=1)
        card1 = KanbanCard.objects.create(project=p, column=col1, title="Card 1")
        card2 = KanbanCard.objects.create(project=p, column=col2, title="Card 2")
        StatusMapping.objects.create(project=p, app_status=col1, position=0)

        self.client.force_login(self.pm)
        resp = self.client.post(reverse("project_delete", kwargs={"project_id": p.id}), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Project.objects.filter(key="DELPRJ").exists())
        self.assertFalse(KanbanCard.objects.filter(id__in=[card1.id, card2.id]).exists())
        self.assertFalse(KanbanColumn.objects.filter(id__in=[col1.id, col2.id]).exists())
        self.assertIn(b"ba\xc5\x9far\xc4\xb1yla silindi", resp.content)

    def test_column_delete_with_cards_blocked(self):
        p = Project.objects.create(name="Col Delete Test", key="COLDEL", created_by=self.pm)
        col = KanbanColumn.objects.create(project=p, name="Busy Col", position=0)
        KanbanCard.objects.create(project=p, column=col, title="Busy Card")

        self.client.force_login(self.pm)
        resp = self.client.post(reverse("kanban_column_delete", kwargs={"project_id": p.id, "column_id": col.id}), follow=True)
        self.assertEqual(resp.status_code, 200)
        # Column must still exist
        self.assertTrue(KanbanColumn.objects.filter(id=col.id).exists())
        self.assertIn("kartlar bulunmaktadır".encode("utf-8"), resp.content)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class JiraImportAndSyncTests(TestCase):
    def setUp(self):
        from unittest.mock import MagicMock
        from .models import JiraConnection, Sprint

        self.admin_role = Role.objects.create(name="Admin", slug="admin", level=Role.LEVEL_ADMIN)
        self.pm_role = Role.objects.create(name="Proje Yöneticisi", slug="pm", level=Role.LEVEL_PROJECT_MANAGER)
        self.prog_role = Role.objects.create(name="Proje Programcısı", slug="prog", level=Role.LEVEL_PROGRAMMER)
        self.viewer_role = Role.objects.create(name="İzleyici", slug="viewer", level=Role.LEVEL_VIEWER)

        self.admin = User.objects.create_superuser(username="admin_user", password="p", email="adm@e.com", role=self.admin_role)
        self.pm = User.objects.create_user(username="pm_jira", password="p", email="pm_j@e.com", role=self.pm_role)
        self.prog = User.objects.create_user(username="prog_jira", password="p", email="prog_j@e.com", role=self.prog_role)
        self.viewer = User.objects.create_user(username="view_jira", password="p", email="view_j@e.com", role=self.viewer_role)

        self.conn = JiraConnection.objects.create(
            name="Test Jira",
            host="https://jira.example.local",
            username="testuser",
            password="secretpassword",
            created_by=self.pm,
        )
        self.project = Project.objects.create(
            key="KONF",
            name="Konfigürasyon Projesi",
            jira_connection=self.conn,
            created_by=self.pm,
        )
        self.prog.project = self.project
        self.prog.save()
        self.col_todo = KanbanColumn.objects.create(project=self.project, name="Yapılacak", position=0)
        self.col_doing = KanbanColumn.objects.create(project=self.project, name="Geliştirmede", position=1)
        self.col_done = KanbanColumn.objects.create(project=self.project, name="Tamamlandı", position=2)

        self.client = Client()

    def test_sync_statuses_creates_jira_status_objects(self):
        from unittest.mock import MagicMock, patch
        from .services import JiraService

        dummy_status1 = MagicMock()
        dummy_status1.name = "In Progress"
        dummy_status1.id = "3"
        dummy_status1.statusCategory = {"key": "indeterminate", "colorName": "yellow"}

        dummy_status2 = MagicMock()
        dummy_status2.name = "Done"
        dummy_status2.id = "6"
        dummy_status2.statusCategory = {"key": "done", "colorName": "green"}

        service = JiraService()
        with patch.object(service, "connect", return_value={"name": "testuser"}):
            service.client = MagicMock()
            service.client.jira.statuses.return_value = [dummy_status1, dummy_status2]
            count = service.sync_statuses()
            self.assertEqual(count, 2)

        self.assertTrue(JiraStatus.objects.filter(jira_status_key="In Progress").exists())
        self.assertTrue(JiraStatus.objects.filter(jira_status_key="Done").exists())
        s1 = JiraStatus.objects.get(jira_status_key="In Progress")
        self.assertEqual(s1.jira_id, 3)
        self.assertEqual(s1.color.get("colorName"), "yellow")

    def test_jira_sync_statuses_view_success(self):
        from unittest.mock import patch

        self.client.force_login(self.pm)
        with patch("kanbanapp.views.JiraService.sync_statuses", return_value=5):
            resp = self.client.get(reverse("jira_sync_statuses", kwargs={"connection_id": self.conn.id}), follow=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("5 adet statü başarıyla çekildi".encode("utf-8"), resp.content)

    def test_jira_sync_statuses_view_permission_denied_for_programmer(self):
        self.client.force_login(self.prog)
        resp = self.client.get(reverse("jira_sync_statuses", kwargs={"connection_id": self.conn.id}))
        self.assertEqual(resp.status_code, 403)

    def test_project_jira_sync_statuses_view_success(self):
        from unittest.mock import patch

        self.client.force_login(self.pm)
        with patch("kanbanapp.views.JiraService.sync_statuses", return_value=8):
            resp = self.client.get(reverse("project_jira_sync_statuses", kwargs={"project_id": self.project.id}), follow=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("8 adet statü başarıyla çekildi".encode("utf-8"), resp.content)

    def test_kanban_card_import_jira_view_creates_card_and_maps_status(self):
        from unittest.mock import patch

        # Create JiraStatus and StatusMapping for "In Progress" -> col_doing
        js = JiraStatus.objects.create(jira_status_key="In Progress", name="In Progress", jira_id=3)
        StatusMapping.objects.create(project=self.project, app_status=self.col_doing, jira_status=js)

        mock_issue = {
            "id": "10042",
            "key": "KONF-42",
            "summary": "Veritabanı migration hatası çözülecek",
            "description": "Migration dosyaları sıralanacak",
            "status_key": "In Progress",
            "status_id": 3,
            "assignee": "prog_jira",
            "reporter": "pm_jira",
            "created": "2026-09-29",
            "updated": "2026-09-29",
            "sprint": None,
            "epic_key": None,
            "blocks": [],
            "blocked_by": [],
        }

        self.client.force_login(self.pm)

        # GET should render import form
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=[]):
            get_resp = self.client.get(reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}))
            self.assertEqual(get_resp.status_code, 200)
            self.assertIn("Jira'dan İş Ekle".encode("utf-8"), get_resp.content)

        # POST with issue key
        with patch("kanbanapp.views.JiraService.get_project_issue", return_value=mock_issue):
            post_resp = self.client.post(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {
                    "jira_key": "KONF-42",
                    "difficulty_level": "5",
                },
                follow=True,
            )
            self.assertEqual(post_resp.status_code, 200)
            self.assertContains(post_resp, "panoya eklendi")

        # Verify card
        card = KanbanCard.objects.filter(project=self.project, jira_key="KONF-42").first()
        self.assertIsNotNone(card)
        self.assertEqual(card.title, "Veritabanı migration hatası çözülecek")
        self.assertEqual(card.description, "Migration dosyaları sıralanacak")
        self.assertEqual(card.jira_issue_id, 10042)
        self.assertEqual(card.difficulty_level, 5)
        # Verify it mapped to col_doing
        self.assertEqual(card.column_id, self.col_doing.id)

        # Verify JiraIssue snapshot
        jissue = JiraIssue.objects.filter(project=self.project, jira_key="KONF-42").first()
        self.assertIsNotNone(jissue)
        self.assertEqual(jissue.summary, "Veritabanı migration hatası çözülecek")
        self.assertEqual(jissue.status_key, "In Progress")

    def test_kanban_card_import_jira_updates_existing_card(self):
        from unittest.mock import patch

        card = KanbanCard.objects.create(
            project=self.project,
            column=self.col_todo,
            title="Eski Başlık",
            jira_key="KONF-10",
        )

        mock_issue = {
            "id": "10010",
            "key": "KONF-10",
            "summary": "Yeni Güncel Başlık",
            "description": "Yeni Açıklama",
            "status_key": "Yapılacak",
            "status_id": 1,
            "assignee": None,
            "reporter": None,
            "created": "",
            "updated": "",
            "sprint": None,
            "epic_key": None,
            "blocks": [],
            "blocked_by": [],
        }

        self.client.force_login(self.prog)
        with patch("kanbanapp.views.JiraService.get_project_issue", return_value=mock_issue):
            post_resp = self.client.post(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jira_key": "KONF-10"},
                follow=True,
            )
            self.assertEqual(post_resp.status_code, 200)
            self.assertContains(post_resp, "zaten panoda mevcuttu")

        card.refresh_from_db()
        self.assertEqual(card.title, "Yeni Güncel Başlık")
        self.assertEqual(card.description, "Yeni Açıklama")

    def test_kanban_card_jira_refresh_view(self):
        from unittest.mock import patch

        js_done = JiraStatus.objects.create(jira_status_key="Done", name="Done", jira_id=6)
        StatusMapping.objects.create(project=self.project, app_status=self.col_done, jira_status=js_done)

        card = KanbanCard.objects.create(
            project=self.project,
            column=self.col_todo,
            title="Önceki Başlık",
            description="Önceki açıklama",
            jira_key="KONF-99",
            jira_issue_id=10099,
        )

        mock_updated = {
            "id": "10099",
            "key": "KONF-99",
            "summary": "Jira'da Güncellenmiş Başlık",
            "description": "Jira'da Güncellenmiş Açıklama",
            "status_key": "Done",
            "status_id": 6,
            "assignee": "prog_jira",
            "reporter": "pm_jira",
            "created": "",
            "updated": "2026-09-29T10:00:00",
            "sprint": None,
            "epic_key": None,
            "blocks": [],
            "blocked_by": [],
        }

        self.client.force_login(self.prog)
        with patch("kanbanapp.views.JiraService.get_project_issue", return_value=mock_updated):
            resp = self.client.get(
                reverse("kanban_card_jira_refresh", kwargs={"project_id": self.project.id, "card_id": card.id}),
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "güncellendi")

        card.refresh_from_db()
        self.assertEqual(card.title, "Jira'da Güncellenmiş Başlık")
        self.assertEqual(card.description, "Jira'da Güncellenmiş Açıklama")
        # Column should have updated to col_done via StatusMapping
        self.assertEqual(card.column_id, self.col_done.id)

    def test_card_without_jira_key_rejected(self):
        self.client.force_login(self.prog)
        resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col_todo.id, "title": "Unlinked Task"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jira")
        self.assertEqual(KanbanCard.objects.filter(title="Unlinked Task").count(), 0)

    def test_refresh_project_updates_existing_card_contents_from_jira(self):
        from unittest.mock import patch

        card = KanbanCard.objects.create(
            project=self.project,
            column=self.col_todo,
            title="Eski Başlık",
            description="Eski Açıklama",
            jira_key="KONF-77",
            jira_issue_id=777,
        )

        mock_pull = [
            {
                "id": "777",
                "key": "KONF-77",
                "summary": "Jira'da Değişen Başlık",
                "description": "Jira'da Değişen Açıklama",
                "status_key": "Yapılacak",
                "status_id": 1,
                "assignee": None,
                "reporter": None,
                "created": "",
                "updated": "2026-09-29T11:00:00",
                "sprint": None,
                "epic_key": None,
                "blocks": [],
                "blocked_by": [],
            }
        ]

        self.client.force_login(self.pm)
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_pull), \
             patch("kanbanapp.views.JiraService.sync_statuses", return_value=1):
            resp = self.client.post(reverse("refresh_project", kwargs={"project_id": self.project.id}), follow=True)
            self.assertEqual(resp.status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.title, "Jira'da Değişen Başlık")
        self.assertEqual(card.description, "Jira'da Değişen Açıklama")


class CardEditJiraFormatTests(TestCase):
    def setUp(self):
        self.pm_role = Role.objects.create(name="Proje Yöneticisi", slug="pm", level=Role.LEVEL_PROJECT_MANAGER)
        self.pm = User.objects.create_user(username="pm_user", password="x", email="pm@test.local", role=self.pm_role)
        self.project = Project.objects.create(name="Proje 1", key="PRJ", created_by=self.pm)
        self.col = KanbanColumn.objects.create(project=self.project, name="To Do", position=0)
        from .models import JiraIssue
        self.jira_issue = JiraIssue.objects.create(
            project=self.project,
            jira_key="PRJ-101",
            jira_id="101",
            summary="Örnek İş",
            description="h2. Başlık\n*bold*\n{code:python}\nprint('hello')\n{code}\n<script>alert(1)</script>",
        )
        self.card = KanbanCard.objects.create(
            project=self.project,
            column=self.col,
            title="Örnek İş",
            description=self.jira_issue.description,
            jira_key="PRJ-101",
            difficulty_level=3,
        )

    def test_render_jira_markup_formatting_and_security(self):
        from kanbanapp.templatetags.jira_filters import render_jira_markup
        html_out = render_jira_markup(self.card.description)
        # Check headings
        self.assertIn('<h2 class="jira-h2">Başlık</h2>', html_out)
        # Check bold
        self.assertIn("<strong>bold</strong>", html_out)
        # Check code block with safe escaped code
        self.assertIn('<pre class="jira-code-block"><code>print(&#x27;hello&#x27;)</code></pre>', html_out)
        # Check XSS prevention: <script> must be escaped
        self.assertNotIn("<script>", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_card_edit_view_renders_wide_layout_and_description(self):
        self.client.force_login(self.pm)
        resp = self.client.get(
            reverse("kanban_card_edit", kwargs={"project_id": self.project.id, "card_id": self.card.id})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "card-edit-wrapper")
        self.assertContains(resp, "jira-description-container")
        self.assertContains(resp, "PRJ-101")
        self.assertContains(resp, "jira-code-block")

    def test_card_edit_description_is_tamper_proof(self):
        self.client.force_login(self.pm)
        resp = self.client.post(
            reverse("kanban_card_edit", kwargs={"project_id": self.project.id, "card_id": self.card.id}),
            {
                "column": self.col.id,
                "difficulty_level": 5,
                "jira_key": "PRJ-101",
                "title": "Hacked Title",
                "description": "Hacked Description",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.card.refresh_from_db()
        # Difficulty should be updated
        self.assertEqual(self.card.difficulty_level, 5)
        # Title and description must remain intact from Jira!
        self.assertEqual(self.card.title, "Örnek İş")
        self.assertEqual(
            self.card.description,
            "h2. Başlık\n*bold*\n{code:python}\nprint('hello')\n{code}\n<script>alert(1)</script>",
        )

class ProjectAccessAndMemberTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username="admin_perm", password="p")
        self.pm_role, _ = Role.objects.get_or_create(
            slug="pm_perm_slug", defaults={"name": "Proje Yöneticisi Perm", "level": Role.LEVEL_PROJECT_MANAGER}
        )
        self.prog_role, _ = Role.objects.get_or_create(
            slug="prog_perm_slug", defaults={"name": "Proje Programcısı Perm", "level": Role.LEVEL_PROGRAMMER}
        )

    def test_assigned_project_manager_can_view_and_manage_project(self):
        pm_user = User.objects.create_user(username="pm_assigned", password="p", email="pm_a@test.com", role=self.pm_role)
        p = Project.objects.create(key="PRM", name="Permission Project", created_by=self.admin)
        from .models import ProjectMember
        ProjectMember.objects.create(project=p, user=pm_user)

        self.client.force_login(pm_user)
        # Dashboard lists the project
        dash_resp = self.client.get(reverse("dashboard"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, "Permission Project")

        # Projects list shows the project
        proj_resp = self.client.get(reverse("projects"))
        self.assertEqual(proj_resp.status_code, 200)
        self.assertContains(proj_resp, "Permission Project")

        # Board access is allowed
        board_resp = self.client.get(reverse("board", kwargs={"project_id": p.id}))
        self.assertEqual(board_resp.status_code, 200)
        self.assertTrue(board_resp.context["can_manage_project"])

    def test_project_member_programmer_can_view_project(self):
        prog_user = User.objects.create_user(username="prog_member", password="p", email="pr_m@test.com", role=self.prog_role)
        p = Project.objects.create(key="MBR", name="Member Project", created_by=self.admin)
        from .models import ProjectMember
        ProjectMember.objects.create(project=p, user=prog_user)

        self.client.force_login(prog_user)
        # Dashboard lists the project
        dash_resp = self.client.get(reverse("dashboard"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, "Member Project")

        # Board access is allowed
        board_resp = self.client.get(reverse("board", kwargs={"project_id": p.id}))
        self.assertEqual(board_resp.status_code, 200)

    def test_user_project_and_project_member_sync(self):
        p = Project.objects.create(key="SNC", name="Sync Project", created_by=self.admin)
        from .models import ProjectMember
        u = User.objects.create_user(username="sync_user", password="p", email="sync@test.com", project=p)
        # ProjectMember is auto-created on User save
        self.assertTrue(ProjectMember.objects.filter(project=p, user=u).exists())

        u2 = User.objects.create_user(username="sync_user2", password="p", email="sync2@test.com")
        self.assertIsNone(u2.project)
        pm = ProjectMember.objects.create(project=p, user=u2)
        u2.refresh_from_db()
        self.assertEqual(u2.project_id, p.id)


class JiraStatusSyncOptionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username="admin_sync_opt", password="p")
        self.conn = JiraConnection.objects.create(name="Sync Jira", host="https://jira.sync.local", username="u", password="p")
        self.project = Project.objects.create(key="JSO", name="Sync Option Project", created_by=self.admin, jira_connection=self.conn, sync_jira_status=True)
        self.col_todo = KanbanColumn.objects.create(project=self.project, name="To Do", position=0)
        self.col_done = KanbanColumn.objects.create(project=self.project, name="Done", position=1)
        self.js_done = JiraStatus.objects.create(name="Done", jira_status_key="DONE")
        self.mapping_done = StatusMapping.objects.create(project=self.project, app_status=self.col_done, jira_status=self.js_done, transfer_to_jira=True)
        self.card = KanbanCard.objects.create(project=self.project, column=self.col_todo, title="Sync Task", jira_key="JSO-1")
        self.client.force_login(self.admin)

    def test_move_card_with_sync_enabled_calls_transition(self):
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.transition_issue") as mock_trans:
            resp = self.client.post(
                reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": self.card.id}),
                {"column_id": self.col_done.id},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            mock_trans.assert_called_once()
            self.card.refresh_from_db()
            self.assertEqual(self.card.column_id, self.col_done.id)

    def test_move_card_with_project_sync_disabled_skips_transition(self):
        self.project.sync_jira_status = False
        self.project.save()
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.transition_issue") as mock_trans:
            resp = self.client.post(
                reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": self.card.id}),
                {"column_id": self.col_done.id},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            mock_trans.assert_not_called()
            self.assertIn("Jira statü aktarımı yapılmadı", resp.content.decode("utf-8"))
            self.card.refresh_from_db()
            self.assertEqual(self.card.column_id, self.col_done.id)

    def test_move_card_with_mapping_transfer_disabled_skips_transition(self):
        self.mapping_done.transfer_to_jira = False
        self.mapping_done.save()
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.transition_issue") as mock_trans:
            resp = self.client.post(
                reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": self.card.id}),
                {"column_id": self.col_done.id},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            mock_trans.assert_not_called()
            self.card.refresh_from_db()
            self.assertEqual(self.card.column_id, self.col_done.id)

    def test_refresh_project_does_not_override_columns_when_sync_disabled(self):
        self.project.sync_jira_status = False
        self.project.save()
        mock_issues = [{
            "id": "1001",
            "key": "JSO-1",
            "summary": "Updated Title",
            "description": "Updated Desc",
            "status_id": "99",
            "status_key": "Done",
            "assignee": None,
            "reporter": None,
            "created": "",
            "updated": "",
            "sprint": None,
            "epic_key": None,
        }]
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_issues), \
             patch("kanbanapp.views.JiraService.sync_statuses", return_value=1):
            resp = self.client.post(reverse("refresh_project", kwargs={"project_id": self.project.id}), follow=True)
            self.assertEqual(resp.status_code, 200)

        self.card.refresh_from_db()
        # Title updated
        self.assertEqual(self.card.title, "Updated Title")
        # Column MUST stay as col_todo because sync_jira_status is False!
        self.assertEqual(self.card.column_id, self.col_todo.id)


class MultiStatusMappingAndScreenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="pm_tester", password="password123")
        self.client = Client()
        self.client.force_login(self.user)
        self.conn = JiraConnection.objects.create(
            name="Test Jira", host="https://jira.example.local", username="admin", password="enc_password"
        )
        self.project = Project.objects.create(
            key="MULT", name="Multi Status Project", created_by=self.user,
            jira_connection=self.conn, sync_jira_status=True,
        )
        self.col_todo = KanbanColumn.objects.create(project=self.project, name="Yapılacak", position=0)
        self.col_dev = KanbanColumn.objects.create(project=self.project, name="Geliştirme", position=1)
        self.col_review = KanbanColumn.objects.create(project=self.project, name="Kod İnceleme", position=2)

        self.js_todo = JiraStatus.objects.create(jira_status_key="to_do", name="To Do")
        self.js_in_prog = JiraStatus.objects.create(jira_status_key="in_progress", name="In Progress")
        self.js_review = JiraStatus.objects.create(jira_status_key="review", name="In Review")

        self.card = KanbanCard.objects.create(
            project=self.project, column=self.col_todo, title="Multi Card", jira_key="MULT-1"
        )

    def test_multiple_jira_statuses_for_single_app_status_picks_primary_on_move(self):
        # Column 'Geliştirme' has 2 Jira statuses mapped: 'In Progress' (primary) and 'In Review'
        m1 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_in_prog,
            is_primary=True, transfer_to_jira=True
        )
        m2 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_review,
            is_primary=False, transfer_to_jira=True
        )

        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.transition_issue") as mock_trans:
            resp = self.client.post(
                reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": self.card.id}),
                {"column_id": self.col_dev.id},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            mock_trans.assert_called_once_with(self.project, "MULT-1", "In Progress")

    def test_fine_grained_app_statuses_preserves_card_column_on_jira_refresh(self):
        # Two app columns mapped to the same Jira status ('In Progress')
        m_dev = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_in_prog,
            is_primary=True, transfer_to_jira=True
        )
        m_rev = StatusMapping.objects.create(
            project=self.project, app_status=self.col_review, jira_status=self.js_in_prog,
            is_primary=False, transfer_to_jira=True
        )
        self.card.column = self.col_review
        self.card.save()

        mock_issues = [{
            "id": "2001",
            "key": "MULT-1",
            "summary": "Multi Card Updated",
            "description": "Desc",
            "status_id": "10",
            "status_key": "In Progress",
            "assignee": None,
            "reporter": None,
            "created": "",
            "updated": "",
            "sprint": None,
            "epic_key": None,
        }]
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_issues), \
             patch("kanbanapp.views.JiraService.sync_statuses", return_value=1):
            resp = self.client.post(reverse("refresh_project", kwargs={"project_id": self.project.id}), follow=True)
            self.assertEqual(resp.status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.column_id, self.col_review.id)

    def test_project_status_mappings_screen_get(self):
        resp = self.client.get(reverse("project_status_mappings", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jira Statü Eşleme")
        self.assertContains(resp, "Yapılacak")
        self.assertContains(resp, "Geliştirme")
        self.assertContains(resp, "Kod İnceleme")

    def test_project_status_mappings_add_mapping(self):
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {
                "action": "add_mapping",
                "column_id": self.col_todo.id,
                "jira_status_id": self.js_todo.id,
                "transfer_to_jira": "1",
                "is_primary": "1",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        mapping = StatusMapping.objects.filter(project=self.project, app_status=self.col_todo, jira_status=self.js_todo).first()
        self.assertIsNotNone(mapping)
        self.assertTrue(mapping.is_primary)
        self.assertTrue(mapping.transfer_to_jira)

    def test_project_status_mappings_set_primary(self):
        m1 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_in_prog,
            is_primary=True, transfer_to_jira=True
        )
        m2 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_review,
            is_primary=False, transfer_to_jira=True
        )

        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "set_primary", "mapping_id": m2.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        m1.refresh_from_db()
        m2.refresh_from_db()
        self.assertFalse(m1.is_primary)
        self.assertTrue(m2.is_primary)

    def test_project_status_mappings_toggle_transfer(self):
        m = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_in_prog,
            is_primary=True, transfer_to_jira=True
        )
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "toggle_transfer", "mapping_id": m.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertFalse(m.transfer_to_jira)

    def test_project_status_mappings_delete_mapping_primary_fallback(self):
        m1 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_in_prog,
            is_primary=True, transfer_to_jira=True
        )
        m2 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_dev, jira_status=self.js_review,
            is_primary=False, transfer_to_jira=True
        )

        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "delete_mapping", "mapping_id": m1.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(StatusMapping.objects.filter(id=m1.id).exists())
        m2.refresh_from_db()
        self.assertTrue(m2.is_primary)

    def test_project_status_mappings_auto_map(self):
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "auto_map"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        mapped = StatusMapping.objects.filter(project=self.project, app_status=self.col_todo, jira_status=self.js_todo).exists()
        self.assertTrue(mapped)

    def test_project_status_mappings_toggle_project_sync(self):
        self.assertTrue(self.project.sync_jira_status)
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "toggle_project_sync"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.project.refresh_from_db()
        self.assertFalse(self.project.sync_jira_status)

    def test_project_status_mappings_move_mapping(self):
        m1 = StatusMapping.objects.create(
            project=self.project, app_status=self.col_todo, jira_status=self.js_todo,
            is_primary=True, transfer_to_jira=True
        )
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "move_mapping", "mapping_id": m1.id, "target_column_id": self.col_dev.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        m1.refresh_from_db()
        self.assertEqual(m1.app_status_id, self.col_dev.id)

    def test_toggle_jira_status_visibility_for_project(self):
        # 1. Hide unmapped js_review for this project
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "toggle_jira_status_visibility", "jira_status_id": self.js_review.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.project.hidden_jira_statuses.filter(id=self.js_review.id).exists())
        self.assertContains(resp, "gizlendi")

        # 2. Toggle again to unhide
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "toggle_jira_status_visibility", "jira_status_id": self.js_review.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.project.hidden_jira_statuses.filter(id=self.js_review.id).exists())
        self.assertContains(resp, "yeniden görünür yapıldı")

    def test_toggle_jira_status_visibility_prevents_hiding_mapped_status(self):
        StatusMapping.objects.create(
            project=self.project, app_status=self.col_todo, jira_status=self.js_todo,
            is_primary=True, transfer_to_jira=True
        )
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "toggle_jira_status_visibility", "jira_status_id": self.js_todo.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Gizlemeden önce eşlemeyi kaldırmalısınız")
        self.assertFalse(self.project.hidden_jira_statuses.filter(id=self.js_todo.id).exists())

    def test_bulk_update_hidden_statuses(self):
        js_unused1 = JiraStatus.objects.create(jira_status_key="unused1", name="Unused Status 1")
        js_unused2 = JiraStatus.objects.create(jira_status_key="unused2", name="Unused Status 2")

        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {
                "action": "bulk_update_hidden_statuses",
                "hidden_status_ids": [str(js_unused1.id), str(js_unused2.id)],
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jira statü görünürlük ayarları kaydedildi")
        hidden_ids = list(self.project.hidden_jira_statuses.values_list("id", flat=True))
        self.assertIn(js_unused1.id, hidden_ids)
        self.assertIn(js_unused2.id, hidden_ids)

    def test_hidden_status_excluded_from_auto_map_and_dropdowns(self):
        from kanbanapp.forms import StatusMappingForm

        # Hide js_todo
        self.project.hidden_jira_statuses.add(self.js_todo)

        # 1. auto_map must NOT map js_todo
        resp = self.client.post(
            reverse("project_status_mappings", kwargs={"project_id": self.project.id}),
            {"action": "auto_map"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        mapped = StatusMapping.objects.filter(project=self.project, app_status=self.col_todo, jira_status=self.js_todo).exists()
        self.assertFalse(mapped)

        # 2. GET view context must exclude js_todo from available_jira_statuses
        resp = self.client.get(reverse("project_status_mappings", kwargs={"project_id": self.project.id}))
        self.assertEqual(resp.status_code, 200)
        col_data = resp.context["columns_data"][0]
        avail_ids = [js.id for js in col_data["available_jira_statuses"]]
        self.assertNotIn(self.js_todo.id, avail_ids)
        self.assertGreaterEqual(resp.context["hidden_jira_count"], 1)

        # 3. StatusMappingForm must exclude js_todo
        form = StatusMappingForm(project=self.project)
        self.assertNotIn(self.js_todo, form.fields["jira_status"].queryset)

    def test_kanban_cards_reorder_view_success(self):
        col = KanbanColumn.objects.create(project=self.project, name="Col1", status_type="custom", position=0)
        c1 = KanbanCard.objects.create(project=self.project, column=col, title="Card 1", position=0)
        c2 = KanbanCard.objects.create(project=self.project, column=col, title="Card 2", position=1)
        c3 = KanbanCard.objects.create(project=self.project, column=col, title="Card 3", position=2)

        import json
        resp = self.client.post(
            reverse("kanban_cards_reorder", kwargs={"project_id": self.project.id}),
            data=json.dumps({"column_id": col.id, "card_ids": [c3.id, c1.id, c2.id]}),
            content_type="application/json",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

        c1.refresh_from_db()
        c2.refresh_from_db()
        c3.refresh_from_db()
        self.assertEqual(c3.position, 0)
        self.assertEqual(c1.position, 1)
        self.assertEqual(c2.position, 2)

    def test_kanban_card_move_view_with_position(self):
        col1 = KanbanColumn.objects.create(project=self.project, name="Col A", status_type="custom", position=0)
        col2 = KanbanColumn.objects.create(project=self.project, name="Col B", status_type="custom", position=1)
        card = KanbanCard.objects.create(project=self.project, column=col1, title="Move Card", position=0)

        resp = self.client.post(
            reverse("kanban_card_move", kwargs={"project_id": self.project.id, "card_id": card.id}),
            {"column_id": col2.id, "position": "3", "skip_jira_sync": "1"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.column_id, col2.id)
        self.assertEqual(card.position, 3)

    def test_kanban_columns_reorder_view(self):
        col1 = KanbanColumn.objects.create(project=self.project, name="Col 1", position=0)
        col2 = KanbanColumn.objects.create(project=self.project, name="Col 2", position=1)
        col3 = KanbanColumn.objects.create(project=self.project, name="Col 3", position=2)

        import json
        resp = self.client.post(
            reverse("kanban_columns_reorder", kwargs={"project_id": self.project.id}),
            data=json.dumps({"column_ids": [col3.id, col1.id, col2.id]}),
            content_type="application/json",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

        col1.refresh_from_db()
        col2.refresh_from_db()
        col3.refresh_from_db()
        self.assertEqual(col3.position, 0)
        self.assertEqual(col1.position, 1)
        self.assertEqual(col2.position, 2)

    def test_kanban_columns_reorder_missing_params(self):
        resp = self.client.post(
            reverse("kanban_columns_reorder", kwargs={"project_id": self.project.id}),
            data={},
            content_type="application/json",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_kanban_columns_reorder_permission_denied_for_non_member(self):
        role_prog, _ = Role.objects.get_or_create(slug="proje-programcisi", defaults={"name": "Proje Programcısı", "level": Role.PROGRAMMER})
        other_user = User.objects.create_user(username="stranger", email="stranger_col@example.com", password="pass12345", role=role_prog)
        other_client = Client()
        other_client.force_login(other_user)

        import json
        resp = other_client.post(
            reverse("kanban_columns_reorder", kwargs={"project_id": self.project.id}),
            data=json.dumps({"column_ids": [self.col_todo.id]}),
            content_type="application/json",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        self.assertEqual(resp.status_code, 403)


class JqlCardImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="jql_admin", password="password123")
        self.client = Client()
        self.client.force_login(self.user)
        self.conn = JiraConnection.objects.create(
            name="JQL Jira", host="https://jira.example.local", username="admin", password="enc_password"
        )
        self.project = Project.objects.create(
            key="JQLP", name="JQL Project", created_by=self.user,
            jira_connection=self.conn, sync_jira_status=True,
        )
        self.col_todo = KanbanColumn.objects.create(project=self.project, name="Yapılacak", position=0)
        self.col_done = KanbanColumn.objects.create(project=self.project, name="Tamamlandı", position=1)

    def test_jql_search_returns_open_issues(self):
        mock_issues = [
            {"id": "501", "key": "JQLP-1", "summary": "Open Bug 1", "status_key": "Open", "assignee": "alice", "description": ""},
            {"id": "502", "key": "JQLP-2", "summary": "In Progress Feature", "status_key": "In Progress", "assignee": "bob", "description": ""},
        ]
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_issues):
            resp = self.client.get(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jql": 'project = "JQLP"'},
            )
            self.assertEqual(resp.status_code, 200)
            issues_in_context = resp.context["issues"]
            self.assertEqual(len(issues_in_context), 2)
            self.assertEqual(issues_in_context[0]["key"], "JQLP-1")
            self.assertEqual(issues_in_context[1]["key"], "JQLP-2")
            self.assertContains(resp, "Open Bug 1")
            self.assertContains(resp, "In Progress Feature")

    def test_closed_and_resolved_issues_are_strictly_filtered_out(self):
        mock_issues = [
            {"id": "601", "key": "JQLP-10", "summary": "Open Issue", "status_key": "To Do", "description": ""},
            {"id": "602", "key": "JQLP-11", "summary": "Resolved Issue", "status_key": "Resolved", "description": ""},
            {"id": "603", "key": "JQLP-12", "summary": "Closed Issue", "status_key": "Closed", "description": ""},
            {"id": "604", "key": "JQLP-13", "summary": "Done Status Issue", "status_key": "Done", "description": ""},
            {"id": "605", "key": "JQLP-14", "summary": "Status Category Done", "status_key": "Custom Status", "status_category": "done", "description": ""},
            {"id": "606", "key": "JQLP-15", "summary": "Resolution Set", "status_key": "Open", "resolution": "Fixed", "description": ""},
            {"id": "607", "key": "JQLP-16", "summary": "Kapatıldı", "status_key": "Kapatıldı", "description": ""},
            {"id": "608", "key": "JQLP-17", "summary": "Çözüldü", "status_key": "Çözüldü", "description": ""},
            {"id": "609", "key": "JQLP-18", "summary": "Ready Issue", "status_key": "Ready", "description": ""},
            {"id": "610", "key": "JQLP-19", "summary": "Ready for Deploy", "status_key": "Ready for Deploy", "description": ""},
            {"id": "611", "key": "JQLP-20", "summary": "Hazır Issue", "status_key": "Hazır", "description": ""},
        ]
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_issues):
            resp = self.client.get(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jql": 'project = "JQLP"'},
            )
            self.assertEqual(resp.status_code, 200)
            issues_in_context = resp.context["issues"]
            # Only JQLP-10 is open! All other 10 closed/resolved/ready issues MUST be excluded!
            self.assertEqual(len(issues_in_context), 1)
            self.assertEqual(issues_in_context[0]["key"], "JQLP-10")
            self.assertContains(resp, "Open Issue")
            self.assertNotContains(resp, "Resolved Issue")
            self.assertNotContains(resp, "Closed Issue")
            self.assertNotContains(resp, "Resolution Set")
            self.assertNotContains(resp, "Ready Issue")
            self.assertNotContains(resp, "Ready for Deploy")
            self.assertNotContains(resp, "Hazır Issue")

    def test_direct_import_of_closed_issue_is_rejected(self):
        closed_issue = {
            "id": "701",
            "key": "JQLP-99",
            "summary": "Should Not Import",
            "status_key": "Closed",
            "description": "",
        }
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.get_project_issue", return_value=closed_issue):
            resp = self.client.post(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jira_key": "JQLP-99"},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "kapalı veya çözülmüş durumda")
            # Card must NOT be created
            self.assertFalse(KanbanCard.objects.filter(project=self.project, jira_key="JQLP-99").exists())

    def test_direct_import_of_ready_issue_is_rejected(self):
        ready_issue = {
            "id": "702",
            "key": "JQLP-98",
            "summary": "Ready For Release",
            "status_key": "Ready for Release",
            "description": "",
        }
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.get_project_issue", return_value=ready_issue):
            resp = self.client.post(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jira_key": "JQLP-98"},
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "kapalı veya çözülmüş durumda")
            self.assertFalse(KanbanCard.objects.filter(project=self.project, jira_key="JQLP-98").exists())

    def test_build_open_issues_jql_does_not_contain_invalid_status_names(self):
        from kanbanapp.views import build_open_issues_jql, build_fallback_open_issues_jql
        query = build_open_issues_jql('assignee in ("engin.talay")', "EVDBS")
        # Ensure hardcoded status values that cause 400 are NOT in the JQL
        self.assertNotIn("status not in", query)
        self.assertNotIn("Kapatıldı", query)
        self.assertNotIn("Çözüldü", query)
        self.assertNotIn("Tamamlandı", query)
        self.assertIn("resolution is EMPTY", query)
        self.assertIn("statusCategory != Done", query)

        fallback = build_fallback_open_issues_jql('assignee in ("engin.talay")', "EVDBS")
        self.assertNotIn("status not in", fallback)
        self.assertIn("resolution is EMPTY", fallback)

    def test_import_jira_fallback_ladder(self):
        from unittest.mock import patch
        calls = []

        def mock_pull(project, jql, max_results=100):
            calls.append(jql)
            if "statusCategory" in jql:
                raise Exception("JiraError HTTP 400: statusCategory is not valid")
            if "resolution is EMPTY" in jql:
                raise Exception("JiraError HTTP 400: resolution error")
            return [{"id": "999", "key": "JQLP-RAW", "summary": "Raw Issue", "status_key": "Open"}]

        with patch("kanbanapp.views.JiraService.pull_project_issues", side_effect=mock_pull):
            resp = self.client.get(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jql": 'assignee = "test"'},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(calls), 3)
            self.assertIn("statusCategory", calls[0])
            self.assertIn("resolution is EMPTY", calls[1])
            self.assertEqual(calls[2], 'assignee = "test"')
            self.assertContains(resp, "Raw Issue")

    def test_already_imported_cards_are_cleaned_out_of_search_results(self):
        # Already created on the board
        KanbanCard.objects.create(
            project=self.project, column=self.col_todo, title="Existing Card", jira_key="JQLP-EXIST"
        )
        mock_issues = [
            {"id": "801", "key": "JQLP-EXIST", "summary": "Already Added Issue", "status_key": "Open", "description": ""},
            {"id": "802", "key": "JQLP-NEW", "summary": "Brand New Issue", "status_key": "Open", "description": ""},
        ]
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.pull_project_issues", return_value=mock_issues):
            resp = self.client.get(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {"jql": 'project = "JQLP"'},
            )
            self.assertEqual(resp.status_code, 200)
            issues_in_context = resp.context["issues"]
            # JQLP-EXIST must be cleaned out! Only JQLP-NEW is listed!
            self.assertEqual(len(issues_in_context), 1)
            self.assertEqual(issues_in_context[0]["key"], "JQLP-NEW")
            self.assertContains(resp, "Brand New Issue")
            self.assertNotContains(resp, "Already Added Issue")

    def test_batch_manual_card_addition(self):
        mock_issues_db = {
            "JQLP-B1": {"id": "901", "key": "JQLP-B1", "summary": "Batch 1", "status_key": "To Do", "description": "Desc 1"},
            "JQLP-B2": {"id": "902", "key": "JQLP-B2", "summary": "Batch 2", "status_key": "To Do", "description": "Desc 2"},
        }
        from unittest.mock import patch
        with patch("kanbanapp.views.JiraService.get_project_issue", side_effect=lambda proj, key: mock_issues_db[key]):
            resp = self.client.post(
                reverse("kanban_card_import_jira", kwargs={"project_id": self.project.id}),
                {
                    "selected_keys": ["JQLP-B1", "JQLP-B2"],
                    "difficulty_level": "3",
                    "column_id": self.col_todo.id,
                },
                follow=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "2 adet Jira işi başarıyla panoya eklendi")
            self.assertTrue(KanbanCard.objects.filter(project=self.project, jira_key="JQLP-B1").exists())
            self.assertTrue(KanbanCard.objects.filter(project=self.project, jira_key="JQLP-B2").exists())
            c1 = KanbanCard.objects.get(project=self.project, jira_key="JQLP-B1")
            self.assertEqual(c1.difficulty_level, 3)
            self.assertEqual(c1.column_id, self.col_todo.id)


@override_settings(AUTH_PASSWORD_VALIDATORS=[])
class ProjectTicketAndMessagingTests(TestCase):
    def setUp(self):
        self.admin_role = Role.objects.create(name="Admin", slug="admin", level=Role.LEVEL_ADMIN)
        self.pm_role = Role.objects.create(name="Proje Yöneticisi", slug="pm", level=Role.LEVEL_PROJECT_MANAGER)
        self.prog_role = Role.objects.create(name="Proje Programcısı", slug="prog", level=Role.LEVEL_PROGRAMMER)

        self.admin = User.objects.create_superuser(username="tadmin", password="p", email="tadmin@e.com", role=self.admin_role)
        self.reporter_user = User.objects.create_user(username="reporter1", password="p", email="rep@e.com", role=self.prog_role)
        self.dev_user = User.objects.create_user(username="dev1", password="p", email="dev@e.com", role=self.prog_role)

        self.project = Project.objects.create(key="TCK", name="Ticket Test Project", created_by=self.admin)
        from .models import ProjectMember
        ProjectMember.objects.create(project=self.project, user=self.reporter_user)
        ProjectMember.objects.create(project=self.project, user=self.dev_user)
        self.col_todo = KanbanColumn.objects.create(project=self.project, name="Yapılacak", status_type="custom", position=0)

        self.client = Client()

    def test_create_bug_and_feature_ticket(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.reporter_user)
        dummy_file = SimpleUploadedFile("screenshot.png", b"fake-png-content", content_type="image/png")

        resp = self.client.post(
            reverse("project_ticket_create", kwargs={"project_id": self.project.id}),
            {
                "project": self.project.id,
                "ticket_type": ProjectTicket.TYPE_BUG,
                "title": "Giriş sayfası 500 hatası veriyor",
                "description": "Kullanıcı hatalı şifre girince uygulama çöküyor.",
                "priority": ProjectTicket.PRIORITY_HIGH,
                "assignee": self.dev_user.id,
                "attachments": [dummy_file],
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ProjectTicket.objects.filter(project=self.project, title="Giriş sayfası 500 hatası veriyor").exists())

        ticket = ProjectTicket.objects.get(project=self.project, title="Giriş sayfası 500 hatası veriyor")
        self.assertEqual(ticket.reporter, self.reporter_user)
        self.assertEqual(ticket.assignee, self.dev_user)
        self.assertTrue(ticket.is_bug)
        self.assertEqual(ticket.ticket_code, f"TCK-T{ticket.id}")

        # Ek kontrolü
        self.assertEqual(ticket.attachments.count(), 1)
        att = ticket.attachments.first()
        self.assertTrue(att.is_image)
        self.assertEqual(att.uploaded_by, self.reporter_user)

        # İlk sistem yorumu kontrolü
        self.assertTrue(ticket.comments.filter(is_system_note=True).exists())

    def test_ticket_list_view_and_filtering(self):
        t1 = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_BUG,
            title="Kritik UI Hatası",
            reporter=self.reporter_user,
            priority=ProjectTicket.PRIORITY_URGENT,
            status=ProjectTicket.STATUS_OPEN,
        )
        t2 = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_FEATURE,
            title="Excel Dışa Aktarım İsteği",
            reporter=self.reporter_user,
            assignee=self.dev_user,
            priority=ProjectTicket.PRIORITY_MEDIUM,
            status=ProjectTicket.STATUS_RESOLVED,
        )

        self.client.force_login(self.reporter_user)

        # Genel liste
        resp = self.client.get(reverse("ticket_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kritik UI Hatası")
        self.assertContains(resp, "Excel Dışa Aktarım İsteği")

        # Tür filtresi: sadece bug
        resp_bug = self.client.get(reverse("ticket_list"), {"type": "bug"})
        self.assertContains(resp_bug, "Kritik UI Hatası")
        self.assertNotContains(resp_bug, "Excel Dışa Aktarım İsteği")

        # Durum filtresi: all_open
        resp_open = self.client.get(reverse("ticket_list"), {"status": "all_open"})
        self.assertContains(resp_open, "Kritik UI Hatası")
        self.assertNotContains(resp_open, "Excel Dışa Aktarım İsteği")

        # Bana atananlar
        self.client.force_login(self.dev_user)
        resp_me = self.client.get(reverse("ticket_list"), {"assigned": "me"})
        self.assertContains(resp_me, "Excel Dışa Aktarım İsteği")
        self.assertNotContains(resp_me, "Kritik UI Hatası")

    def test_messaging_between_reporter_and_assignee(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        ticket = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_BUG,
            title="Raporlama Donuyor",
            reporter=self.reporter_user,
            assignee=self.dev_user,
            status=ProjectTicket.STATUS_OPEN,
        )

        # İşi açan mesaj atar
        self.client.force_login(self.reporter_user)
        resp_rep = self.client.post(
            reverse("ticket_add_comment", kwargs={"ticket_id": ticket.id}),
            {"message": "Hata sadece Chrome tarayıcısında oluyor bilginize."},
            follow=True,
        )
        self.assertEqual(resp_rep.status_code, 200)

        # Geliştirici (işi yapan) cevap yazar ve ek dosya ekler
        self.client.force_login(self.dev_user)
        dummy_log = SimpleUploadedFile("log.txt", b"error stack trace", content_type="text/plain")
        resp_dev = self.client.post(
            reverse("ticket_add_comment", kwargs={"ticket_id": ticket.id}),
            {
                "message": "Logları inceledim, düzeltiyorum.",
                "attachment": dummy_log,
            },
            follow=True,
        )
        self.assertEqual(resp_dev.status_code, 200)

        comments = ticket.comments.filter(is_system_note=False).order_by("created_at")
        self.assertEqual(comments.count(), 2)

        c1 = comments[0]
        self.assertEqual(c1.author, self.reporter_user)
        self.assertTrue(c1.is_reporter)
        self.assertEqual(c1.author_badge_label, "İşi Açan")

        c2 = comments[1]
        self.assertEqual(c2.author, self.dev_user)
        self.assertTrue(c2.is_assignee)
        self.assertEqual(c2.author_badge_label, "İşi Yapan / Geliştirici")
        self.assertTrue(bool(c2.attachment))

        # Detay sayfasında görüntüleme kontrolü
        detail_resp = self.client.get(reverse("ticket_detail", kwargs={"ticket_id": ticket.id}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Hata sadece Chrome tarayıcısında oluyor")
        self.assertContains(detail_resp, "Logları inceledim, düzeltiyorum.")
        self.assertContains(detail_resp, "İşi Açan")
        self.assertContains(detail_resp, "İşi Yapan / Geliştirici")

    def test_ticket_status_update_and_resolution_notes(self):
        ticket = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_BUG,
            title="CSS Bozulması",
            reporter=self.reporter_user,
            status=ProjectTicket.STATUS_OPEN,
        )

        self.client.force_login(self.dev_user)
        resp = self.client.post(
            reverse("ticket_update_status", kwargs={"ticket_id": ticket.id}),
            {"status": ProjectTicket.STATUS_RESOLVED, "resolution_notes": "Stil dosyası güncellendi."},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, ProjectTicket.STATUS_RESOLVED)
        self.assertEqual(ticket.resolution_notes, "Stil dosyası güncellendi.")

        # Sistem yorumu kaydedildi mi?
        self.assertTrue(ticket.comments.filter(message__contains="Çözüldü").exists())

    def test_ticket_assign_and_self_assign(self):
        ticket = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_FEATURE,
            title="Dark Mode Desteği",
            reporter=self.reporter_user,
            status=ProjectTicket.STATUS_OPEN,
        )

        # Geliştirici kendini atar
        self.client.force_login(self.dev_user)
        resp = self.client.post(
            reverse("ticket_assign", kwargs={"ticket_id": ticket.id}),
            {"assignee": self.dev_user.id},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.dev_user)
        self.assertTrue(ticket.comments.filter(message__contains=self.dev_user.username).exists())

        # Atamayı kaldır
        resp_clear = self.client.post(
            reverse("ticket_assign", kwargs={"ticket_id": ticket.id}),
            {"assignee": ""},
            follow=True,
        )
        self.assertEqual(resp_clear.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assignee)

    def test_ticket_convert_to_kanban_card(self):
        ticket = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_FEATURE,
            title="Otomatik Mail Bildirimi",
            description="İş bittiğinde mail atılsın.",
            reporter=self.reporter_user,
            assignee=self.dev_user,
            status=ProjectTicket.STATUS_OPEN,
        )

        self.client.force_login(self.dev_user)
        resp = self.client.post(
            reverse("ticket_create_card", kwargs={"ticket_id": ticket.id}),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.card)
        self.assertEqual(ticket.status, ProjectTicket.STATUS_IN_PROGRESS)
        self.assertIn("Otomatik Mail Bildirimi", ticket.card.title)
        self.assertEqual(ticket.card.assignee, self.dev_user)
        self.assertEqual(ticket.card.column, self.col_todo)

        # Detay sayfasında Kanban kartı bilgisi görüntülenmeli
        detail_resp = self.client.get(reverse("ticket_detail", kwargs={"ticket_id": ticket.id}))
        self.assertContains(detail_resp, "Pano Üzerinde Görüntüle")
        self.assertContains(detail_resp, self.col_todo.name)

    def test_ticket_attachment_upload_and_delete(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        ticket = ProjectTicket.objects.create(
            project=self.project,
            ticket_type=ProjectTicket.TYPE_BUG,
            title="Ek Yükleme Testi",
            reporter=self.reporter_user,
        )

        self.client.force_login(self.reporter_user)
        dummy_file = SimpleUploadedFile("extra_doc.pdf", b"pdf-content", content_type="application/pdf")

        # Yeni ek yükle
        resp_upload = self.client.post(
            reverse("ticket_add_attachment", kwargs={"ticket_id": ticket.id}),
            {"file": dummy_file},
            follow=True,
        )
        self.assertEqual(resp_upload.status_code, 200)
        self.assertEqual(ticket.attachments.count(), 1)
        att = ticket.attachments.first()

        # Eki sil
        resp_del = self.client.post(
            reverse("ticket_delete_attachment", kwargs={"ticket_id": ticket.id, "attachment_id": att.id}),
            follow=True,
        )
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(ticket.attachments.count(), 0)

    def test_ticket_paste_elements_and_image_handling(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.reporter_user)

        # 1. Talep oluşturma sayfasında paste dropzone ve preview alanlarının varlığı
        create_resp = self.client.get(reverse("project_ticket_create", kwargs={"project_id": self.project.id}))
        self.assertEqual(create_resp.status_code, 200)
        self.assertContains(create_resp, "paste-dropzone")
        self.assertContains(create_resp, "Ctrl+V")
        self.assertContains(create_resp, "pasted-images-preview")

        # 2. Panodan yapıştırılan isimlendirilmiş bir ekran görüntüsünü ticket oluştururken yükleme
        pasted_img = SimpleUploadedFile("ekran_goruntusu_20261007_134500_1.png", b"\x89PNG\r\n\x1a\nfakeimagecontent", content_type="image/png")
        post_resp = self.client.post(
            reverse("project_ticket_create", kwargs={"project_id": self.project.id}),
            {
                "project": self.project.id,
                "ticket_type": ProjectTicket.TYPE_BUG,
                "title": "Paste Test Talebi",
                "description": "Panodan yapıştırma testi açıklaması",
                "priority": ProjectTicket.PRIORITY_MEDIUM,
                "attachments": [pasted_img],
            },
            follow=True,
        )
        self.assertEqual(post_resp.status_code, 200)
        ticket = ProjectTicket.objects.get(project=self.project, title="Paste Test Talebi")
        self.assertEqual(ticket.attachments.count(), 1)
        att = ticket.attachments.first()
        self.assertTrue(att.is_image)
        self.assertIn("ekran_goruntusu", att.filename)

        # 3. Detay sayfasında mesajlaşma paste önizleme ve detay paste dropzone varlığı
        detail_resp = self.client.get(reverse("ticket_detail", kwargs={"ticket_id": ticket.id}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "detail-paste-dropzone")
        self.assertContains(detail_resp, "chat-attachment-preview")
        self.assertContains(detail_resp, "Ctrl+V")

        # 4. Mesaj kutusuna yapıştırılan ekran görüntüsünün yüklenmesi
        pasted_chat_img = SimpleUploadedFile("ekran_goruntusu_chat_1.png", b"\x89PNG\r\n\x1a\nchatimagecontent", content_type="image/png")
        comment_resp = self.client.post(
            reverse("ticket_add_comment", kwargs={"ticket_id": ticket.id}),
            {
                "message": "İşte hatanın ekran görüntüsü:",
                "attachment": pasted_chat_img,
            },
            follow=True,
        )
        self.assertEqual(comment_resp.status_code, 200)
        comment = ticket.comments.filter(is_system_note=False).last()
        self.assertEqual(comment.message, "İşte hatanın ekran görüntüsü:")
        self.assertTrue(comment.attachment_is_image)
        self.assertIn("ekran_goruntusu_chat_1", comment.attachment.name)













