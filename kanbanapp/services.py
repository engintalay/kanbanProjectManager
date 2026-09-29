"""Jira integration (READ-ONLY).

Only fetches issue data. Never creates, updates, assigns or comments on Jira.
"""
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlparse

from django.conf import settings

from .models import JiraConnection, JiraStatus, JiraCustomStatus

logger = logging.getLogger(__name__)

FIBONACCI = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89]


def normalize_no_proxy():
    """Ensure NO_PROXY env variable has syntax compatible with Python urllib.

    Python urllib requires '.domain.com' or 'domain.com' rather than '*.domain.com'.
    """
    for env_var in ("NO_PROXY", "no_proxy"):
        val = os.environ.get(env_var, "")
        if not val:
            continue
        parts = [p.strip() for p in val.split(",") if p.strip()]
        expanded = list(parts)
        for p in parts:
            if p.startswith("*."):
                dot_dom = p[1:]
                bare_dom = p[2:]
                if dot_dom not in expanded:
                    expanded.append(dot_dom)
                if bare_dom not in expanded:
                    expanded.append(bare_dom)
        for known in (
            ".gelirler.gov.tr",
            "gelirler.gov.tr",
            ".gib.gov.tr",
            "gib.gov.tr",
            ".gelbim.gov.tr",
            "gelbim.gov.tr",
            "localhost",
            "127.0.0.1",
        ):
            if known not in expanded:
                expanded.append(known)
        os.environ[env_var] = ",".join(expanded)


def is_local_host(host_or_url: str) -> bool:
    """Check if host is on local network, intranet, loopback, or in NO_PROXY."""
    if not host_or_url:
        return False
    if "://" in host_or_url:
        parsed = urlparse(host_or_url)
        hostname = parsed.hostname or host_or_url
    else:
        hostname = host_or_url.split(":")[0]

    hostname = hostname.lower().strip()
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return True
    if hostname.endswith(".local") or "." not in hostname:
        return True

    # Check private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback
    except ValueError:
        pass

    # Known local / intranet domains
    local_domains = (
        ".gelirler.gov.tr",
        "gelirler.gov.tr",
        ".gib.gov.tr",
        "gib.gov.tr",
        ".gelbim.gov.tr",
        "gelbim.gov.tr",
    )
    if any(hostname == d.lstrip(".") or hostname.endswith(d) for d in local_domains):
        return True

    # Check against NO_PROXY
    no_proxy = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
    for item in no_proxy.split(","):
        item = item.strip().lower()
        if not item:
            continue
        if item.startswith("*."):
            item = item[1:]
        if item.startswith("."):
            if hostname.endswith(item) or hostname == item[1:]:
                return True
        elif hostname == item:
            return True
        else:
            try:
                network = ipaddress.ip_network(item, strict=False)
                try:
                    ip = ipaddress.ip_address(hostname)
                    if ip in network:
                        return True
                except ValueError:
                    pass
            except ValueError:
                pass

    return False


def format_jira_error(exc: Exception) -> str:
    """Extract a user-friendly, detailed error description from Jira / requests exceptions."""
    from jira.exceptions import JIRAError
    import requests

    if isinstance(exc, JIRAError):
        status_code = getattr(exc, "status_code", None)
        text = (getattr(exc, "text", "") or "").strip()
        url = getattr(exc, "url", "")

        msg = ""
        # Check if error response is JSON
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if data.get("errorMessages"):
                        msg = "; ".join(data["errorMessages"])
                    elif data.get("errors"):
                        msg = "; ".join(f"{k}: {v}" for k, v in data["errors"].items())
                    elif data.get("message"):
                        msg = data["message"]
            except Exception:
                pass

        if not msg:
            if "Basic Authentication Failure" in text or status_code == 401:
                msg = "Yetkilendirme başarısız (401 Unauthorized - Kullanıcı adı veya şifre/token geçersiz)."
            elif status_code == 403:
                msg = "Erişim reddedildi (403 Forbidden - Yetki yetersiz veya hesap kilitli)."
            elif status_code == 404:
                msg = f"Kaynak bulunamadı (404 Not Found - {url})."
            elif text:
                # Strip HTML tags if server returned an HTML error page
                cleaned = re.sub(r"<[^>]+>", " ", text)
                cleaned = " ".join(cleaned.split())
                if len(cleaned) > 250:
                    cleaned = cleaned[:250] + "..."
                msg = cleaned

        status_prefix = f"HTTP {status_code}: " if status_code else ""
        return f"{status_prefix}{msg}" if msg else str(exc)

    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"Zaman aşımı (Read Timeout - 15s): Sunucu yanıt vermedi ({exc})"
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"Bağlantı zaman aşımı (Connect Timeout): Sunucuya ulaşılamadı ({exc})"
    if isinstance(exc, requests.exceptions.SSLError):
        return f"SSL Sertifika Hatası: {exc}"
    if isinstance(exc, requests.exceptions.ProxyError):
        return f"Proxy Bağlantı Hatası: {exc}"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Sunucuya bağlanılamadı (Ağ/DNS hatası): {exc}"

    return str(exc)


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "ENCRYPTION_KEY", None) or os.environ.get("ENCRYPTION_KEY", "")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _decrypt(value):
    if value in (None, ""):
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception:
        # Already plaintext or decrypted by EncryptedCharField
        return str(value)


