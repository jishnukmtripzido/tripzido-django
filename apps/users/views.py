from django.shortcuts import render

# Create your views here.
# apps/users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User
from rest_framework import status
from django.core.cache import cache
from django.conf import settings
from drf_spectacular.utils import extend_schema
from drf_spectacular.openapi import OpenApiParameter
from drf_spectacular.types import OpenApiTypes
import random
from .services import UserService
from apps.core.responses import success_response, error_response
from .serializers import (
    SendOTPSerializer,
    VerifyOTPSerializer,
    RegisterSendOTPSerializer,
    RegisterVerifyOTPSerializer,
)
from .tasks import send_otp_sms
import requests
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.core.responses import success_response, error_response
from .services import UserService
from .serializers import ProfileSerializer, ProfileUpdateSerializer


class SendOTPView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SendOTPSerializer,  # Tells Swagger to expect a JSON body matching this serializer
        description="Sends an OTP to the provided phone number.",
    )
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid phone number or token.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        phone_number = serializer.validated_data.get("phone_number")
        turnstile_token = serializer.validated_data.get("turnstile_token")

        if not phone_number:
            return error_response(
                message="Phone number is required.",
                errors={"phone_number": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # 1. CLOUDFLARE TURNSTILE VERIFICATION
        # ==========================================
        if not turnstile_token:
            return error_response(
                message="Bot verification token is missing.",
                errors={"turnstile_token": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cloudflare_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        # Ensure you add TURNSTILE_SECRET_KEY to your Django settings.py
        cf_payload = {
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": turnstile_token,
        }

        try:
            cf_response = requests.post(cloudflare_url, data=cf_payload)
            cf_data = cf_response.json()

            if not cf_data.get("success"):
                return error_response(
                    message="Bot verification failed.",
                    # Cloudflare returns error-codes if validation fails
                    errors={"turnstile": cf_data.get("error-codes", ["Invalid token"])},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except requests.RequestException:
            # Handle the rare case where Cloudflare is unreachable
            return error_response(
                message="Error contacting verification server. Please try again.",
                errors={},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        # ==========================================
        # END VERIFICATION
        # =====

        # check if user exists with this phone number
        user = UserService.get_user_by_phone(phone_number)
        if not user:
            return error_response(
                message="User with this phone number does not exist. Please register first.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate a random 4-digit OTP
        otp = str(random.randint(1000, 9999))

        print(
            f"Generated OTP for {phone_number}: {otp}"
        )  # For debugging, remove in production

        # Store the OTP in Redis with a 5-minute expiration
        cache.set(f"otp_{phone_number}", otp, timeout=300)

        # 🚀 Fire and forget — no waiting
        send_otp_sms.delay(phone_number, otp)

        # Here you would integrate with an SMS gateway to send the OTP to the user's phone number.
        # For this example, we'll just return the OTP in the response (not recommended for production).
        return success_response(
            message="OTP sent successfully", data={}, status=status.HTTP_200_OK
        )


class OTPVerifyAndTokenView(APIView):
    """
    After OTP is verified, call this to get JWT tokens.
    Your OTP verification logic runs first, then this issues the tokens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=VerifyOTPSerializer,  # Tells Swagger to expect a JSON body matching this
        description="Verifies the provided OTP and issues JWT tokens if valid.",
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data provided.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )
        phone_number = serializer.validated_data.get("phone_number")
        otp = request.data.get("otp")

        # 1. verify OTP here
        # fetch the stored code from redis
        cached_otp = cache.get(f"otp_{phone_number}")
        if cached_otp is None:
            return error_response(
                message="OTP expired or not found. Please request a new one.",
                errors={"otp": ["OTP not found or expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(cached_otp) != str(otp):
            return error_response(
                message="Invalid OTP. Please try again.",
                errors={"otp": ["Incorrect OTP."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. get or create user
        user = UserService.get_user_by_phone(phone_number)
        if not user:
            return error_response(
                message="User not found. Please register first.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. issue tokens
        refresh = RefreshToken.for_user(user)

        return success_response(
            message="OTP verified and tokens issued",
            data={
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()  # This will blacklist the token, preventing future use
            return success_response(
                message="Logged out successfully", data={}, status=status.HTTP_200_OK
            )
        except Exception as e:
            return error_response(
                message="Invalid token or logout failed",
                errors=str(e),
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProfileView(GenericAPIView):
    """
    GET  /api/users/me/   -> current user's profile
    PATCH /api/users/me/  -> partial update of name / email / address
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return success_response(
            data=serializer.data,
            message="Profile retrieved successfully",
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        update_serializer = ProfileUpdateSerializer(data=request.data)
        if not update_serializer.is_valid():
            return error_response(
                message="Invalid profile data",
                errors=update_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_user = UserService.update_profile(
            request.user, update_serializer.to_internal_fields()
        )

        response_serializer = ProfileSerializer(updated_user)
        return success_response(
            data=response_serializer.data,
            message="Profile updated successfully",
            status=status.HTTP_200_OK,
        )


# ── Add these two views to your existing apps/users/views.py ───────────────
# Also add RegisterSendOTPSerializer, RegisterVerifyOTPSerializer to the
# serializers import at the top of views.py.


class RegisterSendOTPView(APIView):
    """
    POST /api/users/register/send-otp/

    Creates (or re-uses a pending) user record and fires an OTP to the
    provided phone number.  The user is NOT yet considered "registered"
    until they complete OTP verification via RegisterVerifyOTPView.

    Request body:
        phone_number    (str, required)
        first_name      (str, required)
        last_name       (str, optional)
        email           (str, optional)
        turnstile_token (str, required)

    Responses:
        200 – OTP dispatched
        400 – validation error
        403 – Cloudflare Turnstile verification failed
        409 – phone number already registered to an active account
        500 – Cloudflare unreachable
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSendOTPSerializer,
        description="Validates registration details, creates a pending user, and sends OTP.",
    )
    def post(self, request):
        serializer = RegisterSendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid registration data.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = serializer.validated_data["phone_number"]
        first_name = serializer.validated_data["first_name"]
        last_name = serializer.validated_data.get("last_name", "")
        email = serializer.validated_data.get("email") or None
        turnstile_token = serializer.validated_data["turnstile_token"]

        # ── 1. Cloudflare Turnstile bot check ──────────────────────────────
        cloudflare_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        try:
            cf_response = requests.post(
                cloudflare_url,
                data={
                    "secret": settings.TURNSTILE_SECRET_KEY,
                    "response": turnstile_token,
                },
            )
            cf_data = cf_response.json()
            if not cf_data.get("success"):
                return error_response(
                    message="Bot verification failed.",
                    errors={"turnstile": cf_data.get("error-codes", ["Invalid token"])},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except requests.RequestException:
            return error_response(
                message="Error contacting verification server. Please try again.",
                errors={},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── 2. Duplicate-phone check ───────────────────────────────────────
        existing = UserService.get_user_by_phone(phone_number)
        if existing:
            return error_response(
                message="An account with this phone number already exists. Please sign in.",
                errors={"phone_number": ["Phone number already registered."]},
                status=status.HTTP_409_CONFLICT,
            )

        # ── 3. Create (or idempotently upsert) the user ───────────────────
        # We create the user now so that on OTP verification we can issue
        # tokens immediately.  The account is functional from the moment
        # it's created; the OTP step is the ownership proof.
        UserService.create_user(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )

        # ── 4. Generate & cache OTP ───────────────────────────────────────
        otp = str(random.randint(1000, 9999))
        print(f"[DEBUG] Registration OTP for {phone_number}: {otp}")  # remove in prod
        cache.set(f"otp_{phone_number}", otp, timeout=300)

        # ── 5. Dispatch OTP via SMS (async Celery task) ───────────────────
        send_otp_sms.delay(phone_number, otp)

        return success_response(
            message="OTP sent successfully. Please verify to complete registration.",
            data={},
            status=status.HTTP_200_OK,
        )


class RegisterVerifyOTPView(APIView):
    """
    POST /api/users/register/verify-otp/

    Verifies the OTP for a newly registered phone number and — on
    success — issues JWT access + refresh tokens so the user is
    immediately logged in.

    Request body:
        phone_number (str, required)
        otp          (str, required, 4 digits)

    Responses:
        200 – OTP valid; returns access_token + refresh_token
        400 – invalid/expired OTP or validation error
        404 – no user found for this phone number
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterVerifyOTPSerializer,
        description="Verifies OTP for registration and issues JWT tokens.",
    )
    def post(self, request):
        serializer = RegisterVerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Invalid data provided.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = serializer.validated_data["phone_number"]
        otp = serializer.validated_data["otp"]

        # ── 1. OTP verification ───────────────────────────────────────────
        cached_otp = cache.get(f"otp_{phone_number}")
        if cached_otp is None:
            return error_response(
                message="OTP expired or not found. Please request a new one.",
                errors={"otp": ["OTP not found or expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(cached_otp) != str(otp):
            return error_response(
                message="Invalid OTP. Please try again.",
                errors={"otp": ["Incorrect OTP."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Fetch the pre-created user ─────────────────────────────────
        user = UserService.get_user_by_phone(phone_number)
        if not user:
            return error_response(
                message="User not found. Please restart registration.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Consume the OTP so it can't be reused
        cache.delete(f"otp_{phone_number}")

        # ── 3. Issue JWT tokens ───────────────────────────────────────────
        refresh = RefreshToken.for_user(user)

        return success_response(
            message="Registration complete. Welcome!",
            data={
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
            },
            status=status.HTTP_200_OK,
        )
