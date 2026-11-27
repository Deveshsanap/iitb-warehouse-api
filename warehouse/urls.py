"""API URL routes for the warehouse app."""
from django.urls import path

from .views import (
    AdminUserDetailView,
    AdminUsersView,
    DashboardView,
    LoadView,
    MapView,
    ShuttleView,
    UnloadView,
    login,
)

urlpatterns = [
    path("auth/login/", login, name="login"),
    path("map/", MapView.as_view(), name="map"),
    path("load/", LoadView.as_view(), name="load"),
    path("unload/", UnloadView.as_view(), name="unload"),
    path("shuttle/", ShuttleView.as_view(), name="shuttle"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("admin/users/", AdminUsersView.as_view(), name="admin-users"),
    path("admin/users/<int:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
]
