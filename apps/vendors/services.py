# apps/vendors/services.py
from apps.vendors.repositories import (
    AdminBankAccountRepository,
    AdminSubscriptionPlanRepository,
    AdminVendorCommissionRepository,
    AdminVendorDocumentRepository,
    AdminVendorRepository,
    AdminVendorSubscriptionRepository,
    VendorTermsRepository,
    VendorDashboardRepository,
)
from django.utils import timezone
from django.db import transaction
from django.db.models import ProtectedError

from apps.vendors.models import (
    BankAccount,
    SubscriptionPlan,
    Vendor,
    VendorDocument,
    VendorTeamMember,
)


class VendorTermsService:

    @staticmethod
    def get_current_terms(vendor_id: int):
        return VendorTermsRepository.get_current(vendor_id)

    @staticmethod
    def save_new_version(vendor_id: int, data: dict):
        return VendorTermsRepository.save_new_version(vendor_id, data)


def _trend_pct(current, previous) -> float:
    if not previous:
        return 100.0 if current else 0.0
    return round(float((current - previous) / previous * 100), 1)


class VendorDashboardService:

    @staticmethod
    def _month_bounds():
        """(this_month_start, now, last_month_start, last_month_end_exclusive)
        — "this month" is calendar-start-to-date (partial), "last
        month" is the full previous calendar month. Standard MoM
        comparison shape, matches the original mock's rangeLabel intent."""
        now = timezone.localtime()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if this_month_start.month == 1:
            last_month_start = this_month_start.replace(
                year=this_month_start.year - 1, month=12
            )
        else:
            last_month_start = this_month_start.replace(
                month=this_month_start.month - 1
            )
        return this_month_start, now, last_month_start, this_month_start

    @staticmethod
    def get_dashboard(vendor) -> dict:
        this_start, now, last_start, last_end = VendorDashboardService._month_bounds()

        revenue_this_month = VendorDashboardRepository.get_revenue_for_period(
            vendor.id, this_start, now
        )
        revenue_last_month = VendorDashboardRepository.get_revenue_for_period(
            vendor.id, last_start, last_end
        )

        orders_this_month = VendorDashboardRepository.get_orders_count_for_period(
            vendor.id, this_start, now
        )
        orders_last_month = VendorDashboardRepository.get_orders_count_for_period(
            vendor.id, last_start, last_end
        )

        to_start, to_return = VendorDashboardRepository.get_needs_attention(vendor.id)
        fleet = VendorDashboardRepository.get_fleet_snapshot(vendor.id)

        return {
            "vendor_status": vendor.status,
            "vendor_status_label": vendor.get_status_display(),
            "vendor_rejection_reason": vendor.rejection_reason,
            "current_balance": VendorDashboardRepository.get_current_balance(vendor.id),
            "revenue_this_month": revenue_this_month,
            "revenue_last_month": revenue_last_month,
            "revenue_trend_pct": _trend_pct(revenue_this_month, revenue_last_month),
            "orders_this_month": orders_this_month,
            "orders_last_month": orders_last_month,
            "orders_trend_pct": _trend_pct(orders_this_month, orders_last_month),
            "weekly_order_bars": VendorDashboardRepository.get_weekly_booking_counts(
                vendor.id
            ),
            "range_label": f"{this_start:%d %b %Y} - {now:%d %b %Y}",
            "bookings_to_start": to_start,
            "bookings_to_return": to_return,
            "fleet_total_listings": fleet["total_listings"],
            "fleet_pending_approval": fleet["pending_approval"],
            "fleet_blocked_units": fleet["blocked_units"],
            "recent_bookings": VendorDashboardRepository.get_recent_bookings(vendor.id),
        }

    @staticmethod
    def get_status_and_balance(vendor) -> dict:
        return {
            "vendor_status": vendor.status,
            "vendor_status_label": vendor.get_status_display(),
            "vendor_rejection_reason": vendor.rejection_reason,
            "current_balance": VendorDashboardRepository.get_current_balance(vendor.id),
        }

    @staticmethod
    def get_needs_attention_section(vendor) -> dict:
        to_start, to_return = VendorDashboardRepository.get_needs_attention(vendor.id)
        return {
            "bookings_to_start": to_start,
            "bookings_to_return": to_return,
        }

    @staticmethod
    def get_stats(vendor) -> dict:
        this_start, now, last_start, last_end = VendorDashboardService._month_bounds()

        revenue_this_month = VendorDashboardRepository.get_revenue_for_period(
            vendor.id, this_start, now
        )
        revenue_last_month = VendorDashboardRepository.get_revenue_for_period(
            vendor.id, last_start, last_end
        )
        orders_this_month = VendorDashboardRepository.get_orders_count_for_period(
            vendor.id, this_start, now
        )
        orders_last_month = VendorDashboardRepository.get_orders_count_for_period(
            vendor.id, last_start, last_end
        )

        return {
            "revenue_this_month": revenue_this_month,
            "revenue_last_month": revenue_last_month,
            "revenue_trend_pct": _trend_pct(revenue_this_month, revenue_last_month),
            "orders_this_month": orders_this_month,
            "orders_last_month": orders_last_month,
            "orders_trend_pct": _trend_pct(orders_this_month, orders_last_month),
            "weekly_order_bars": VendorDashboardRepository.get_weekly_booking_counts(
                vendor.id
            ),
            "range_label": f"{this_start:%d %b %Y} - {now:%d %b %Y}",
        }

    @staticmethod
    def get_fleet_section(vendor) -> dict:
        fleet = VendorDashboardRepository.get_fleet_snapshot(vendor.id)
        return {
            "fleet_total_listings": fleet["total_listings"],
            "fleet_pending_approval": fleet["pending_approval"],
            "fleet_blocked_units": fleet["blocked_units"],
        }

    @staticmethod
    def get_recent_bookings_section(vendor) -> dict:
        return {
            "recent_bookings": VendorDashboardRepository.get_recent_bookings(vendor.id),
        }


