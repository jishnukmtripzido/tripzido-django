from rest_framework.permissions import BasePermission


class IsStaffRole(BasePermission):
    """
    Grants access only to authenticated users holding SUPPORT or
    SUPER_ADMIN role — the two roles allowed into the admin portal.
    Stacks on top of IsAuthenticated (a request must already carry a
    valid JWT); this only adds the role check on top of that.
    """

    message = "This account does not have admin access."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.has_role("SUPER_ADMIN") or user.has_role("SUPPORT")
