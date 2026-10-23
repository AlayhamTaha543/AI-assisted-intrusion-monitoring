from rest_framework.permissions import BasePermission


class IsIngestor(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.groups.filter(name='ingestor').exists() or user.is_superuser
