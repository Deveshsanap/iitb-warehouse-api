"""Role helpers and DRF permission classes.

Roles (stored on Profile.role): admin, auditor, technician.
- Any authenticated user: map + shuttle (read).
- Technician + admin: load / unload.
- Auditor + admin: dashboard.
- Admin only: user CRUD.
- Auditor is read-only everywhere (no write endpoint grants auditor).
"""
from rest_framework.permissions import BasePermission

from .models import Profile


def get_role(user):
    """Return the user's role string, or None for anonymous / no profile."""
    if not user or not user.is_authenticated:
        return None
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    return profile.role


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) == Profile.ROLE_ADMIN


class IsTechnicianOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) in (
            Profile.ROLE_TECHNICIAN,
            Profile.ROLE_ADMIN,
        )


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return get_role(request.user) in (
            Profile.ROLE_AUDITOR,
            Profile.ROLE_ADMIN,
        )
