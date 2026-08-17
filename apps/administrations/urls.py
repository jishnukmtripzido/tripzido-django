from django.urls import path
from apps.administrations.views import (
    AdminDashboardView,
    AdminPlatformConfigDetailView,
    AdminPlatformConfigListCreateView,
    AdminTaxRateListCreateView,
    CancellationPolicyView,
    OfferListView,
    PopularRentalListView,
    AnnouncementBannerView,
    LegalDocumentView,
    AdminOfferListCreateView,
    AdminOfferDetailView,
    AdminPopularRentalListCreateView,
    AdminPopularRentalDetailView,
    AdminAnnouncementBannerListCreateView,
    AdminAnnouncementBannerDetailView,
    AdminCancellationPolicyListCreateView,
    AdminCancellationPolicyDetailView,
    AdminLegalDocumentListCreateView,
)

urlpatterns = [
    path(
        "cancellation-policy/",
        CancellationPolicyView.as_view(),
        name="cancellation-policy",
    ),
    path("offers/", OfferListView.as_view(), name="offer-list"),
    path(
        "popular-rentals/", PopularRentalListView.as_view(), name="popular-rental-list"
    ),
    path(
        "announcement-banner/",
        AnnouncementBannerView.as_view(),
        name="announcement-banner",
    ),
    path("legal-document/", LegalDocumentView.as_view(), name="legal-document"),
    path(
        "admin/tax-rates/", AdminTaxRateListCreateView.as_view(), name="admin-tax-rates"
    ),
    path(
        "admin/platform-config/",
        AdminPlatformConfigListCreateView.as_view(),
        name="admin-platform-config",
    ),
    path(
        "admin/platform-config/<int:config_id>/",
        AdminPlatformConfigDetailView.as_view(),
        name="admin-platform-config-detail",
    ),
    path("admin/offers/", AdminOfferListCreateView.as_view(), name="admin-offers"),
    path(
        "admin/offers/<int:offer_id>/",
        AdminOfferDetailView.as_view(),
        name="admin-offer-detail",
    ),
    path(
        "admin/popular-rentals/",
        AdminPopularRentalListCreateView.as_view(),
        name="admin-popular-rentals",
    ),
    path(
        "admin/popular-rentals/<int:rental_id>/",
        AdminPopularRentalDetailView.as_view(),
        name="admin-popular-rental-detail",
    ),
    path(
        "admin/banners/",
        AdminAnnouncementBannerListCreateView.as_view(),
        name="admin-banners",
    ),
    path(
        "admin/banners/<int:banner_id>/",
        AdminAnnouncementBannerDetailView.as_view(),
        name="admin-banner-detail",
    ),
    path(
        "admin/cancellation-policies/",
        AdminCancellationPolicyListCreateView.as_view(),
        name="admin-cancellation-policies",
    ),
    path(
        "admin/cancellation-policies/<int:policy_id>/",
        AdminCancellationPolicyDetailView.as_view(),
        name="admin-cancellation-policy-detail",
    ),
    path(
        "admin/legal-documents/",
        AdminLegalDocumentListCreateView.as_view(),
        name="admin-legal-documents",
    ),
    path("admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
]
