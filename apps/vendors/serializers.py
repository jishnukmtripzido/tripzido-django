# # apps/vendors/serializers.py
# from rest_framework import serializers
# from apps.bookings.serializers import VendorBookingListSerializer
# from apps.vendors.models import (
#     SubscriptionPlan,
#     VendorSubscription,
#     Vendor,
#     VendorDocument,
#     BankAccount,
#     VendorCommission,
# )


# class VendorTermsSerializer(serializers.Serializer):
#     vendor_id = serializers.IntegerField()
#     version = serializers.IntegerField()
#     terms_items = serializers.ListField(child=serializers.CharField(), default=list)
#     security_deposit_note = serializers.CharField(allow_blank=True)
#     operating_hours_note = serializers.CharField(allow_blank=True)
#     distance_limit_note = serializers.CharField(allow_blank=True)
#     excess_charge_note = serializers.CharField(allow_blank=True)
#     late_penalty_note = serializers.CharField(allow_blank=True)


# class VendorTermsUpdateSerializer(serializers.Serializer):
#     terms_items = serializers.ListField(
#         child=serializers.CharField(allow_blank=False), required=False, default=list
#     )
#     security_deposit_note = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )
#     operating_hours_note = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )
#     distance_limit_note = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )
#     excess_charge_note = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )
#     late_penalty_note = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )


# class VendorDashboardSerializer(serializers.Serializer):
#     vendor_status = serializers.CharField()
#     vendor_status_label = serializers.CharField()
#     vendor_rejection_reason = serializers.CharField(allow_blank=True)
#     current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
#     revenue_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
#     revenue_last_month = serializers.DecimalField(max_digits=12, decimal_places=2)
#     revenue_trend_pct = serializers.FloatField()
#     orders_this_month = serializers.IntegerField()
#     orders_last_month = serializers.IntegerField()
#     orders_trend_pct = serializers.FloatField()
#     weekly_order_bars = serializers.ListField(child=serializers.IntegerField())
#     range_label = serializers.CharField()
#     # Reuses the exact serializer the Bookings list/detail screens
#     # already use — same fields, same available_next_statuses for
#     # quick-action buttons, so the frontend can reuse BookingListItem
#     # directly instead of a new component.
#     bookings_to_start = VendorBookingListSerializer(many=True)
#     bookings_to_return = VendorBookingListSerializer(many=True)
#     fleet_total_listings = serializers.IntegerField()
#     fleet_pending_approval = serializers.IntegerField()
#     fleet_blocked_units = serializers.IntegerField()
#     recent_bookings = VendorBookingListSerializer(many=True)


# class AdminVendorListSerializer(serializers.ModelSerializer):
#     status_label = serializers.CharField(source="get_status_display")

#     class Meta:
#         model = Vendor
#         fields = [
#             "id",
#             "business_name",
#             "owner_name",
#             "email",
#             "phone_number",
#             "gst_number",
#             "status",
#             "status_label",
#             "created_at",
#         ]


# class AdminVendorSubscriptionSummarySerializer(serializers.Serializer):
#     id = serializers.IntegerField()
#     plan_name = serializers.CharField(source="plan.name")
#     status = serializers.CharField()
#     started_at = serializers.DateTimeField(allow_null=True)
#     expires_at = serializers.DateTimeField(allow_null=True)


# class AdminVendorDetailSerializer(serializers.ModelSerializer):
#     status_label = serializers.CharField(source="get_status_display")
#     reviewed_by_name = serializers.SerializerMethodField()
#     suspended_by_name = serializers.SerializerMethodField()
#     banned_by_name = serializers.SerializerMethodField()
#     current_subscription = serializers.SerializerMethodField()

#     class Meta:
#         model = Vendor
#         fields = [
#             "id",
#             "business_name",
#             "owner_name",
#             "email",
#             "phone_number",
#             "address",
#             "gst_number",
#             "logo_image",
#             "status",
#             "status_label",
#             "rejection_reason",
#             "reviewed_by_name",
#             "reviewed_at",
#             "suspended_by_name",
#             "suspended_at",
#             "suspension_reason",
#             "banned_by_name",
#             "banned_at",
#             "ban_reason",
#             "current_subscription",
#             "created_at",
#         ]

