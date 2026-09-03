import logging
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class NotificationService:

    @staticmethod
    def notify_user(
        user,
        portal: str,
        notification_type: str,
        title: str,
        message: str = "",
        link: str = "",
    ):
        try:
            return Notification.objects.create(
                recipient=user,
                portal=portal,
                notification_type=notification_type,
                title=title,
                message=message,
                link=link,
            )
        except Exception:
            # Never let a notification failure propagate up and take
            # down the caller's transaction — a bug here should never
            # be able to fail a real payment/booking/listing action.
            logger.exception(
                "Failed to create notification for user_id=%s type=%s",
                user.id,
                notification_type,
            )
            return None

    @staticmethod
    def notify_all_staff(
        notification_type: str, title: str, message: str = "", link: str = ""
    ):
        try:
            from apps.users.models import User, UserRoleAssignment

            staff_user_ids = UserRoleAssignment.objects.filter(
                role__system_role__in=["SUPER_ADMIN", "SUPPORT"]
            ).values_list("user_id", flat=True)

            rows = [
                Notification(
                    recipient_id=user_id,
                    portal=Notification.Portal.ADMIN,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    link=link,
                )
                for user_id in staff_user_ids
            ]
            return Notification.objects.bulk_create(rows)
        except Exception:
            logger.exception("Failed to notify staff, type=%s", notification_type)
            return []

    @staticmethod
    def notify_vendor_and_team(
        vendor,
        portal: str,
        notification_type: str,
        title: str,
        message: str = "",
        link: str = "",
    ):
        try:
            from apps.vendors.models import VendorTeamMember

            recipients = [vendor.user]
            team_members = VendorTeamMember.objects.filter(
                vendor=vendor
            ).select_related("user")
            recipients += [tm.user for tm in team_members]

            # bulk_create — was individual .create() calls per
            # recipient before, N round-trips instead of 1.
            rows = [
                Notification(
                    recipient=user,
                    portal=portal,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    link=link,
                )
                for user in recipients
            ]
            return Notification.objects.bulk_create(rows)
        except Exception:
            logger.exception(
                "Failed to notify vendor_id=%s, type=%s", vendor.id, notification_type
            )
            return []
