from rest_framework import serializers
from rest_framework import serializers
from apps.users.models import User


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
