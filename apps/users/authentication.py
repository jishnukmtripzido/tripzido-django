from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class VendorAwareJWTAuthentication(JWTAuthentication):
    """
    Identical to the default JWTAuthentication, but additionally
    re-checks — on EVERY authenticated request, not just at login —
    whether a VENDOR-role user's underlying Vendor record is still in
    good standing.

    A JWT's signature/expiry alone can't reflect a status change that
    happened AFTER the token was issued — that's the whole point of a
    stateless token. This is the standard fix for "revoke access
    immediately even though the token is technically still valid":
    re-check live DB state on every request instead of trusting the
    token alone.

    Deliberately checks user.get_vendor_profile() rather than
    user.vendor_profile directly — that resolves BOTH the owner AND
    any team member back to the same underlying Vendor record, so
    suspending the business correctly locks out every team member
    too, not just the owner account.

    Non-vendor users (customers, staff) are completely unaffected —
    get_vendor_profile() returns None for them, so this check is
    skipped entirely and behavior is identical to the stock class.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        vendor = user.get_vendor_profile()
        if vendor is not None and vendor.status != vendor.Status.APPROVED:
            raise AuthenticationFailed(
                "This vendor account is no longer active.",
                code="vendor_inactive",
            )

        return user
