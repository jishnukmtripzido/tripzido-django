from django.urls import path
from apps.users.views import (
    SendOTPView,
    OTPVerifyAndTokenView,
    LogoutView,
    ProfileView,
    RegisterSendOTPView,  # ← new
    RegisterVerifyOTPView,  # ← new
)

urlpatterns = [
    # ── Login ──────────────────────────────────────────────────────────────
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", OTPVerifyAndTokenView.as_view(), name="verify-otp"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", ProfileView.as_view(), name="profile"),
    # ── Registration ───────────────────────────────────────────────────────
    path("register/send-otp/", RegisterSendOTPView.as_view(), name="register-send-otp"),
    path(
        "register/verify-otp/",
        RegisterVerifyOTPView.as_view(),
        name="register-verify-otp",
    ),
]
