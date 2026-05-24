from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Доступ только для staff-пользователей (администраторов)."""

    message = 'Доступ разрешён только администраторам.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsActiveUser(BasePermission):
    """Блокирует деактивированных (забаненных) пользователей."""

    message = 'Пользователь деактивирован.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)
