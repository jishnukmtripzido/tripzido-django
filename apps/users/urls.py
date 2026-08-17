from django.urls import path
from apps.users.views import (
    SendOTPView,
    OTPVerifyAndTokenView,
    LogoutView,
    ProfileView,
    RegisterSendOTPView,
    RegisterVerifyOTPView,
    VendorSendOTPView,  # ← new
    VendorVerifyOTPView,  # ← new
    StaffLoginView,  # ← new
    AdminCustomerListView,
    AdminCustomerDetailView,
    AdminCustomerStatusUpdateView,
    AdminStaffListCreateView,
    AdminStaffDetailView,
)

urlpatterns = [
    # ── Login (customer) ──────────────────────────────────────────────────
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", OTPVerifyAndTokenView.as_view(), name="verify-otp"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", ProfileView.as_view(), name="profile"),
    # ── Registration (customer) ─────────────────────────────────────────────
    path("register/send-otp/", RegisterSendOTPView.as_view(), name="register-send-otp"),
    path(
        "register/verify-otp/",
        RegisterVerifyOTPView.as_view(),
        name="register-verify-otp",
    ),
    # ── Login (vendor portal) ───────────────────────────────────────────────
    path("vendor/send-otp/", VendorSendOTPView.as_view(), name="vendor-send-otp"),
    path("vendor/verify-otp/", VendorVerifyOTPView.as_view(), name="vendor-verify-otp"),
    path("staff/login/", StaffLoginView.as_view(), name="staff-login"),
    path(
        "admin/customers/", AdminCustomerListView.as_view(), name="admin-customer-list"
    ),
    path(
        "admin/customers/<int:user_id>/",
        AdminCustomerDetailView.as_view(),
        name="admin-customer-detail",
    ),
    path(
        "admin/customers/<int:user_id>/status/",
        AdminCustomerStatusUpdateView.as_view(),
        name="admin-customer-status",
    ),
    path("admin/staff/", AdminStaffListCreateView.as_view(), name="admin-staff-list"),
    path(
        "admin/staff/<int:assignment_id>/",
        AdminStaffDetailView.as_view(),
        name="admin-staff-detail",
    ),
]
