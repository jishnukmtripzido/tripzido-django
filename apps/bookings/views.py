import json
import logging
import uuid
from datetime import datetime

# Django
from django.conf import settings
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
    BookingCancellationSerializer,
    BookingConfirmationSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    CancellationPreviewSerializer,
    CancelBookingRequestSerializer,
)
from apps.bookings.services import (
    BookingCheckoutService,
    BookingQueryService,
    CancellationService,
)
from apps.bookings.repositories import BookingRepository
from apps.bookings.signature import verify_cashfree_signature
from apps.payments.models import Payment

# Local Apps - Core
from apps.core.pagination import CustomPagination
from apps.core.responses import error_response, success_response

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

        try:
            pickup_dt = datetime.fromisoformat(data["pickup_datetime"])
            dropoff_dt = datetime.fromisoformat(data["dropoff_datetime"])
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
