from django.utils.functional import SimpleLazyObject
from .middleware import role_level


def request_user(request):
    """Expose the current user, role level, permissions, and active theme to templates."""
    user = request.user
    if getattr(user, "is_authenticated", False):
        lvl = role_level(user)
    else:
        lvl = None

    active_theme = None
    available_themes = []
    jira_has_default = False
    jira_has_connections = False
    try:
        from .models import JiraConnection, Theme
        if getattr(user, "is_authenticated", False):
            conns = JiraConnection.objects.filter(created_by=user)
            jira_has_connections = conns.exists()
            jira_has_default = conns.filter(is_default=True).exists()
        theme_id = request.session.get("active_theme_id")
        if theme_id:
            active_theme = Theme.objects.filter(id=theme_id, is_active=True).first()

        if not active_theme and getattr(user, "is_authenticated", False) and getattr(user, "theme_id", None):
            active_theme = user.theme if (user.theme and user.theme.is_active) else None

        if not active_theme:
            active_theme = Theme.objects.filter(is_default=True, is_active=True).first()
            if not active_theme:
                active_theme = Theme.objects.filter(is_active=True).first()

        available_themes = list(Theme.objects.filter(is_active=True).order_by("-is_default", "name"))
    except Exception:
        pass

    return {
        "current_user": SimpleLazyObject(lambda: request.user),
        "role_level": lvl,
        "is_admin": lvl == 1,
        "can_manage_jira": lvl is not None and lvl <= 2,
        "active_theme": active_theme,
        "available_themes": available_themes,
        "jira_has_default": jira_has_default,
        "jira_has_connections": jira_has_connections,
    }
