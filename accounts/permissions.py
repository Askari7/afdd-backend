from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


def get_allowed_contractor_ids(user):
    """
    Returns the set of contractor IDs (users with role='user') this user may access.
    Returns None for admin/staff (unrestricted). Returns empty list for annotators.
    """
    if not user or not user.is_authenticated:
        return []
    if user.is_staff or user.role == "admin" or user.role == "annotator":
        return None  # None == unrestricted
    if user.role == "user":
        return [user.id]
    if user.role == "manager":
        from accounts.models import ManagerUserAssociation
        return list(
            ManagerUserAssociation.objects.filter(manager=user).values_list("user_id", flat=True)
        )
    return []
