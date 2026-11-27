"""URL configuration for the Warehouse Management System API."""
from django.contrib import admin
from django.urls import include, path

from warehouse.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/", include("warehouse.urls")),
]
