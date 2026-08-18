from django.urls import path
from apps.vendors.views import (
    AdminBankAccountReviewView,
    AdminDocumentReviewView,
    AdminSubscriptionPlanDetailView,
    AdminSubscriptionPlanListCreateView,
    AdminVendorBankAccountsView,
    AdminVendorCommissionDetailView,
    AdminVendorCommissionListCreateView,
    AdminVendorDetailView,
    AdminVendorDocumentsView,
    AdminVendorListView,
    AdminVendorRegistrationView,
    AdminVendorStatusUpdateView,
    AdminVendorSubscriptionAssignView,
    AdminVendorSubscriptionsView,
    VendorDashboardView,
    VendorTermsView,
    VendorTermsManageView,
)

urlpatterns = [
    # Vendor's own terms — auth required, no vendor_id in URL.
    path("me/terms/", VendorTermsManageView.as_view(), name="vendor-terms-manage"),
    # Public read of a specific vendor's terms — used by the customer app.
    path("<int:vendor_id>/terms/", VendorTermsView.as_view(), name="vendor-terms"),
    path("me/dashboard/", VendorDashboardView.as_view(), name="vendor-dashboard"),
    path("admin/vendors/", AdminVendorListView.as_view(), name="admin-vendor-list"),
    path(
        "admin/vendors/<int:vendor_id>/",
        AdminVendorDetailView.as_view(),
        name="admin-vendor-detail",
    ),
    path(
        "admin/vendors/<int:vendor_id>/status/",
        AdminVendorStatusUpdateView.as_view(),
        name="admin-vendor-status",
    ),
    path(
        "admin/vendors/<int:vendor_id>/documents/",
        AdminVendorDocumentsView.as_view(),
        name="admin-vendor-documents",
    ),
    path(
        "admin/documents/<int:doc_id>/review/",
        AdminDocumentReviewView.as_view(),
        name="admin-document-review",
    ),
    path(
        "admin/vendors/<int:vendor_id>/bank-accounts/",
        AdminVendorBankAccountsView.as_view(),
        name="admin-vendor-bank-accounts",
    ),
    path(
        "admin/bank-accounts/<int:account_id>/review/",
        AdminBankAccountReviewView.as_view(),
        name="admin-bank-account-review",
    ),
    path(
        "admin/commissions/",
        AdminVendorCommissionListCreateView.as_view(),
        name="admin-commissions",
    ),
    path(
        "admin/commissions/<int:commission_id>/",
        AdminVendorCommissionDetailView.as_view(),
        name="admin-commission-detail",
    ),
    path(
        "admin/vendors/<int:vendor_id>/subscriptions/",
        AdminVendorSubscriptionsView.as_view(),
        name="admin-vendor-subscriptions",
    ),
    path(
        "admin/vendors/<int:vendor_id>/subscriptions/assign/",
        AdminVendorSubscriptionAssignView.as_view(),
        name="admin-vendor-subscription-assign",
    ),
    path(
        "admin/subscription-plans/",
        AdminSubscriptionPlanListCreateView.as_view(),
        name="admin-subscription-plans",
    ),
    path(
        "admin/subscription-plans/<int:plan_id>/",
        AdminSubscriptionPlanDetailView.as_view(),
        name="admin-subscription-plan-detail",
    ),
    path(
        "admin/register/",
        AdminVendorRegistrationView.as_view(),
        name="admin-vendor-registration",
    ),
]