class AdminVendorService:

    # Mirrors the pattern from VendorBookingService.ALLOWED_TRANSITIONS
    # earlier in this project — REJECTED and BANNED are terminal, no
    # further admin transition from this endpoint. A rejected applicant
    # would need to submit a fresh signup; banning is treated as
    # permanent by design.
    ALLOWED_TRANSITIONS = {
        Vendor.Status.PENDING: [Vendor.Status.APPROVED, Vendor.Status.REJECTED],
        Vendor.Status.APPROVED: [Vendor.Status.SUSPENDED, Vendor.Status.BANNED],
        Vendor.Status.SUSPENDED: [Vendor.Status.APPROVED, Vendor.Status.BANNED],
    }
    REASON_REQUIRED_FOR = {
        Vendor.Status.REJECTED,
        Vendor.Status.SUSPENDED,
        Vendor.Status.BANNED,
    }

    @staticmethod
    def get_all(status_filter=None, search=None):
        return AdminVendorRepository.get_all(status_filter, search)

    @staticmethod
    def get_detail(vendor_id: int):
        return AdminVendorRepository.get_by_id(vendor_id)

    @staticmethod
    @transaction.atomic
    def update_status(vendor_id: int, target_status: str, admin_user, reason: str = ""):
        vendor = Vendor.objects.select_for_update().filter(id=vendor_id).first()
        if vendor is None:
            return None, "Vendor not found"

        allowed = AdminVendorService.ALLOWED_TRANSITIONS.get(vendor.status, [])
        if target_status not in allowed:
            return None, (
                f"Cannot change status from '{vendor.get_status_display()}' to '{target_status}'."
            )
        if (
            target_status in AdminVendorService.REASON_REQUIRED_FOR
            and not reason.strip()
        ):
            return None, "A reason is required for this action."

        now = timezone.now()
        was_suspended = vendor.status == Vendor.Status.SUSPENDED

        if target_status == Vendor.Status.APPROVED and not was_suspended:
            vendor.reviewed_by = admin_user
            vendor.reviewed_at = now
        elif target_status == Vendor.Status.APPROVED and was_suspended:
            pass  # reactivation — suspension fields kept as historical record
        elif target_status == Vendor.Status.REJECTED:
            vendor.reviewed_by = admin_user
            vendor.reviewed_at = now
            vendor.rejection_reason = reason
        elif target_status == Vendor.Status.SUSPENDED:
            vendor.suspended_by = admin_user
            vendor.suspended_at = now
            vendor.suspension_reason = reason
        elif target_status == Vendor.Status.BANNED:
            vendor.banned_by = admin_user
            vendor.banned_at = now
            vendor.ban_reason = reason

        vendor.status = target_status
        vendor.save()
        return vendor, None


