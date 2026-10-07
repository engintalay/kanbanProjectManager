from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.views import serve as static_serve
from django.urls import include, path, re_path
from django.views.static import serve as media_serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("kanbanapp.urls")),
    re_path(r"^static/(?P<path>.*)$", static_serve, kwargs={"insecure": True}, name="static"),
    re_path(r"^media/(?P<path>.*)$", media_serve, kwargs={"document_root": settings.MEDIA_ROOT}, name="media"),
]
