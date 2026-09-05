import json
import logging
import uuid
from datetime import datetime

# Django
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

# Django Rest Framework
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

# DRF Spectacular
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

# Local Apps - Bookings
from apps.bookings.cashfree_client import CashfreeClient
from apps.bookings.serializers import (
    AdminBookingDetailSerializer,
    AdminBookingListSerializer,
    AdminCancelBookingRequestSerializer,
    BookingCancellationSerializer,
    BookingConfirmationSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    CancellationPreviewSerializer,
    CancelBookingRequestSerializer,
    VendorBookingListSerializer,
    VendorBookingDetailSerializer,
    VendorBookingStatusUpdateSerializer,
    VendorCancelBookingRequestSerializer,
    BookingReviewSubmitSerializer,  # NEW
    BookingReviewDetailSerializer,
)
from apps.bookings.services import (
    BookingCheckoutService,
    BookingQueryService,
    CancellationService,
    InvoiceService,
    VendorBookingService,
    BookingReviewService,
)
from apps.bookings.repositories import BookingRepository
from apps.bookings.signature import verify_cashfree_signature
from apps.payments.models import Payment
from apps.bookings.models import Booking, BookingCancellation

# Local Apps - Core
from apps.core.pagination import CustomPagination
from apps.core.permissions import IsStaffRole
from apps.core.responses import error_response, success_response
from apps.core.utils import parse_client_datetime

logger = logging.getLogger(__name__)


