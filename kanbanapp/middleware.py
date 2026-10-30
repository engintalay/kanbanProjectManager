from functools import wraps
import logging

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


notfound_logger = logging.getLogger("kanbanapp.notfound")


class NotFoundLoggingMiddleware(MiddlewareMixin):
    """404 alan isteklerin kaynağını kayıt altına alır.

    Terminalde sadece ``"GET /v1/models" 404`` görünmek yerine kimin,
    hangi User-Agent ve referrer ile istediğini de görürsün:
    konsola yazar ve ``logs/notfound.log`` dosyasına yazar.
    """

    def process_response(self, request, response):
        if response.status_code != 404:
            return response

        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        client_ip = forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "-")
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            user = request.user.username
        else:
            user = "anon"

        notfound_logger.warning(
            "%s %s user=%s ip=%s ua=%s referer=%s",
            request.method,
            request.get_full_path(),
            user,
            client_ip or "-",
            request.META.get("HTTP_USER_AGENT", "-"),
            request.META.get("HTTP_REFERER", "-"),
        )
        return response
