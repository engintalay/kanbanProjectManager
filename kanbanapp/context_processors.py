from django.utils.functional import SimpleLazyObject


def request_user(request):
    """Expose the current user and its role level to templates.

    Safe for anonymous users: an unauthenticated user gets ``role_level``
    of ``None`` so ``{% if role_level >= 1 %}`` renders as False.
    """
    user = request.user
    role = getattr(user, "role", None)
    level = getattr(role, "level", None) if role is not None else None
    return {
        "current_user": SimpleLazyObject(lambda r: r.user),
        "role_level": level,
        "is_admin": user.is_authenticated and level == 1,
    }