#     def get_reviewed_by_name(self, obj):
#         return obj.reviewed_by.get_full_name() if obj.reviewed_by else None

#     def get_suspended_by_name(self, obj):
#         return obj.suspended_by.get_full_name() if obj.suspended_by else None

#     def get_banned_by_name(self, obj):
#         return obj.banned_by.get_full_name() if obj.banned_by else None

#     def get_current_subscription(self, obj):
#         sub = (
#             VendorSubscription.objects.filter(vendor=obj, is_current=True)
#             .select_related("plan")
#             .first()
#         )
#         if sub is None:
#             return None
#         return AdminVendorSubscriptionSummarySerializer(sub).data


# class AdminVendorStatusUpdateSerializer(serializers.Serializer):
#     status = serializers.ChoiceField(choices=Vendor.Status.choices)
#     reason = serializers.CharField(required=False, allow_blank=True, default="")


# class AdminVendorDocumentSerializer(serializers.ModelSerializer):
#     status_label = serializers.CharField(source="get_status_display")
#     doc_type_label = serializers.CharField(source="get_doc_type_display")
#     reviewed_by_name = serializers.SerializerMethodField()

#     class Meta:
#         model = VendorDocument
#         fields = [
#             "id",
#             "doc_type",
#             "doc_type_label",
#             "file",
#             "original_filename",
#             "status",
#             "status_label",
#             "rejection_reason",
#             "reviewed_by_name",
#             "reviewed_at",
#             "is_active",
#             "created_at",
#         ]

#     def get_reviewed_by_name(self, obj):
#         return obj.reviewed_by.get_full_name() if obj.reviewed_by else None


# class AdminVendorDocumentUpdateSerializer(serializers.Serializer):
#     doc_type = serializers.ChoiceField(
#         choices=VendorDocument.DocType.choices, required=False
#     )
#     file = serializers.FileField(required=False)


# class AdminDocumentReviewSerializer(serializers.Serializer):
#     status = serializers.ChoiceField(
#         choices=[("VERIFIED", "Verified"), ("REJECTED", "Rejected")]
#     )
#     rejection_reason = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )


# class AdminBankAccountSerializer(serializers.ModelSerializer):
#     status_label = serializers.CharField(source="get_status_display")
#     verified_by_name = serializers.SerializerMethodField()
#     account_number_masked = serializers.SerializerMethodField()

#     class Meta:
#         model = BankAccount
#         fields = [
#             "id",
#             "account_holder_name",
#             "account_number_masked",
#             "ifsc_code",
#             "bank_name",
#             "branch_name",
#             "status",
#             "status_label",
#             "is_active_acc",
#             "rejection_reason",
#             "verified_by_name",
#             "verified_at",
#             "is_active",
#             "submitted_at",
#         ]

#     def get_verified_by_name(self, obj):
#         return obj.verified_by.get_full_name() if obj.verified_by else None

#     def get_account_number_masked(self, obj):
#         return obj.account_number


# class AdminBankAccountUpdateSerializer(serializers.Serializer):
#     account_holder_name = serializers.CharField(max_length=200, required=False)
#     account_number = serializers.CharField(max_length=50, required=False)
#     ifsc_code = serializers.CharField(max_length=11, required=False)
#     bank_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
#     branch_name = serializers.CharField(
#         max_length=200, required=False, allow_blank=True
#     )


# class AdminBankAccountReviewSerializer(serializers.Serializer):
#     status = serializers.ChoiceField(
#         choices=[("VERIFIED", "Verified"), ("REJECTED", "Rejected")]
#     )
#     rejection_reason = serializers.CharField(
#         required=False, allow_blank=True, default=""
#     )


# class AdminVendorCommissionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = VendorCommission
#         fields = ["id", "name", "commission_type", "flat_percentage", "description"]


# class AdminVendorSubscriptionSerializer(serializers.ModelSerializer):
#     plan_name = serializers.CharField(source="plan.name")
#     status_label = serializers.CharField(source="get_status_display")
#     assigned_by_name = serializers.SerializerMethodField()

#     class Meta:
#         model = VendorSubscription
#         fields = [
#             "id",
#             "plan",
#             "plan_name",
#             "status",
#             "status_label",
#             "started_at",
#             "expires_at",
#             "cancelled_at",
#             "cancellation_reason",
#             "is_current",
#             "is_manually_assigned",
#             "assigned_by_name",
#             "created_at",
#         ]