class CreateBookingOrderView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        required = [
            "listing_id",
            "package_id",
            "pickup_datetime",
            "dropoff_datetime",
            "quantity",
        ]
        missing = [f for f in required if f not in data]
        if missing:
            return error_response(
                message="Missing required fields",
                errors={"missing": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # try:
        #     pickup_dt = datetime.fromisoformat(data["pickup_datetime"])
        #     dropoff_dt = datetime.fromisoformat(data["dropoff_datetime"])
        #     quantity = int(data["quantity"])
        # except (ValueError, TypeError):
        #     return error_response(
        #         message="Invalid date or quantity format",
        #         status=status.HTTP_400_BAD_REQUEST,
        #     )
        try:
            pickup_dt = parse_client_datetime(data["pickup_datetime"])
            dropoff_dt = parse_client_datetime(data["dropoff_datetime"])
            quantity = int(data["quantity"])
        except (ValueError, TypeError):
            return error_response(
                message="Invalid date or quantity format",
                status=status.HTTP_400_BAD_REQUEST,
            )

        return_url = (
            f"{settings.FRONTEND_BASE_URL}/checkout/processing?order_id={{order_id}}"
        )

        result, error = BookingCheckoutService.create_order(
            customer=request.user,
            listing_id=data["listing_id"],
            package_id=data["package_id"],
            pickup_dt=pickup_dt,
            dropoff_dt=dropoff_dt,
            quantity=quantity,
            payment_mode=data.get("payment_mode", "FULL"),
            return_url=return_url,
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        if result is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=result,
            message="Order created successfully",
            status=status.HTTP_201_CREATED,
        )


class BookingPaymentStatusView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id: str):
        local_status = BookingCheckoutService.get_status(order_id)
        if local_status is None:
            return error_response(
                message="Order not found", status=status.HTTP_404_NOT_FOUND
            )

        if local_status["status"] in ("SUCCESS", "FAILED"):
            return success_response(
                data=local_status, message="Status retrieved", status=status.HTTP_200_OK
            )

        # Webhook may not have arrived yet — Cashfree's own guidance is to
        # always double-check via Get Order before treating anything as
        # confirmed, so fall back to a direct gateway call here.
        try:
            gateway_order = CashfreeClient.fetch_order(order_id)
        except Exception:
            return success_response(
                data=local_status, message="Status retrieved", status=status.HTTP_200_OK
            )

        order_status = (
            gateway_order.get("order_status")
            if isinstance(gateway_order, dict)
            else None
        )
        if order_status == "PAID":
            BookingCheckoutService.confirm_payment_success(
                order_id, {"data": {"order": gateway_order}}
            )
        elif order_status in ("EXPIRED", "TERMINATED"):
            BookingCheckoutService.mark_payment_failed(
                order_id, f"Gateway reported {order_status}"
            )

        local_status = BookingCheckoutService.get_status(order_id)
        return success_response(
            data=local_status, message="Status retrieved", status=status.HTTP_200_OK
        )


@method_decorator(csrf_exempt, name="dispatch")
class CashfreeWebhookView(View):
    """
    Plain Django view, not DRF — needs the exact raw request body for
    signature verification before any JSON parsing happens.
    """

    def post(self, request, *args, **kwargs):
        raw_body = request.body
        timestamp = request.headers.get("x-webhook-timestamp")
        signature = request.headers.get("x-webhook-signature")

        if not verify_cashfree_signature(raw_body, timestamp, signature):
            logger.warning("Cashfree webhook signature verification failed")
            return HttpResponse(status=400)

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return HttpResponse(status=400)

        event_type = payload.get("type", "")
        order_id = payload.get("data", {}).get("order", {}).get("order_id")

        if not order_id:
            return HttpResponse(status=400)

        if event_type == "PAYMENT_SUCCESS_WEBHOOK":
            BookingCheckoutService.confirm_payment_success(order_id, payload)
        elif event_type in ("PAYMENT_FAILED_WEBHOOK", "PAYMENT_USER_DROPPED_WEBHOOK"):
            reason = (
                payload.get("data", {})
                .get("payment", {})
                .get("payment_message", event_type)
            )
            BookingCheckoutService.mark_payment_failed(order_id, reason)
        else:
            logger.info("Unhandled Cashfree webhook event type: %s", event_type)

        # Always 2xx quickly once verified — Cashfree expects a fast ack
        # and will retry on non-2xx, slow, or missing responses.
        return HttpResponse(status=200)


class CustomerBookingsView(GenericAPIView):
    """
    GET /api/bookings/?status=pending|confirmed|ongoing|completed|cancelled

    Powers BookingsList.tsx's tab switcher — one tab, one status filter,
    one paginated request. Defaults to "pending" to match the
    component's initial `useState<BookingTab>("Pending")`.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BookingListSerializer
    pagination_class = CustomPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="One of: pending, confirmed, ongoing, completed, cancelled. Defaults to pending.",
            ),
        ],
        responses=BookingListSerializer(many=True),
    )
    def get(self, request):
        tab = request.query_params.get("status", "pending")

        bookings, error = BookingQueryService.get_customer_bookings(request.user, tab)
        if bookings is None:
            return error_response(
                message=error,
                status=status.HTTP_400_BAD_REQUEST,
            )

        page = self.paginate_queryset(bookings)
        serializer = self.get_serializer(page, many=True, context={"request": request})
        paginated_response = self.get_paginated_response(serializer.data)

        return success_response(
            data=paginated_response.data,
            message="Bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class CustomerBookingDetailView(GenericAPIView):
    """GET /api/bookings/{id}/ — full detail for the "View Details" page."""

    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer

    def get(self, request, booking_id: int):
        booking = BookingQueryService.get_booking_detail(booking_id, request.user)

        if booking is None:
            return error_response(
                message="Booking not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = BookingDetailSerializer(booking, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Booking details retrieved successfully",
            status=status.HTTP_200_OK,
        )


class BookingConfirmationView(GenericAPIView):
    """
    GET /api/bookings/confirmation/?group=<uuid>

    Powers the post-checkout "Booking Confirmed!" page. A single
    checkout can create multiple Booking rows sharing one
    booking_group_id (bulk booking — see
    BookingCheckoutService.create_order), all paid for by one Payment.
    This fetches the whole group, not a single booking_reference, so a
    multi-vehicle order shows every vehicle rather than just the first
    one.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BookingConfirmationSerializer

    def get(self, request):
        group_id = request.query_params.get("group")
        if not group_id:
            return error_response(
                message="Missing required 'group' query parameter",
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            uuid.UUID(str(group_id))
        except (ValueError, AttributeError, TypeError):
            return error_response(
                message="'group' must be a valid booking group id",
                status=status.HTTP_400_BAD_REQUEST,
            )

        bookings = list(BookingRepository.get_bookings_by_group(group_id, request.user))
        if not bookings:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        payment = (
            Payment.objects.filter(booking_group_id=group_id)
            .order_by("-initiated_at")
            .first()
        )

        data = {
            "booking_group_id": group_id,
            "payment_status": payment.status if payment else "",
            "payment_mode": bookings[0].payment_mode,
            "total_paid": float(sum(b.advance_amount for b in bookings)),
            "total_deposit": float(sum(b.security_deposit_amount for b in bookings)),
            "vehicle_count": len(bookings),
            "bookings": bookings,
        }
        serializer = BookingConfirmationSerializer(data, context={"request": request})
        return success_response(
            data=serializer.data,
            message="Booking confirmation retrieved successfully",
            status=status.HTTP_200_OK,
        )


class BookingCancellationPreviewView(GenericAPIView):
    """
    GET /api/bookings/{id}/cancellation-preview/

    Lets the frontend show "you'll get ₹X back" before the customer
    confirms cancellation, plus the full refund schedule. Read-only —
    does not cancel anything.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CancellationPreviewSerializer

    def get(self, request, booking_id: int):
        booking = BookingQueryService.get_booking_detail(booking_id, request.user)
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        preview, error = CancellationService.preview_cancellation(booking)
        if preview is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        serializer = CancellationPreviewSerializer(preview)
        return success_response(
            data=serializer.data,
            message="Cancellation preview retrieved successfully",
            status=status.HTTP_200_OK,
        )


class CancelBookingView(GenericAPIView):
    """
    POST /api/bookings/{id}/cancel/
    Body: { "reason_code": "CHANGE_OF_PLANS", "reason_text": "" }

    Cancels a CONFIRMED booking owned by the requesting customer.
    Computes and records the refund entitlement but does not call the
    payment gateway to actually issue it (see CancellationService).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CancelBookingRequestSerializer

    def post(self, request, booking_id: int):
        booking = BookingQueryService.get_booking_detail(booking_id, request.user)
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        request_serializer = CancelBookingRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return error_response(
                message="Invalid cancellation request",
                errors=request_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancellation, error = CancellationService.cancel_booking(
            booking,
            cancelled_by_user=request.user,
            reason_code=request_serializer.validated_data["reason_code"],
            reason_text=request_serializer.validated_data.get("reason_text", ""),
        )

        if cancellation is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        serializer = BookingCancellationSerializer(cancellation)
        return success_response(
            data=serializer.data,
            message="Booking cancelled successfully",
            status=status.HTTP_200_OK,
        )


class VendorBookingsView(GenericAPIView):
    """
    GET /api/bookings/vendor/?status=all|confirmed|ongoing|completed|cancelled
    Defaults to "all" — matches the vendor list's initial "All" tab.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VendorBookingListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        tab = request.query_params.get("status", "all")
        bookings, error = VendorBookingService.get_bookings_for_vendor(vendor.id, tab)
        if bookings is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        page = self.paginate_queryset(bookings)
        serializer = self.get_serializer(page, many=True, context={"request": request})
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorBookingDetailView(GenericAPIView):
    """GET /api/bookings/vendor/<int:booking_id>/"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorBookingDetailSerializer

    def get(self, request, booking_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        booking = VendorBookingService.get_booking_detail(booking_id, vendor.id)
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        serializer = VendorBookingDetailSerializer(
            booking, context={"request": request}
        )
        return success_response(
            data=serializer.data,
            message="Booking details retrieved successfully",
            status=status.HTTP_200_OK,
        )


class VendorBookingStatusUpdateView(GenericAPIView):
    """PATCH /api/bookings/vendor/<int:booking_id>/status/  Body: {"status": "ONGOING"}"""

    permission_classes = [IsAuthenticated]
    serializer_class = VendorBookingStatusUpdateSerializer

    def patch(self, request, booking_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = VendorBookingStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid status",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking, error = VendorBookingService.update_status(
            booking_id,
            vendor.id,
            serializer.validated_data["status"],
            request.user,
            verification_pin=serializer.validated_data.get("verification_pin", ""),
        )
        if booking is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        detail_serializer = VendorBookingDetailSerializer(
            booking, context={"request": request}
        )
        return success_response(
            data=detail_serializer.data,
            message="Booking status updated successfully",
            status=status.HTTP_200_OK,
        )


class VendorCancelBookingView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VendorCancelBookingRequestSerializer

    def post(self, request, booking_id: int):
        vendor = request.user.get_vendor_profile()
        if vendor is None:
            return error_response(
                message="This account has no vendor profile.",
                status=status.HTTP_403_FORBIDDEN,
            )

        booking = VendorBookingService.get_booking_detail(booking_id, vendor.id)
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        serializer = VendorCancelBookingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid cancellation request",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancellation, error = CancellationService.cancel_booking_by_vendor(
            booking,
            vendor_user=request.user,
            reason_code=serializer.validated_data["reason_code"],
            reason_text=serializer.validated_data.get("reason_text", ""),
        )
        if cancellation is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        detail = VendorBookingDetailSerializer(booking, context={"request": request})
        return success_response(
            data=detail.data,
            message="Booking cancelled successfully",
            status=status.HTTP_200_OK,
        )


class AdminCancelBookingView(GenericAPIView):
    permission_classes = [
        IsAuthenticated,
        IsStaffRole,
    ]  # + your admin/staff permission class
    serializer_class = AdminCancelBookingRequestSerializer

    def post(self, request, booking_id: int):
        # # plug in your actual admin-role check here
        # if not request.user.is_staff:
        #     return error_response(
        #         message="Not authorized.", status=status.HTTP_403_FORBIDDEN
        #     )

        booking = Booking.objects.filter(id=booking_id).first()
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        serializer = AdminCancelBookingRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid cancellation request",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancellation, error = CancellationService.cancel_booking_by_admin(
            booking,
            admin_user=request.user,
            reason_text=serializer.validated_data["reason_text"],
            refund_percentage_override=serializer.validated_data.get(
                "refund_percentage_override"
            ),
        )
        if cancellation is None:
            return error_response(message=error, status=status.HTTP_400_BAD_REQUEST)

        cancel_serializer = BookingCancellationSerializer(cancellation)
        return success_response(
            data=cancel_serializer.data,
            message="Booking cancelled successfully",
            status=status.HTTP_200_OK,
        )


class AdminBookingListView(GenericAPIView):
    """GET /api/bookings/admin/bookings/?status=&vendor_id=&search=&page="""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBookingListSerializer
    pagination_class = CustomPagination

    def get(self, request):
        qs = Booking.objects.select_related(
            "listing__vendor", "listing__vehicle_type__brand", "customer"
        ).order_by("-created_at")
        status_filter = request.query_params.get("status")
        vendor_id = request.query_params.get("vendor_id")
        search = request.query_params.get("search")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if vendor_id:
            qs = qs.filter(listing__vendor_id=vendor_id)
        if search:
            qs = qs.filter(
                Q(booking_reference__icontains=search)
                | Q(listing__vendor__business_name__icontains=search)
                | Q(customer__phone_number__icontains=search)
            )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        paginated_response = self.get_paginated_response(serializer.data)
        return success_response(
            data=paginated_response.data,
            message="Bookings retrieved successfully",
            status=status.HTTP_200_OK,
        )


class AdminBookingDetailView(GenericAPIView):
    """GET /api/bookings/admin/bookings/<int:booking_id>/"""

    permission_classes = [IsAuthenticated, IsStaffRole]
    serializer_class = AdminBookingDetailSerializer

    def get(self, request, booking_id: int):
        booking = (
            Booking.objects.filter(id=booking_id)
            .select_related(
                "listing__vendor",
                "listing__vehicle_type__brand",
                "customer",
                "pickup_location",
                "cancellation",
            )
            .prefetch_related("payments")
            .first()
        )
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(booking)
        return success_response(
            data=serializer.data,
            message="Booking retrieved successfully",
            status=status.HTTP_200_OK,
        )


class BookingInvoiceView(GenericAPIView):
    """GET /api/bookings/<id>/invoice/ — downloads a PDF invoice."""

    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id: int):
        booking = BookingQueryService.get_booking_detail(booking_id, request.user)
        if booking is None:
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )

        if not InvoiceService.is_eligible(booking):
            return error_response(
                message="Invoice is only available once a booking is confirmed.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = InvoiceService.generate_invoice_pdf(booking)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="invoice-{booking.booking_reference}.pdf"'
        )
        return response


