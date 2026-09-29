from django.utils.functional import SimpleLazyObject
from .middleware import role_level


def request_user(request):
    """Expose the current user, role level, and permissions to templates."""
    user = request.user
    if getattr(user, "is_authenticated", False):
        lvl = role_level(user)
    else:
        lvl = None

    return {
        "current_user": SimpleLazyObject(lambda: request.user),
        "role_level": lvl,
        "is_admin": lvl == 1,
        "can_manage_jira": lvl is not None and lvl <= 2,
    }
