from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import override_settings
from django.test.runner import TestCase
from django.urls import reverse

from .models import JiraIssue, JiraStatus, KanbanCard, KanbanColumn, Project, Role, StatusMapping

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

    def test_column_and_card_crud_flow(self):
        col_resp = self.client.post(
            reverse("kanban_column_create", kwargs={"project_id": self.project.id}),
            {"name": "Backlog", "status_type": "custom", "position": 0},
        )
        self.assertEqual(col_resp.status_code, 302)
        col = KanbanColumn.objects.get(name="Backlog")

        self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": col.id, "title": "Task One", "description": "desc", "is_extra": True},
        )
        self.assertEqual(KanbanCard.objects.count(), 1)

        self.client.post(
            reverse("kanban_card_edit", kwargs={"project_id": self.project.id, "card_id": 1}),
            {"column": col.id, "title": "Task One Edited", "description": "d", "is_extra": True},
        )
        self.assertEqual(KanbanCard.objects.first().title, "Task One Edited")

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

        card_resp = self.client.post(
            reverse("kanban_card_create", kwargs={"project_id": self.project.id}),
            {"column": self.col.id, "title": "Prog Task", "description": "desc", "is_extra": True},
        )
        self.assertEqual(card_resp.status_code, 302)
        self.assertEqual(KanbanCard.objects.filter(title="Prog Task").count(), 1)

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

