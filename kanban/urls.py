from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.views import serve as static_serve
from django.urls import include, path, re_path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("kanbanapp.urls")),
    re_path(r"^static/(?P<path>.*)$", static_serve, kwargs={"insecure": True}, name="static"),
]
