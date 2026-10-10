from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_storage():
    """
    Storage for files that must not be publicly served (see
    settings.PRIVATE_MEDIA_ROOT). These files have no public URL, so
    never use `.url` on them (Django would fall back to MEDIA_URL and
    produce a dead link) — links go through a signed download endpoint
    instead.

    A callable rather than an instance so the path isn't baked into
    migrations.
    """
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
