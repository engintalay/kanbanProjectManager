from django.contrib.auth.decorators import login_required


@login_required
def request_user(request):
    """Expose the current user and its role level to templates."""
    return {
        "current_user": request.user,
        "role_level": _role_level(request.user),
        "is_admin": _role_level(request.user) >= 1,
    }


def _role_level(user):
    role = getattr(user, "role", None)
    if role is not None:
        return getattr(role, "level", 1)
    return 1
