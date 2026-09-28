from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("", views.dashboard_view, name="dashboard"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("projects/", views.project_list_view, name="projects"),
    path("projects/create/", views.project_create_view, name="project_create"),
    path("projects/<int:project_id>/edit/", views.project_edit_view, name="project_edit"),
    path("projects/<int:project_id>/delete/", views.project_delete_view, name="project_delete"),
]
