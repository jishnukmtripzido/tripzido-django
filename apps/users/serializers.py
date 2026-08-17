from rest_framework import serializers
from apps.users.models import User, Role


class SendOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        required=True, help_text="Phone number to send OTP to, e.g. +919999999999"
    )
    turnstile_token = serializers.CharField(
        required=True,
        help_text="Turnstile token from Cloudflare Turnstile widget for bot protection",
    )


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        required=True, help_text="Phone number to verify OTP for, e.g. +919999999999"
    )
    otp = serializers.CharField(required=True, help_text="OTP to verify")


class ProfileSerializer(serializers.ModelSerializer):
    """
    Read-only representation of the logged-in user's profile, shaped to
    match BasicDetails.tsx directly — `name` is the combined display
    name (frontend has one "Name" field, not separate first/last
    inputs), and `mobile_number` is exposed as an explicit
    "always verified" field since phone is the auth identity and can't
    be edited from this page.
    """

    name = serializers.CharField(source="get_full_name", read_only=True)
    mobile_number = serializers.CharField(source="phone_number", read_only=True)
    mobile_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "first_name",
            "last_name",
            "email",
            "mobile_number",
            "mobile_verified",
            "address",
        ]

    def get_mobile_verified(self, user) -> bool:
        # Phone is the OTP-verified login identity for every user in
        # this model, so this is always true today. Kept as an explicit
        # field (rather than hardcoding true on the frontend) in case a
        # future unverified-number flow is introduced.
        return True


class ProfileUpdateSerializer(serializers.Serializer):
    """
    Validates a partial profile update. Accepts a single `name` field
    (matching the frontend's single Name input) and splits it into
    first_name/last_name on save — mirrors how `get_full_name()` joins
    them back together for reads.

    phone_number is intentionally not accepted here: it's the verified
    login identity and BasicDetails.tsx has no Edit affordance for it.
    """

    name = serializers.CharField(max_length=101, required=False, allow_blank=False)
    email = serializers.EmailField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "At least one of name, email, address must be provided."
            )
        return attrs

    def to_internal_fields(self) -> dict:
        """
        Converts validated_data into the {model_field: value} shape
        UserRepository.update_user_fields expects — splitting `name`
        into first_name/last_name.
        """
        data = dict(self.validated_data)
        fields = {}

        if "name" in data:
            name_parts = data.pop("name").strip().split(maxsplit=1)
            fields["first_name"] = name_parts[0] if name_parts else ""
            fields["last_name"] = name_parts[1] if len(name_parts) > 1 else ""

        fields.update(data)
        return fields


# ── Add these two serializers to your existing serializers.py ──────────────


class RegisterSendOTPSerializer(serializers.Serializer):
    """
    Validates the registration payload before creating the user and
    dispatching an OTP.

    Fields:
        phone_number    – required; the login identity (e.g. "+919876543210")
        first_name      – required
        last_name       – optional
        email           – optional, validated as e-mail format
        turnstile_token – required; Cloudflare Turnstile bot-check token
    """

    phone_number = serializers.CharField(
        required=True,
        help_text="Phone number including country code, e.g. +919999999999",
    )
    first_name = serializers.CharField(
        required=True,
        max_length=50,
        help_text="User's given name",
    )
    last_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=50,
        help_text="User's family name (optional)",
    )
    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional e-mail address",
    )
    turnstile_token = serializers.CharField(
        required=True,
        help_text="Cloudflare Turnstile widget token for bot protection",
    )


class RegisterVerifyOTPSerializer(serializers.Serializer):
    """
    Validates the OTP verification step for a registration flow.

    Fields:
        phone_number – the number that received the OTP
        otp          – the 4-digit code entered by the user
    """

    phone_number = serializers.CharField(
        required=True,
        help_text="Phone number used during registration",
    )
    otp = serializers.CharField(
        required=True,
        min_length=4,
        max_length=4,
        help_text="4-digit OTP sent via SMS",
    )


class StaffLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class AdminUserListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "full_name",
            "email",
            "status",
            "status_label",
            "created_at",
        ]


class AdminUserDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "phone_country_code",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "address",
            "status",
            "status_label",
            "suspended_at",
            "suspension_reason",
            "banned_at",
            "ban_reason",
            "is_phone_blocked",
            "created_at",
        ]


class AdminUserStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            (User.AccountStatus.ACTIVE, "Active"),
            (User.AccountStatus.SUSPENDED, "Suspended"),
            (User.AccountStatus.BANNED, "Banned"),
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdminStaffListItemSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    email = serializers.CharField(allow_blank=True, allow_null=True)
    role = serializers.CharField()
    role_label = serializers.CharField()
    assigned_at = serializers.DateTimeField(required=False)
    assigned_by_name = serializers.CharField(allow_null=True, required=False)


class AdminStaffCreateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    phone_country_code = serializers.CharField(max_length=5, default="+91")
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    role = serializers.ChoiceField(
        choices=[
            (Role.SystemRole.SUPPORT, "Support"),
            (Role.SystemRole.SUPER_ADMIN, "Super Admin"),
        ]
    )
