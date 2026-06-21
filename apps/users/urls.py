from django.urls import path
from apps.users.views import (
    SendOTPView,
    OTPVerifyAndTokenView,
    LogoutView,
    ProfileView,
)

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", OTPVerifyAndTokenView.as_view(), name="verify-otp"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", ProfileView.as_view(), name="profile"),
]
