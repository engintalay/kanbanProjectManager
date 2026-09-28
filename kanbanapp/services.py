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
    """Thin READ-ONLY wrapper around the Jira REST API via the `jira` SDK."""

    def __init__(self, connection):
        self.connection = connection
        self.password = _decrypt(connection.password)
        self._jira = None

    @property
    def jira(self):
        if self._jira is None:
            from jira import Jira

            self._jira = Jira(
                server=self.connection.host,
                basic_auth=(self.connection.username, self.password),
                timeout=30,
            )
        return self._jira

    def test_connection(self):
        try:
            return bool(self.jira.myself)
        except Exception as exc:  # noqa: BLE001
            logger.error("Jira bağlantı testi başarısız: %s", exc)
            return False

    def pull_issues(self, jql, max_results=500):
        """Return a list of lightweight issue dicts (status, fields, links)."""
        issues = []
        start_at = 0
        while True:
            resp = self.jira.search_issues(jql, startAt=start_at, maxResults=max_results)
            if not resp.isLast:
                start_at += max_results
                continue
            break
        for issue in resp:
            fields = issue.fields
            issue_dict = {
                "id": str(issue.id),
                "key": issue.key,
                "summary": issue.summary,
                "description": issue.description or "",
                "status_key": fields.status.name if fields and fields.status else None,
                "status_id": fields.status.id if fields and fields.status else None,
                "assignee": fields.assignee.displayName if fields and fields.assignee else None,
                "reporter": fields.reporter.displayName if fields and fields.reporter else None,
                "created": str(fields.created),
                "updated": str(fields.updated),
                "sprint": fields.sprint.name if fields and fields.sprint else None,
                "epic_key": fields.epic.key if fields and fields.epic else None,
                "blocks": [b.key for b in fields.blocks] if fields and fields.blocks else [],
                "blocked_by": [b.key for b in fields.blockedBy] if fields and fields.blockedBy else [],
            }
            issues.append(issue_dict)
        return issues

    def close(self):
        if self._jira is not None:
            self._jira.logout()


class JiraService:
    """High-level service: connects, syncs statuses, pulls issues per project."""

    def __init__(self):
        self.client = None

    def connect(self, connection):
        if not connection.is_valid:
            raise ValueError("Bağlantı bilgileri eksik (host, kullanıcı, şifre).")
        ok = connection.jira.test_connection()
        if not ok:
            raise ConnectionError(f"Jira bağlantısı başarısız: {connection.host}")
        return ok

    def sync_statuses(self):
        """Import Jira statuses (READ-ONLY) into local JiraStatus table."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        jira = self.client.jira
        statuses = []
        resp = jira.statuses()
        while True:
            issues = resp.issues()
            if issues:
                statuses.extend(issues)
            if not resp.isLast:
                resp = jira.statuses(startAt=resp.maxResults)
            else:
                break
        for status in statuses:
            key = status.name if hasattr(status, "name") else str(status)
            name = getattr(status, "name", key)
            JiraStatus.objects.update_or_create(
                jira_status_key=key,
                defaults={"name": name, "jira_id": int(getattr(status, "id", 0))},
            )
        return JiraStatus.objects.count()

    def pull_project_issues(self, project, jql, max_results=500):
        self.connect(project.jira_connection)
        issues = self.client.pull_issues(jql, max_results=max_results)
        return issues

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