class AdminVendorDocumentService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return AdminVendorDocumentRepository.get_for_vendor(vendor_id)

    @staticmethod
    def review(doc_id: int, admin_user, new_status: str, rejection_reason: str = ""):
        doc = AdminVendorDocumentRepository.get_by_id(doc_id)
        if doc is None:
            return None, "Document not found"
        if doc.status != VendorDocument.Status.PENDING:
            return None, "This document has already been reviewed."
        if new_status not in (
            VendorDocument.Status.VERIFIED,
            VendorDocument.Status.REJECTED,
        ):
            return None, "Invalid target status."
        if (
            new_status == VendorDocument.Status.REJECTED
            and not rejection_reason.strip()
        ):
            return None, "A rejection reason is required."

        doc.status = new_status
        doc.reviewed_by = admin_user
        doc.reviewed_at = timezone.now()
        if new_status == VendorDocument.Status.REJECTED:
            doc.rejection_reason = rejection_reason
        doc.save()
        return doc, None


class AdminBankAccountService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return AdminBankAccountRepository.get_for_vendor(vendor_id)

    @staticmethod
    def review(
        account_id: int, admin_user, new_status: str, rejection_reason: str = ""
    ):
        account = AdminBankAccountRepository.get_by_id(account_id)
        if account is None:
            return None, "Bank account not found"
        if account.status != BankAccount.Status.PENDING_VERIFICATION:
            return None, "This account has already been reviewed."
        if new_status not in (BankAccount.Status.VERIFIED, BankAccount.Status.REJECTED):
            return None, "Invalid target status."
        if new_status == BankAccount.Status.REJECTED and not rejection_reason.strip():
            return None, "A rejection reason is required."

        account.status = new_status
        account.verified_by = admin_user
        account.verified_at = timezone.now()
        if new_status == BankAccount.Status.VERIFIED:
            # A verified account becomes the vendor's active payout
            # account — the model's own save() already auto-deactivates
            # any other account for this vendor when is_active_acc=True
            # is set, so this is the only line needed to make the switch.
            account.is_active_acc = True
        else:
            account.rejection_reason = rejection_reason
        account.save()
        return account, None


class AdminVendorCommissionService:

    @staticmethod
    def get_all():
        return AdminVendorCommissionRepository.get_all()

    @staticmethod
    def create(data: dict):
        return AdminVendorCommissionRepository.create(data)

    @staticmethod
    def update(commission_id: int, data: dict):
        instance = AdminVendorCommissionRepository.get_by_id(commission_id)
        if instance is None:
            return None
        return AdminVendorCommissionRepository.update(instance, data)

    @staticmethod
    def delete(commission_id: int):
        instance = AdminVendorCommissionRepository.get_by_id(commission_id)
        if instance is None:
            return False, "not_found"
        try:
            AdminVendorCommissionRepository.delete(instance)
        except ProtectedError:
            return False, "in_use"
        return True, None


class AdminSubscriptionPlanService:

    @staticmethod
    def get_all():
        return AdminSubscriptionPlanRepository.get_all()

    @staticmethod
    def get_detail(plan_id: int):
        return AdminSubscriptionPlanRepository.get_by_id(plan_id)

    @staticmethod
    def create(data: dict):
        return AdminSubscriptionPlanRepository.create(data)

    @staticmethod
    def update(plan_id: int, data: dict):
        instance = AdminSubscriptionPlanRepository.get_by_id(plan_id)
        if instance is None:
            return None
        return AdminSubscriptionPlanRepository.update(instance, data)

    @staticmethod
    def delete(plan_id: int):
        instance = AdminSubscriptionPlanRepository.get_by_id(plan_id)
        if instance is None:
            return False, "not_found"
        try:
            AdminSubscriptionPlanRepository.delete(instance)
        except ProtectedError:
            return False, "in_use"
        return True, None


class AdminVendorSubscriptionService:

    @staticmethod
    def get_for_vendor(vendor_id: int):
        return AdminVendorSubscriptionRepository.get_for_vendor(vendor_id)

    @staticmethod
    def assign(vendor_id: int, plan_id: int, admin_user):
        if not Vendor.objects.filter(id=vendor_id).exists():
            return None, "Vendor not found"
        if not SubscriptionPlan.objects.filter(id=plan_id).exists():
            return None, "Plan not found"
        return (
            AdminVendorSubscriptionRepository.assign(vendor_id, plan_id, admin_user),
            None,
        )


