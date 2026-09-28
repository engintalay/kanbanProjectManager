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
    path("jira/", views.jira_connections, name="jira_connections"),
    path("jira/create/", views.jira_connection_create, name="jira_connection_create"),
    path("jira/<int:connection_id>/edit/", views.jira_connection_edit, name="jira_connection_edit"),
    path("jira/<int:connection_id>/delete/", views.jira_connection_delete, name="jira_connection_delete"),
    path("jira/<int:connection_id>/test/", views.jira_test_connection, name="jira_test_connection"),
    path("projects/<int:project_id>/refresh/", views.refresh_project, name="refresh_project"),
]
