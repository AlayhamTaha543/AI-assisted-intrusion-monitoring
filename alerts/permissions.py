from rest_framework.permissions import BasePermission


class IsAnalyst(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.groups.filter(name='analyst').exists() or user.is_superuser