#     def get_assigned_by_name(self, obj):
#         return obj.assigned_by.get_full_name() if obj.assigned_by else None


# class AdminVendorSubscriptionAssignSerializer(serializers.Serializer):
#     plan_id = serializers.IntegerField()


# class AdminSubscriptionPlanSerializer(serializers.ModelSerializer):
#     commission_name = serializers.CharField(source="commission.name", read_only=True)

#     class Meta:
#         model = SubscriptionPlan
#         fields = [
#             "id",
#             "name",
#             "description",
#             "billing_cycle",
#             "price",
#             "commission",
#             "commission_name",
#             "max_listings",
#             "max_pickup_locations",
#             "max_images_per_listing",
#             "can_enable_partial_payment",
#             "can_access_analytics",
#             "can_respond_to_reviews",
#             "priority_listing",
#             "is_default",
#             "sort_order",
#         ]


# # class AdminVendorRegistrationSerializer(serializers.Serializer):
# #     phone_number = serializers.CharField(max_length=15)
# #     phone_country_code = serializers.CharField(max_length=5, default="+91")
# #     email = serializers.EmailField()
# #     password = serializers.CharField(min_length=8, write_only=True)
# #     business_name = serializers.CharField(max_length=200)
# #     owner_name = serializers.CharField(max_length=200)
# #     address = serializers.CharField()
# #     gst_number = serializers.CharField(
# #         max_length=20, required=False, allow_blank=True, default=""
# #     )


# class AdminVendorRegistrationSerializer(serializers.Serializer):
#     existing_user_id = serializers.IntegerField(required=False, allow_null=True)
#     phone_number = serializers.CharField(max_length=15)
#     phone_country_code = serializers.CharField(max_length=5, default="+91")
#     email = serializers.EmailField()
#     password = serializers.CharField(min_length=8, write_only=True)
#     business_name = serializers.CharField(max_length=200)
#     owner_name = serializers.CharField(max_length=200)
#     address = serializers.CharField()
#     gst_number = serializers.CharField(
#         max_length=20, required=False, allow_blank=True, default=""
#     )


# class AdminVendorTeamMemberSerializer(serializers.Serializer):
#     id = serializers.IntegerField()
#     user_id = serializers.IntegerField()
#     full_name = serializers.CharField()
#     phone_number = serializers.CharField()
#     email = serializers.CharField(allow_blank=True, allow_null=True)
#     added_at = serializers.DateTimeField()
#     added_by_name = serializers.CharField(allow_null=True)
#     is_active = serializers.BooleanField()


# class AdminVendorTeamMemberCreateSerializer(serializers.Serializer):
#     phone_number = serializers.CharField(max_length=15)
#     phone_country_code = serializers.CharField(max_length=5, default="+91")
#     email = serializers.EmailField()
#     password = serializers.CharField(min_length=8, write_only=True)
#     first_name = serializers.CharField(max_length=50)
#     last_name = serializers.CharField(
#         max_length=50, required=False, allow_blank=True, default=""
#     )


# class VendorDashboardStatusSerializer(serializers.Serializer):
#     vendor_status = serializers.CharField()
#     vendor_status_label = serializers.CharField()
#     vendor_rejection_reason = serializers.CharField(allow_blank=True)
#     current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)


# class VendorDashboardAttentionSerializer(serializers.Serializer):
#     bookings_to_start = VendorBookingListSerializer(many=True)
#     bookings_to_return = VendorBookingListSerializer(many=True)


# class VendorDashboardStatsSerializer(serializers.Serializer):
#     revenue_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
#     revenue_last_month = serializers.DecimalField(max_digits=12, decimal_places=2)
#     revenue_trend_pct = serializers.FloatField()
#     orders_this_month = serializers.IntegerField()
#     orders_last_month = serializers.IntegerField()
#     orders_trend_pct = serializers.FloatField()
#     weekly_order_bars = serializers.ListField(child=serializers.IntegerField())
#     range_label = serializers.CharField()


