from django.http import HttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.generics import GenericAPIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from datetime import datetime
import json
import logging

from apps.bookings.services import BookingCheckoutService
from apps.bookings.signature import verify_cashfree_signature
from apps.bookings.cashfree_client import CashfreeClient
from apps.core.responses import success_response, error_response
from django.conf import settings

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