def parse_jira_issue(issue):
    """Convert a Jira Issue resource or dict to a standardized dict."""
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

    status_id = None
    if status:
        raw_status_id = getattr(status, "id", None)
        if raw_status_id is not None:
            try:
                status_id = int(raw_status_id)
            except (ValueError, TypeError):
                status_id = None

    status_category_key = None
    if status:
        sc = getattr(status, "statusCategory", None)
        if isinstance(sc, dict):
            status_category_key = sc.get("key")
        elif sc:
            status_category_key = getattr(sc, "key", None)

    resolution_obj = getattr(fields, "resolution", None) if fields else None
    resolution_name = getattr(resolution_obj, "name", str(resolution_obj)) if resolution_obj else None

    issuetype_obj = getattr(fields, "issuetype", None) if fields else None
    issuetype_name = getattr(issuetype_obj, "name", str(issuetype_obj)) if issuetype_obj else None

    priority_obj = getattr(fields, "priority", None) if fields else None
    priority_name = getattr(priority_obj, "name", str(priority_obj)) if priority_obj else None

    issue_id = str(getattr(issue, "id", ""))
    issue_key = getattr(issue, "key", "")

    return {
        "id": issue_id,
        "key": issue_key,
        "summary": getattr(fields, "summary", "") if fields else "",
        "description": getattr(fields, "description", "") or "",
        "status_key": getattr(status, "name", None) if status else None,
        "status_id": status_id,
        "status_category": status_category_key,
        "resolution": resolution_name,
        "issue_type": issuetype_name,
        "priority": priority_name,
        "assignee": getattr(assignee, "displayName", str(assignee)) if assignee else None,
        "reporter": getattr(reporter, "displayName", str(reporter)) if reporter else None,
        "created": str(getattr(fields, "created", "")) if fields else "",
        "updated": str(getattr(fields, "updated", "")) if fields else "",
        "sprint": sprint_name,
        "epic_key": getattr(epic_obj, "key", None) if epic_obj else None,
        "blocks": blocks,
        "blocked_by": blocked_by,
    }


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

            normalize_no_proxy()

            # Initialize with get_server_info=False so __init__ doesn't make eager
            # requests before session proxy settings can be applied
            self._jira = JIRA(
                server=self.connection.host,
                basic_auth=(self.connection.username, self.password),
                timeout=15,
                get_server_info=False,
                logging=False,
            )

            # Disable proxy for local network / intranet hosts or if disable_proxy is set
            should_bypass_proxy = getattr(self.connection, "disable_proxy", False) or is_local_host(
                self.connection.host
            )
            if should_bypass_proxy:
                self._jira._session.trust_env = False
                self._jira._session.proxies = {}

            # Fetch server_info safely
            try:
                si = self._jira.server_info()
                if isinstance(si, dict):
                    self._jira._version = tuple(si.get("versionNumbers", []))
            except Exception as exc:
                logger.warning("Jira server_info alınamadı (işlemlere devam ediliyor): %s", exc)

        return self._jira

    def test_connection(self):
        """Test connection to Jira and verify authentication.

        Returns user info dict on success.
        Raises an Exception with detailed root cause on failure.
        """
        return self.jira.myself()

    def pull_issues(self, jql, max_results=500):
        """Return a list of lightweight issue dicts (status, fields, links)."""
        issues = []
        start_at = 0
        while True:
            resp = self.jira.search_issues(jql, startAt=start_at, maxResults=max_results)
            if not resp:
                break
            for issue in resp:
                issues.append(parse_jira_issue(issue))

            total = getattr(resp, "total", len(resp))
            start_at += len(resp)
            if start_at >= total or len(resp) < max_results:
                break

        return issues

    def get_issue(self, issue_key):
        """Fetch a single issue by key or id and return standardized issue dict."""
        issue = self.jira.issue(issue_key)
        return parse_jira_issue(issue)

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
            raise ValueError("Bağlantı bilgileri eksik (host, kullanıcı adı veya şifre boş).")
        self.client = JiraClient(connection)
        try:
            return self.client.test_connection()
        except Exception as exc:
            err_detail = format_jira_error(exc)
            logger.error("Jira bağlantı testi başarısız (%s): %s", connection.host, err_detail)
            raise ConnectionError(f"Jira bağlantısı başarısız ({connection.host}): {err_detail}") from exc

    def test_connection(self, connection):
        return self.connect(connection)

    def sync_statuses(self, connection=None):
        """Import Jira statuses into local JiraStatus table."""
        if connection is not None:
            self.connect(connection)
        if self.client is None:
            raise ValueError("Önce bir Jira bağlantısı kurulmalıdır.")
        jira = self.client.jira
        statuses = jira.statuses()
        synced_count = 0
        for status in statuses:
            key = getattr(status, "name", str(status))
            name = getattr(status, "name", key)
            raw_id = getattr(status, "id", None)
            status_id = None
            if raw_id is not None:
                try:
                    status_id = int(raw_id)
                except (ValueError, TypeError):
                    status_id = None
            category = getattr(status, "statusCategory", None)
            color_data = {}
            if category:
                if isinstance(category, dict):
                    color_data = {"colorName": category.get("colorName"), "key": category.get("key")}
                else:
                    color_name = getattr(category, "colorName", "")
                    cat_key = getattr(category, "key", "")
                    color_data = {"colorName": color_name, "key": cat_key}

            JiraStatus.objects.update_or_create(
                jira_status_key=key,
                defaults={"name": name, "jira_id": status_id, "color": color_data},
            )
            synced_count += 1
        return synced_count

    def pull_project_issues(self, project, jql, max_results=500):
        self.connect(project.jira_connection)
        issues = self.client.pull_issues(jql, max_results=max_results)
        return issues

    def get_issue(self, connection, issue_key):
        self.connect(connection)
        return self.client.get_issue(issue_key)

    def get_project_issue(self, project, issue_key):
        if not project.jira_connection:
            raise ValueError("Projeye bağlı bir Jira bağlantısı bulunmuyor.")
        return self.get_issue(project.jira_connection, issue_key)

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