# class VendorDashboardFleetSerializer(serializers.Serializer):
#     fleet_total_listings = serializers.IntegerField()
#     fleet_pending_approval = serializers.IntegerField()
#     fleet_blocked_units = serializers.IntegerField()


# class VendorDashboardRecentBookingsSerializer(serializers.Serializer):
#     recent_bookings = VendorBookingListSerializer(many=True)


# class AdminVendorDocumentUploadSerializer(serializers.Serializer):
#     doc_type = serializers.ChoiceField(choices=VendorDocument.DocType.choices)
#     file = serializers.FileField()


# class AdminBankAccountCreateSerializer(serializers.Serializer):
#     account_holder_name = serializers.CharField(max_length=200)
#     account_number = serializers.CharField(max_length=50)
#     ifsc_code = serializers.CharField(max_length=11)
#     bank_name = serializers.CharField(
#         max_length=200, required=False, allow_blank=True, default=""
#     )
#     branch_name = serializers.CharField(
#         max_length=200, required=False, allow_blank=True, default=""
#     )


# class AdminVendorUpdateSerializer(serializers.Serializer):
#     business_name = serializers.CharField(max_length=200, required=False)
#     owner_name = serializers.CharField(max_length=200, required=False)
#     email = serializers.EmailField(required=False)
#     address = serializers.CharField(required=False)
#     gst_number = serializers.CharField(max_length=20, required=False, allow_blank=True)


# class VendorProfileSerializer(serializers.ModelSerializer):
#     """
#     Vendor-facing read of their own profile — GET /api/vendors/me/.
#     Same shape as AdminVendorDetailSerializer minus the internal
#     audit-trail fields (reviewed_by_name/reviewed_at, suspended_by_name,
#     banned_by_name) that only make sense to staff. Suspension/ban
#     *reasons* are kept, though — a vendor should be able to see why
#     their own account is restricted.
#     """

#     status_label = serializers.CharField(source="get_status_display")
#     current_subscription = serializers.SerializerMethodField()

#     class Meta:
#         model = Vendor
#         fields = [
#             "id",
#             "business_name",
#             "owner_name",
#             "email",
#             "phone_number",
#             "address",
#             "gst_number",
#             "logo_image",
#             "status",
#             "status_label",
#             "rejection_reason",
#             "suspension_reason",
#             "ban_reason",
#             "current_subscription",
#             "created_at",
#         ]

#     def get_current_subscription(self, obj):
#         sub = (
#             VendorSubscription.objects.filter(vendor=obj, is_current=True)
#             .select_related("plan")
#             .first()
#         )
#         if sub is None:
#             return None
#         return AdminVendorSubscriptionSummarySerializer(sub).data


# class VendorDocumentSerializer(serializers.ModelSerializer):
#     """
#     Vendor-facing read of their own KYC documents — GET/POST
#     /api/vendors/me/documents/. Same data as AdminVendorDocumentSerializer
#     minus reviewed_by_name and is_active, which are internal-only (a
#     vendor never sees a document an admin has deactivated on their
#     behalf — VendorSelfDocumentRepository already filters those out).
#     """

#     status_label = serializers.CharField(source="get_status_display")
#     doc_type_label = serializers.CharField(source="get_doc_type_display")

#     class Meta:
#         model = VendorDocument
#         fields = [
#             "id",
#             "doc_type",
#             "doc_type_label",
#             "file",
#             "original_filename",
#             "status",
#             "status_label",
#             "rejection_reason",
#             "reviewed_at",
#             "created_at",
#         ]


# class VendorBankAccountSerializer(serializers.ModelSerializer):
#     """
#     Vendor-facing read of their own bank accounts — GET/POST
#     /api/vendors/me/bank-accounts/. Same data as AdminBankAccountSerializer
#     minus verified_by_name and is_active, same reasoning as above.
#     """

#     status_label = serializers.CharField(source="get_status_display")
#     account_number_masked = serializers.SerializerMethodField()

#     class Meta:
#         model = BankAccount
#         fields = [
#             "id",
#             "account_holder_name",
#             "account_number_masked",
#             "ifsc_code",
#             "bank_name",
#             "branch_name",
#             "status",
#             "status_label",
#             "is_active_acc",
#             "rejection_reason",
#             "verified_at",
#             "submitted_at",
#         ]

#     def get_account_number_masked(self, obj):
#         return obj.account_number


