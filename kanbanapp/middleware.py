from functools import wraps

from django.contrib.auth.decorators import login_required
from django.utils.deprecation import MiddlewareMixin


def role_level(user):
    """Return the numeric role level for a user (1 = admin = most power, 5 = viewer)."""
    if not user or not getattr(user, "is_authenticated", False):
        return 99
    if getattr(user, "is_superuser", False):
        return 1
    role = getattr(user, "role", None)
    if role is not None:
        return getattr(role, "level", 1)
    return 1


def role_required(max_level):
    """Decorator: require the logged-in user to have role level <= max_level (1=admin, 5=viewer)."""

    def _decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if role_level(request.user) > max_level:
                return _forbidden(request)
            return view(request, *args, **kwargs)

        wrapped.max_role_level = max_level
        return wrapped

    return _decorator


def _forbidden(request):
    from django.http import HttpResponse

    return HttpResponse(
        "<h1>403</h1><p>Bu işlem için yetkiniz yok.</p>",
        status=403,
        content_type="text/html",
    )


class RoleLevelMiddleware(MiddlewareMixin):
    """Expose ``role_level`` to every request (used by templates/views)."""

    def process_request(self, request):
        request.role_level = role_level(request.user)
