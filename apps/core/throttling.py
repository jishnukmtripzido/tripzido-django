from rest_framework.permissions import SAFE_METHODS
from rest_framework.settings import api_settings
from rest_framework.throttling import UserRateThrottle


class UploadRateThrottle(UserRateThrottle):
    """
    Per-user cap on file uploads ("upload" rate in settings). Only
    writes count — the same views also serve GET (e.g. listing a
    vendor's documents), and browsing shouldn't eat the upload quota.
    """

    scope = "upload"

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)


# For views that need the upload cap on top of the global defaults —
# setting throttle_classes on a view replaces the defaults otherwise.
UPLOAD_THROTTLE_CLASSES = [*api_settings.DEFAULT_THROTTLE_CLASSES, UploadRateThrottle]