# apps/vendors/serializers.py
from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from apps.bookings.serializers import VendorBookingListSerializer
from apps.vendors.models import (
    SubscriptionPlan,
    VendorSubscription,
    Vendor,
    VendorDocument,
    BankAccount,
    VendorCommission,
)

# KYC document upload constraints — shared by AdminVendorDocumentUploadSerializer
# (admin upload + vendor self-service /me/documents/, both admin- and
# vendor-facing endpoints funnel through this one serializer) and
# AdminVendorDocumentUpdateSerializer (admin file replacement). The
# frontend mirrors these same limits, but this is the source of truth.
DOCUMENT_FILE_EXTENSION_VALIDATOR = FileExtensionValidator(
    allowed_extensions=["pdf", "png", "jpg", "jpeg"]
)
DOCUMENT_FILE_MAX_BYTES = 50 * 1024 * 1024  # 50MB


def validate_document_file_size(file):
    if file.size > DOCUMENT_FILE_MAX_BYTES:
        raise serializers.ValidationError("File must be 50MB or smaller.")


class VendorTermsSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()
    version = serializers.IntegerField()
    terms_items = serializers.ListField(child=serializers.CharField(), default=list)
    security_deposit_note = serializers.CharField(allow_blank=True)
    operating_hours_note = serializers.CharField(allow_blank=True)
    distance_limit_note = serializers.CharField(allow_blank=True)
    excess_charge_note = serializers.CharField(allow_blank=True)
    late_penalty_note = serializers.CharField(allow_blank=True)


class VendorTermsUpdateSerializer(serializers.Serializer):
    terms_items = serializers.ListField(
        child=serializers.CharField(allow_blank=False), required=False, default=list
    )
    security_deposit_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    operating_hours_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    distance_limit_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    excess_charge_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    late_penalty_note = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class VendorDashboardSerializer(serializers.Serializer):
    vendor_status = serializers.CharField()
    vendor_status_label = serializers.CharField()
    vendor_rejection_reason = serializers.CharField(allow_blank=True)
    current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_trend_pct = serializers.FloatField()
    orders_this_month = serializers.IntegerField()
    orders_last_month = serializers.IntegerField()
    orders_trend_pct = serializers.FloatField()
    weekly_order_bars = serializers.ListField(child=serializers.IntegerField())
    range_label = serializers.CharField()
    # Reuses the exact serializer the Bookings list/detail screens
    # already use — same fields, same available_next_statuses for
    # quick-action buttons, so the frontend can reuse BookingListItem
    # directly instead of a new component.
    bookings_to_start = VendorBookingListSerializer(many=True)
    bookings_to_return = VendorBookingListSerializer(many=True)
    fleet_total_listings = serializers.IntegerField()
    fleet_pending_approval = serializers.IntegerField()
    fleet_blocked_units = serializers.IntegerField()
    recent_bookings = VendorBookingListSerializer(many=True)


class AdminVendorListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")

    class Meta:
        model = Vendor
        fields = [
            "id",
            "business_name",
            "owner_name",
            "email",
            "phone_number",
            "gst_number",
            "status",
            "status_label",
            "created_at",
        ]


class AdminVendorSubscriptionSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    plan_name = serializers.CharField(source="plan.name")
    status = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)


class AdminVendorDetailSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    reviewed_by_name = serializers.SerializerMethodField()
    suspended_by_name = serializers.SerializerMethodField()
    banned_by_name = serializers.SerializerMethodField()
    current_subscription = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "id",
            "business_name",
            "owner_name",
            "email",
            "phone_number",
            "address",
            "gst_number",
            "logo_image",
            "status",
            "status_label",
            "rejection_reason",
            "reviewed_by_name",
            "reviewed_at",
            "suspended_by_name",
            "suspended_at",
            "suspension_reason",
            "banned_by_name",
            "banned_at",
            "ban_reason",
            "current_subscription",
            "created_at",
        ]

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else None

    def get_suspended_by_name(self, obj):
        return obj.suspended_by.get_full_name() if obj.suspended_by else None

    def get_banned_by_name(self, obj):
        return obj.banned_by.get_full_name() if obj.banned_by else None

    def get_current_subscription(self, obj):
        sub = (
            VendorSubscription.objects.filter(vendor=obj, is_current=True)
            .select_related("plan")
            .first()
        )
        if sub is None:
            return None
        return AdminVendorSubscriptionSummarySerializer(sub).data