class BookingReviewView(GenericAPIView):
    """
    GET    /api/bookings/{id}/review/  — this customer's review for this booking, or null
    POST   /api/bookings/{id}/review/  — create one (booking must be COMPLETED, one per booking)
    PATCH  /api/bookings/{id}/review/  — edit the existing one

    Ownership + existence enforced by BookingQueryService.get_booking_detail,
    same scoping every other endpoint on this resource already relies on.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BookingReviewSubmitSerializer

    def get(self, request, booking_id: int):
        review, error = BookingReviewService.get_existing_review(
            booking_id, request.user
        )
        if error == "not_found":
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )
        if review is None:
            return success_response(
                data=None, message="No review yet", status=status.HTTP_200_OK
            )

        serializer = BookingReviewDetailSerializer(review)
        return success_response(
            data=serializer.data,
            message="Review retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def post(self, request, booking_id: int):
        serializer = BookingReviewSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid review data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        ratings = {
            r["criterion"]: r["score"] for r in serializer.validated_data["ratings"]
        }
        review, error = BookingReviewService.submit_review(
            booking_id,
            request.user,
            serializer.validated_data["review_text"],
            ratings,
        )
        if error == "not_found":
            return error_response(
                message="Booking not found", status=status.HTTP_404_NOT_FOUND
            )
        if error == "not_completed":
            return error_response(
                message="You can only review a completed booking.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        if error == "already_reviewed":
            return error_response(
                message="You've already reviewed this booking.",
                status=status.HTTP_409_CONFLICT,
            )

        output = BookingReviewDetailSerializer(review)
        return success_response(
            data=output.data,
            message="Review submitted successfully",
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, booking_id: int):
        serializer = BookingReviewSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid review data",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        ratings = {
            r["criterion"]: r["score"] for r in serializer.validated_data["ratings"]
        }
        review, error = BookingReviewService.update_review(
            booking_id,
            request.user,
            serializer.validated_data["review_text"],
            ratings,
        )
        if error == "not_found":
            return error_response(
                message="Review not found", status=status.HTTP_404_NOT_FOUND
            )

        output = BookingReviewDetailSerializer(review)
        return success_response(
            data=output.data,
            message="Review updated successfully",
            status=status.HTTP_200_OK,
        )

    def delete(self, request, booking_id: int):
        deleted, error = BookingReviewService.delete_review(booking_id, request.user)
        if error == "not_found":
            return error_response(
                message="Review not found", status=status.HTTP_404_NOT_FOUND
            )
        return success_response(
            data=None,
            message="Review deleted successfully",
            status=status.HTTP_204_NO_CONTENT,
        )
