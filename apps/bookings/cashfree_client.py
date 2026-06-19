from django.conf import settings
from cashfree_pg.api_client import Cashfree
from cashfree_pg.models.create_order_request import CreateOrderRequest
from cashfree_pg.models.customer_details import CustomerDetails
from cashfree_pg.models.order_meta import OrderMeta


def _get_cashfree_instance() -> Cashfree:
    return Cashfree(
        XEnvironment=(
            Cashfree.PRODUCTION
            if settings.CASHFREE_ENVIRONMENT == "PRODUCTION"
            else Cashfree.SANDBOX
        ),
        XClientId=settings.CASHFREE_APP_ID,
        XClientSecret=settings.CASHFREE_SECRET_KEY,
    )


class CashfreeClient:

    @staticmethod
    def create_order(
        order_id: str,
        amount,
        customer_id: str,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        return_url: str,
    ) -> dict:
        """
        Creates a Cashfree order and returns {order_id, payment_session_id}.
        Raises on failure — caller decides how to surface that.
        """
        cashfree = _get_cashfree_instance()

        request = CreateOrderRequest(
            order_id=order_id,
            order_amount=float(amount),
            order_currency="INR",
            customer_details=CustomerDetails(
                customer_id=customer_id,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
            ),
            order_meta=OrderMeta(return_url=return_url),
        )
        response = cashfree.PGCreateOrder(request, None, None)
        data = response.data
        return {
            "order_id": data.order_id,
            "payment_session_id": data.payment_session_id,
        }

    @staticmethod
    def fetch_order(order_id: str) -> dict:
        """
        Cashfree's own recommended pattern: always confirm via this call
        before delivering the service, rather than trusting redirect/
        webhook alone. Returns the raw order entity as a dict.
        """
        cashfree = _get_cashfree_instance()
        response = cashfree.PGFetchOrder(order_id, None, None)
        return (
            response.data.to_dict()
            if hasattr(response.data, "to_dict")
            else response.data
        )
