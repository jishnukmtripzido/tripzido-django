from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.core.responses import success_response, error_response
from apps.core.pagination import CustomPagination


class NotificationListView(GenericAPIView):
    """
    GET /api/notifications/?portal=&unread_only=&page=
    Now also filtered by portal, not just recipient — a single login
    can genuinely hold both a VENDOR and a SUPPORT/SUPER_ADMIN role at
    once, which would otherwise leak admin notifications into the
    vendor bell (and vice versa) for that account.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = CustomPagination

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user)
        portal = request.query_params.get("portal")
        if portal:
            qs = qs.filter(portal=portal)
        if request.query_params.get("unread_only") in ("true", "1"):
            qs = qs.filter(is_read=False)
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Notifications retrieved successfully",
            status=status.HTTP_200_OK,
        )


class NotificationUnreadCountView(APIView):
    """GET /api/notifications/unread-count/?portal="""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user, is_read=False)
        portal = request.query_params.get("portal")
        if portal:
            qs = qs.filter(portal=portal)
        return success_response(
            data={"count": qs.count()},
            message="Unread count retrieved successfully",
            status=status.HTTP_200_OK,
        )


class NotificationMarkReadView(APIView):
    """PATCH /api/notifications/<int:notification_id>/read/"""

    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id: int):
        notification = Notification.objects.filter(
            id=notification_id, recipient=request.user
        ).first()
        if notification is None:
            return error_response(
                message="Notification not found", status=status.HTTP_404_NOT_FOUND
            )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return success_response(
            data=None,
            message="Notification marked as read",
            status=status.HTTP_200_OK,
        )


class NotificationMarkAllReadView(APIView):
    """POST /api/notifications/mark-all-read/"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return success_response(
            data=None,
            message="All notifications marked as read",
            status=status.HTTP_200_OK,
        )
