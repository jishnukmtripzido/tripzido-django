from rest_framework import serializers

class SendOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        required=True,
        help_text="Phone number to send OTP to, e.g. +919999999999"
    )
    turnstile_token = serializers.CharField(
        required=True,
        help_text="Turnstile token from Cloudflare Turnstile widget for bot protection"
    )



class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        required=True,
        help_text="Phone number to verify OTP for, e.g. +919999999999"
    )
    otp = serializers.CharField(
        required=True,
        help_text="OTP to verify"
    )