class VendorProfileSerializer(serializers.ModelSerializer):
    """
    Vendor-facing read of their own profile — GET /api/vendors/me/.
    Same shape as AdminVendorDetailSerializer minus the internal
    audit-trail fields (reviewed_by_name/reviewed_at, suspended_by_name,
    banned_by_name) that only make sense to staff. Suspension/ban
    *reasons* are kept, though — a vendor should be able to see why
    their own account is restricted.
    """

    status_label = serializers.CharField(source="get_status_display")
    current_subscription = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "id",
            "business_name",
            "owner_name",
            "email",
            "phone_number",
            "address",
            "gst_number",
            "logo_image",
            "status",
            "status_label",
            "rejection_reason",
            "suspension_reason",
            "ban_reason",
            "current_subscription",
            "created_at",
        ]

    def get_current_subscription(self, obj):
        sub = (
            VendorSubscription.objects.filter(vendor=obj, is_current=True)
            .select_related("plan")
            .first()
        )
        if sub is None:
            return None
        return AdminVendorSubscriptionSummarySerializer(sub).data


class VendorDocumentSerializer(serializers.ModelSerializer):
    """
    Vendor-facing read of their own KYC documents — GET/POST
    /api/vendors/me/documents/. Same data as AdminVendorDocumentSerializer
    minus reviewed_by_name and is_active, which are internal-only (a
    vendor never sees a document an admin has deactivated on their
    behalf — VendorSelfDocumentRepository already filters those out).
    """

    status_label = serializers.CharField(source="get_status_display")
    doc_type_label = serializers.CharField(source="get_doc_type_display")

    class Meta:
        model = VendorDocument
        fields = [
            "id",
            "doc_type",
            "doc_type_label",
            "file",
            "original_filename",
            "status",
            "status_label",
            "rejection_reason",
            "reviewed_at",
            "created_at",
        ]


class VendorBankAccountSerializer(serializers.ModelSerializer):
    """
    Vendor-facing read of their own bank accounts — GET/POST
    /api/vendors/me/bank-accounts/. Same data as AdminBankAccountSerializer
    minus verified_by_name and is_active, same reasoning as above.
    """

    status_label = serializers.CharField(source="get_status_display")
    account_number_masked = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_holder_name",
            "account_number_masked",
            "ifsc_code",
            "bank_name",
            "branch_name",
            "status",
            "status_label",
            "is_active_acc",
            "rejection_reason",
            "verified_at",
            "submitted_at",
        ]

    def get_account_number_masked(self, obj):
        return obj.account_number


class AdminVendorStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Vendor.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdminVendorDocumentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    doc_type_label = serializers.CharField(source="get_doc_type_display")
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VendorDocument
        fields = [
            "id",
            "doc_type",
            "doc_type_label",
            "file",
            "original_filename",
            "status",
            "status_label",
            "rejection_reason",
            "reviewed_by_name",
            "reviewed_at",
            "is_active",
            "created_at",
        ]

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else None


class AdminVendorDocumentUpdateSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(
        choices=VendorDocument.DocType.choices, required=False
    )
    file = serializers.FileField(
        required=False,
        validators=[
            DOCUMENT_FILE_EXTENSION_VALIDATOR,
            validate_document_file_size,
        ],
    )


class AdminDocumentReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[("VERIFIED", "Verified"), ("REJECTED", "Rejected")]
    )
    rejection_reason = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class AdminBankAccountSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display")
    verified_by_name = serializers.SerializerMethodField()
    account_number_masked = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_holder_name",
            "account_number_masked",
            "ifsc_code",
            "bank_name",
            "branch_name",
            "status",
            "status_label",
            "is_active_acc",
            "rejection_reason",
            "verified_by_name",
            "verified_at",
            "is_active",
            "submitted_at",
        ]

    def get_verified_by_name(self, obj):
        return obj.verified_by.get_full_name() if obj.verified_by else None

    def get_account_number_masked(self, obj):
        return obj.account_number


