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
from .serializers import (SendOTPSerializer, VerifyOTPSerializer)
from .tasks import send_otp_sms 
import requests







class SendOTPView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=SendOTPSerializer,  # Tells Swagger to expect a JSON body matching this serializer
        description="Sends an OTP to the provided phone number."
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
            "response": turnstile_token
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



        #check if user exists with this phone number
        user = UserService.get_user_by_phone(phone_number)
        if not user:
            return error_response(
                message="User with this phone number does not exist. Please register first.",
                errors={"phone_number": ["No user with this phone number."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate a random 4-digit OTP
        otp = str(random.randint(1000, 9999))

        print(f"Generated OTP for {phone_number}: {otp}")  # For debugging, remove in production

        # Store the OTP in Redis with a 5-minute expiration
        cache.set(f"otp_{phone_number}", otp, timeout=300)

        # 🚀 Fire and forget — no waiting
        send_otp_sms.delay(phone_number, otp)

        # Here you would integrate with an SMS gateway to send the OTP to the user's phone number.
        # For this example, we'll just return the OTP in the response (not recommended for production).
        return success_response(message="OTP sent successfully", data={}, status=status.HTTP_200_OK)





class OTPVerifyAndTokenView(APIView):
    """
    After OTP is verified, call this to get JWT tokens.
    Your OTP verification logic runs first, then this issues the tokens.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=VerifyOTPSerializer,  # Tells Swagger to expect a JSON body matching this
        description="Verifies the provided OTP and issues JWT tokens if valid."
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

        return success_response(message="OTP verified and tokens issued", data={
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
        },
        status=status.HTTP_200_OK)






class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()  # This will blacklist the token, preventing future use
            return success_response(message="Logged out successfully", data={}, status=status.HTTP_200_OK)
        except Exception as e:
            return error_response(message="Invalid token or logout failed", errors=str(e), status=status.HTTP_400_BAD_REQUEST)
