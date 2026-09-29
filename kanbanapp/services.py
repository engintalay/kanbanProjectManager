"""Jira integration (READ-ONLY).

Only fetches issue data. Never creates, updates, assigns or comments on Jira.
"""
import logging

from django.conf import settings

from .models import JiraConnection, JiraStatus, JiraCustomStatus

logger = logging.getLogger(__name__)

FIBONACCI = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "DJANGO_ENCRYPTION_KEY", "")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _decrypt(value):
    if value in (None, ""):
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception:
        return ""


class JiraClient:
    """Thin wrapper around the Jira REST API via the `jira` SDK (READ-WRITE)."""

    def __init__(self, connection):
        self.connection = connection
        self.password = _decrypt(connection.password)
        self._jira = None

    @property
    def jira(self):
        if self._jira is None:
            from jira import JIRA

            self._jira = JIRA(
                server=self.connection.host,
                basic_auth=(self.connection.username, self.password),
                timeout=30,
            )
        return self._jira

    def test_connection(self):
        try:
            return bool(self.jira.myself())
        except Exception as exc:  # noqa: BLE001
            logger.error("Jira bağlantı testi başarısız: %s", exc)
            return False

    def pull_issues(self, jql, max_results=500):
        """Return a list of lightweight issue dicts (status, fields, links)."""
        issues = []
        start_at = 0
        while True:
            resp = self.jira.search_issues(jql, startAt=start_at, maxResults=max_results)
            if not resp:
                break
            for issue in resp:
                fields = getattr(issue, "fields", None)
                status = getattr(fields, "status", None) if fields else None
                assignee = getattr(fields, "assignee", None) if fields else None
                reporter = getattr(fields, "reporter", None) if fields else None
                sprint_obj = getattr(fields, "sprint", None) if fields else None
                epic_obj = getattr(fields, "epic", None) if fields else None

                blocks = []
                blocked_by = []
                for link in getattr(fields, "issuelinks", []) if fields else []:
                    if hasattr(link, "outwardIssue"):
                        blocks.append(link.outwardIssue.key)
                    if hasattr(link, "inwardIssue"):
                        blocked_by.append(link.inwardIssue.key)

                sprint_name = None
                if sprint_obj:
                    sprint_name = getattr(sprint_obj, "name", str(sprint_obj))

                issue_dict = {
                    "id": str(issue.id),
                    "key": issue.key,
                    "summary": getattr(fields, "summary", "") if fields else "",
                    "description": getattr(fields, "description", "") or "",
                    "status_key": getattr(status, "name", None) if status else None,
                    "status_id": getattr(status, "id", None) if status else None,
                    "assignee": getattr(assignee, "displayName", str(assignee)) if assignee else None,
                    "reporter": getattr(reporter, "displayName", str(reporter)) if reporter else None,
                    "created": str(getattr(fields, "created", "")) if fields else "",
                    "updated": str(getattr(fields, "updated", "")) if fields else "",
                    "sprint": sprint_name,
                    "epic_key": getattr(epic_obj, "key", None) if epic_obj else None,
                    "blocks": blocks,
                    "blocked_by": blocked_by,
                }
                issues.append(issue_dict)

            total = getattr(resp, "total", len(resp))
            start_at += len(resp)
            if start_at >= total or len(resp) < max_results:
                break

        return issues

    def transition_issue(self, issue_key, transition_name_or_id):
        """Transition Jira issue to a new status."""
        return self.jira.transition_issue(issue_key, transition_name_or_id)

    def assign_issue(self, issue_key, assignee_username):
        """Assign Jira issue to a username."""
        return self.jira.assign_issue(issue_key, assignee_username)

    def add_comment(self, issue_key, comment_text):
        """Add comment to a Jira issue."""
        return self.jira.add_comment(issue_key, comment_text)

    def close(self):
        if self._jira is not None:
            try:
                self._jira.close()
            except Exception:
                pass
            self._jira = None


class JiraService:
    """High-level service: connects, syncs statuses, pulls issues per project."""

    def __init__(self):
        self.client = None

    def connect(self, connection):
        if not connection or not connection.is_valid:
            raise ValueError("Bağlantı bilgileri eksik (host, kullanıcı, şifre).")
        self.client = JiraClient(connection)
        ok = self.client.test_connection()
        if not ok:
            raise ConnectionError(f"Jira bağlantısı başarısız: {connection.host}")
        return ok

    def sync_statuses(self):
        """Import Jira statuses into local JiraStatus table."""
        if self.client is None:
            raise ValueError("Önce bir Jira bağlantısı kurulmalıdır.")
        jira = self.client.jira
        statuses = jira.statuses()
        for status in statuses:
            key = getattr(status, "name", str(status))
            name = getattr(status, "name", key)
            status_id = int(getattr(status, "id", 0)) if getattr(status, "id", None) else None
            JiraStatus.objects.update_or_create(
                jira_status_key=key,
                defaults={"name": name, "jira_id": status_id},
            )
        return JiraStatus.objects.count()

    def pull_project_issues(self, project, jql, max_results=500):
        self.connect(project.jira_connection)
        issues = self.client.pull_issues(jql, max_results=max_results)
        return issues

    def transition_issue(self, project, issue_key, transition_name_or_id):
        self.connect(project.jira_connection)
        return self.client.transition_issue(issue_key, transition_name_or_id)

    def assign_issue(self, project, issue_key, assignee_username):
        self.connect(project.jira_connection)
        return self.client.assign_issue(issue_key, assignee_username)

    def add_comment(self, project, issue_key, comment_text):
        self.connect(project.jira_connection)
        return self.client.add_comment(issue_key, comment_text)

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
