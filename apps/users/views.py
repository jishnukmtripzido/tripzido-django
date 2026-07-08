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
import json
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
from .repositories import normalize_phone  # shared helper — single source of truth


class SendOTPView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SendOTPSerializer,
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

        # Normalise to local number — consistent with DB storage
        local_number, _ = normalize_phone(phone_number)

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
                    errors={"turnstile": cf_data.get("error-codes", ["Invalid token"])},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except requests.RequestException:
            return error_response(
                message="Error contacting verification server. Please try again.",
                errors={},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        # ==========================================
        # END VERIFICATION
        # ==========================================

        # DB lookup uses local number
        user = UserService.get_user_by_phone(local_number)
        if not user:
            return error_response(
                message="User with this phone number does not exist. Please register first.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate a random 4-digit OTP
        # otp = str(random.randint(1000, 9999))
        otp = "1211"
        print(f"Generated OTP for {local_number}: {otp}")  # Remove in production

        # Cache key uses local number — same format as DB
        cache.set(f"otp_{local_number}", otp, timeout=300)

        # Pass full E.164 to SMS gateway so the carrier can route it
        send_otp_sms.delay(phone_number, otp)

        return success_response(
            message="OTP sent successfully", data={}, status=status.HTTP_200_OK
        )


class OTPVerifyAndTokenView(APIView):
    """
    After OTP is verified, call this to get JWT tokens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=VerifyOTPSerializer,
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

        # Normalise — caller may send "+919876543210" or "9876543210"
        local_number, _ = normalize_phone(phone_number)

        # 1. verify OTP — fetch the stored code from Redis
        cached_otp = cache.get(f"otp_{local_number}")
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

        # 2. fetch user
        user = UserService.get_user_by_phone(local_number)
        if not user:
            return error_response(
                message="User not found. Please register first.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Consume OTP so it cannot be replayed
        cache.delete(f"otp_{local_number}")

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
            token.blacklist()
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


class RegisterSendOTPView(APIView):
    """
    POST /api/users/register/send-otp/

    Validates the registration payload, stores it in Redis alongside the
    OTP, and fires the OTP via SMS.  NO database write happens here —
    the User row is created only after OTP verification succeeds in
    RegisterVerifyOTPView.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSendOTPSerializer,
        description="Validates registration details, caches the payload, and sends OTP. No DB write occurs here.",
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

        # Normalise early — everything below uses local_number for cache keys
        local_number, country_code = normalize_phone(phone_number)

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
        existing = UserService.get_user_by_phone(local_number)
        if existing:
            return error_response(
                message="An account with this phone number already exists. Please sign in.",
                errors={"phone_number": ["Phone number already registered."]},
                status=status.HTTP_409_CONFLICT,
            )

        # ── 3. Generate OTP ───────────────────────────────────────────────
        otp = str(random.randint(1000, 9999))
        print(f"[DEBUG] Registration OTP for {local_number}: {otp}")  # Remove in prod

        # ── 4. Cache OTP + registration payload (no DB write) ─────────────
        #
        # Cache keys use local_number ("9876543210") — same format as DB.
        # country_code is stored in the payload so create_user can save it.
        # Both keys share the same 5-minute TTL.
        cache.set(f"otp_{local_number}", otp, timeout=300)
        cache.set(
            f"reg_payload_{local_number}",
            json.dumps(
                {
                    "local_number": local_number,
                    "country_code": country_code,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                }
            ),
            timeout=300,
        )

        # ── 5. Dispatch OTP via SMS (full E.164 for carrier routing) ──────
        send_otp_sms.delay(phone_number, otp)

        return success_response(
            message="OTP sent successfully. Please verify to complete registration.",
            data={},
            status=status.HTTP_200_OK,
        )


class RegisterVerifyOTPView(APIView):
    """
    POST /api/users/register/verify-otp/

    Verifies the OTP, creates the User row (first DB write), consumes
    both cache keys, and issues JWT tokens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterVerifyOTPSerializer,
        description="Verifies OTP for registration, creates the user, and issues JWT tokens.",
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

        print("i/p phone number and otp from registration", phone_number, otp)

        # Normalise — caller may send either format
        local_number, _ = normalize_phone(phone_number)

        # ── 1. OTP verification ───────────────────────────────────────────
        cached_otp = cache.get(f"otp_{local_number}")

        print("cached otp reg", cached_otp)
        if cached_otp is None:
            return error_response(
                message="OTP expired or not found. Please request a new one.",
                errors={"otp": ["OTP not found or expired."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(cached_otp) != str(otp):
            print("otp wrong")
            return error_response(
                message="Invalid OTP. Please try again.",
                errors={"otp": ["Incorrect OTP."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Load cached registration payload ───────────────────────────
        raw_payload = cache.get(f"reg_payload_{local_number}")
        if not raw_payload:
            return error_response(
                message="Registration session expired. Please start over.",
                errors={
                    "phone_number": ["Session not found. Please re-enter your details."]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = json.loads(raw_payload)

        # ── 3. Create user — only after OTP proves phone ownership ────────
        # Guard against double-tap / concurrent requests
        user = UserService.get_user_by_phone(local_number)
        if not user:
            user = UserService.create_user(
                phone_number=payload["local_number"],  # bare local digits
                country_code=payload["country_code"],  # "+91"
                first_name=payload["first_name"],
                last_name=payload.get("last_name", ""),
                email=payload.get("email"),
            )

        # ── 4. Consume both cache keys — no replay possible ───────────────
        cache.delete(f"otp_{local_number}")
        cache.delete(f"reg_payload_{local_number}")

        # ── 5. Issue JWT tokens ───────────────────────────────────────────
        refresh = RefreshToken.for_user(user)

        return success_response(
            message="Registration complete. Welcome!",
            data={
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
            },
            status=status.HTTP_200_OK,
        )