class AdminVendorRegistrationService:

    @staticmethod
    @transaction.atomic
    def register(data: dict, admin_user):
        from apps.users.models import User, Role, UserRoleAssignment

        phone_number = data["phone_number"]

        if User.objects.filter(phone_number=phone_number).exists():
            return None, "A user with this phone number already exists."
        if Vendor.objects.filter(email__iexact=data["email"]).exists():
            return None, "A vendor with this email already exists."

        user = User.objects.create(
            phone_number=phone_number,
            phone_country_code=data.get("phone_country_code", "+91"),
            first_name=data["owner_name"],
            email=data["email"],
        )
        user.set_password(data["password"])
        user.save()

        role, _ = Role.objects.get_or_create(
            system_role=Role.SystemRole.VENDOR,
            defaults={"is_system": True},
        )
        UserRoleAssignment.objects.get_or_create(
            user=user,
            role=role,
            defaults={"assigned_by": admin_user},
        )

        vendor = Vendor.objects.create(
            user=user,
            business_name=data["business_name"],
            owner_name=data["owner_name"],
            email=data["email"],
            phone_number=phone_number,
            address=data["address"],
            gst_number=data.get("gst_number", ""),
            # Approved immediately, not PENDING — admin filling this
            # form in and vetting the details themselves already IS
            # the review step, so there's no separate approval queue
            # for vendors created this way.
            status=Vendor.Status.APPROVED,
            reviewed_by=admin_user,
            reviewed_at=timezone.now(),
        )
        return vendor, None


class AdminVendorTeamService:

    @staticmethod
    def get_team(vendor_id: int):
        # all_objects, not objects — the default SoftDeleteManager
        # excludes deactivated members entirely, which would make
        # them permanently invisible here with no way to reactivate.
        return (
            VendorTeamMember.all_objects.filter(vendor_id=vendor_id)
            .select_related("user", "added_by")
            .order_by("-created_at")
        )

    @staticmethod
    @transaction.atomic
    def add_team_member(vendor_id: int, data: dict, admin_user):
        from apps.users.models import User, Role, UserRoleAssignment

        vendor = Vendor.objects.filter(id=vendor_id).first()
        if vendor is None:
            return None, "Vendor not found"

        if User.objects.filter(phone_number=data["phone_number"]).exists():
            return None, "A user with this phone number already exists."

        user = User.objects.create(
            phone_number=data["phone_number"],
            phone_country_code=data.get("phone_country_code", "+91"),
            first_name=data["first_name"],
            last_name=data.get("last_name", ""),
            email=data["email"],
        )
        user.set_password(data["password"])
        user.save()

        role, _ = Role.objects.get_or_create(
            system_role=Role.SystemRole.VENDOR, defaults={"is_system": True}
        )
        UserRoleAssignment.objects.get_or_create(
            user=user, role=role, defaults={"assigned_by": admin_user}
        )

        member = VendorTeamMember.objects.create(
            vendor=vendor, user=user, added_by=admin_user
        )
        return member, None

    @staticmethod
    def deactivate_team_member(member_id: int, deactivated_by) -> bool:
        """
        Soft-deactivates the membership AND blocks the underlying
        login together — a deactivated membership with a still-active
        login would be a real access-control gap, not just a display
        inconsistency.
        """
        member = VendorTeamMember.all_objects.filter(id=member_id).first()
        if member is None:
            return False
        member.delete(deleted_by=deactivated_by)  # BaseModel's soft-delete override
        member.user.is_active = False
        member.user.save(update_fields=["is_active"])
        return True

    @staticmethod
    def restore_team_member(member_id: int) -> bool:
        member = VendorTeamMember.all_objects.filter(id=member_id).first()
        if member is None:
            return False
        member.restore()
        member.user.is_active = True
        member.user.save(update_fields=["is_active"])
        return True

    @staticmethod
    def hard_delete_team_member(member_id: int) -> bool:
        """
        Permanently removes the VendorTeamMember row only — not the
        underlying User. See the note above: BaseModel's PROTECT
        foreign keys make a User hard-delete unreliable once they've
        done anything else in the app. Removing the membership already
        fully revokes access to this vendor.
        """
        member = VendorTeamMember.all_objects.filter(id=member_id).first()
        if member is None:
            return False
        member.hard_delete()
        return True
