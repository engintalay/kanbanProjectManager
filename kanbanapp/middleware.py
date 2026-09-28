from functools import wraps

from django.contrib.auth.decorators import login_required
from django.utils.deprecation import MiddlewareMixin


def role_level(user):
    """Return the numeric role level for a user (higher = more power)."""
    role = getattr(user, "role", None)
    if role is not None:
        return getattr(role, "level", 1)
    return 1  # default: admin


@login_required
def role_required(level):
    """Decorator: require the logged-in user to have role level >= ``level``."""

    @wraps(view=role_required)
    def _decorator(view):
        @login_required
        def wrapped(request, *args, **kwargs):
            if role_level(request.user) < level:
                return _forbidden(request)
            return view(request, *args, **kwargs)

        wrapped.role_level = level
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
