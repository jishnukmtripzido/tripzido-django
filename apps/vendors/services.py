# apps/vendors/services.py
from apps.vendors.repositories import VendorTermsRepository, VendorDashboardRepository
from django.utils import timezone


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