class AdminBankAccountUpdateSerializer(serializers.Serializer):
    account_holder_name = serializers.CharField(max_length=200, required=False)
    account_number = serializers.CharField(max_length=50, required=False)
    ifsc_code = serializers.CharField(max_length=11, required=False)
    bank_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    branch_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )


class AdminBankAccountReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[("VERIFIED", "Verified"), ("REJECTED", "Rejected")]
    )
    rejection_reason = serializers.CharField(
        required=False, allow_blank=True, default=""
    )


class AdminVendorCommissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorCommission
        fields = ["id", "name", "commission_type", "flat_percentage", "description"]


class AdminVendorSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name")
    status_label = serializers.CharField(source="get_status_display")
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VendorSubscription
        fields = [
            "id",
            "plan",
            "plan_name",
            "status",
            "status_label",
            "started_at",
            "expires_at",
            "cancelled_at",
            "cancellation_reason",
            "is_current",
            "is_manually_assigned",
            "assigned_by_name",
            "created_at",
        ]

    def get_assigned_by_name(self, obj):
        return obj.assigned_by.get_full_name() if obj.assigned_by else None


class AdminVendorSubscriptionAssignSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()


class AdminSubscriptionPlanSerializer(serializers.ModelSerializer):
    commission_name = serializers.CharField(source="commission.name", read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "billing_cycle",
            "price",
            "commission",
            "commission_name",
            "max_listings",
            "max_pickup_locations",
            "max_images_per_listing",
            "can_enable_partial_payment",
            "can_access_analytics",
            "can_respond_to_reviews",
            "priority_listing",
            "is_default",
            "sort_order",
        ]


class AdminVendorRegistrationSerializer(serializers.Serializer):
    existing_user_id = serializers.IntegerField(required=False, allow_null=True)
    phone_number = serializers.CharField(max_length=15)
    phone_country_code = serializers.CharField(max_length=5, default="+91")
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    business_name = serializers.CharField(max_length=200)
    owner_name = serializers.CharField(max_length=200)
    address = serializers.CharField()
    gst_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )


class AdminVendorTeamMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    email = serializers.CharField(allow_blank=True, allow_null=True)
    added_at = serializers.DateTimeField()
    added_by_name = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()


class AdminVendorTeamMemberCreateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    phone_country_code = serializers.CharField(max_length=5, default="+91")
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )


class VendorDashboardStatusSerializer(serializers.Serializer):
    vendor_status = serializers.CharField()
    vendor_status_label = serializers.CharField()
    vendor_rejection_reason = serializers.CharField(allow_blank=True)
    current_balance = serializers.DecimalField(max_digits=12, decimal_places=2)


class VendorDashboardAttentionSerializer(serializers.Serializer):
    bookings_to_start = VendorBookingListSerializer(many=True)
    bookings_to_return = VendorBookingListSerializer(many=True)


class VendorDashboardStatsSerializer(serializers.Serializer):
    revenue_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_trend_pct = serializers.FloatField()
    orders_this_month = serializers.IntegerField()
    orders_last_month = serializers.IntegerField()
    orders_trend_pct = serializers.FloatField()
    weekly_order_bars = serializers.ListField(child=serializers.IntegerField())
    range_label = serializers.CharField()


class VendorDashboardFleetSerializer(serializers.Serializer):
    fleet_total_listings = serializers.IntegerField()
    fleet_pending_approval = serializers.IntegerField()
    fleet_blocked_units = serializers.IntegerField()


class VendorDashboardRecentBookingsSerializer(serializers.Serializer):
    recent_bookings = VendorBookingListSerializer(many=True)


class AdminVendorDocumentUploadSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=VendorDocument.DocType.choices)
    file = serializers.FileField(
        validators=[
            DOCUMENT_FILE_EXTENSION_VALIDATOR,
            validate_document_file_size,
        ],
    )


class AdminBankAccountCreateSerializer(serializers.Serializer):
    account_holder_name = serializers.CharField(max_length=200)
    account_number = serializers.CharField(max_length=50)
    ifsc_code = serializers.CharField(max_length=11)
    bank_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    branch_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )


class AdminVendorUpdateSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=200, required=False)
    owner_name = serializers.CharField(max_length=200, required=False)
    email = serializers.EmailField(required=False)
    address = serializers.CharField(required=False)
    gst_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
