"""
models.py

Defines the core identity, role, and permission models for the platform.

Models:
    - Role: Defines system or custom roles with data-access scope.
    - Permission: Fine-grained action-level permissions assigned to roles.
    - RolePermission: M2M join between Role and Permission with grant/deny flag.
    - User: Unified user model for all platform actors (Customer, Vendor, Admin).
    - UserRoleAssignment: Associates a user with a role and optional scope context.
"""

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.base_user import BaseUserManager


from django.db import models
from apps.core.models import BaseModel
from apps.locations.models import City
from django.contrib.auth.models import PermissionsMixin



class Role(BaseModel):
    """
    Represents a platform role, either a built-in system role or a custom one.

    Roles carry a ``data_scope`` that controls how broadly a role-holder can
    query platform data (e.g. platform-wide vs. only their own records).

    Attributes:
        system_role (str | None): One of the predefined ``SystemRole`` choices.
            Unique and nullable — only set for built-in roles.
        custom_name (str | None): Human-readable label for non-system roles.
        description (str): Optional free-text description.
        is_system (bool): ``True`` for roles created by migrations/fixtures,
            not editable by end-users.
        data_scope (str): Controls the breadth of data access (see
            ``DataScope`` choices).
    """

    class SystemRole(models.TextChoices):
        """Enumeration of built-in system-level roles."""

        CUSTOMER = "CUSTOMER", "Customer"
        VENDOR = "VENDOR", "Vendor"
        SUPPORT = "SUPPORT", "Support"
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"

    class DataScope(models.TextChoices):
        """Enumeration of data-visibility scopes attached to a role."""

        PLATFORM_WIDE = "PLATFORM_WIDE", "All data across platform"
        CITY_SCOPED = "CITY_SCOPED", "Only assigned cities"
        VENDOR_SCOPED = "VENDOR_SCOPED", "Only own vendor data"
        SELF = "SELF", "Only own user data"

    system_role = models.CharField(
        max_length=50,
        choices=SystemRole.choices,
        null=True,
        blank=True,
        unique=True,
    )
    custom_name = models.CharField(max_length=100, null=True, blank=True, unique=True)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)

    data_scope = models.CharField(
        max_length=20,
        choices=DataScope.choices,
        default=DataScope.SELF,
    )

    def __str__(self) -> str:
        """Return a human-readable representation of the role."""
        return f"{self.custom_name} [{self.data_scope}]"


class Permission(BaseModel):
    """
    Represents a fine-grained platform permission.

    Examples: ``can_initiate_payout``, ``can_manage_customers``,
    ``can_moderate_reviews``.

    Permissions are assigned to :class:`Role` instances; roles are then
    assigned to users via :class:`UserRoleAssignment`.

    Attributes:
        codename (str): Unique machine-readable identifier
            (e.g. ``"can_initiate_payout"``).
        name (str): Human-readable label.
        description (str): Optional explanation of what the permission allows.
        is_vendor_permission (bool): ``True`` when the permission is only
            meaningful for vendor-type users.
    """

    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_vendor_permission = models.BooleanField(
        default=False,
        help_text="True if this permission is relevant for vendor users",
    )

    def __str__(self) -> str:
        """Return the codename as the string representation."""
        return self.codename


class RolePermission(BaseModel):
    """
    M2M join table between :class:`Role` and :class:`Permission`.

    Supports an explicit grant/deny flag so that a permission can be
    explicitly *denied* on a role (overrides inherited grants in custom
    permission-checking logic).

    Attributes:
        role (Role): The role being configured.
        permission (Permission): The permission being attached.
        is_granted (bool): ``True`` to grant the permission, ``False`` to
            explicitly deny it.
    """

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    is_granted = models.BooleanField(default=True)

    class Meta:  # pylint: disable=too-few-public-methods
        """Enforce that each (role, permission) pair is unique."""

        unique_together = ("role", "permission")

    def __str__(self) -> str:
        """Return a readable grant/deny summary for this mapping."""
        granted_symbol = "✓" if self.is_granted else "✗"
        return f"{self.role} → {self.permission} ({granted_symbol})"
    

class UserManager(BaseUserManager):

    # def create_user(self, phone_number, **extra_fields):
    #     user = self.model(phone_number=phone_number, **extra_fields)
    #     user.set_unusable_password()   # OTP users → no password
    #     user.save(using=self._db)
    #     return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        if not password:
            raise ValueError("Superuser must have a password")  # enforce it
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_active", True)
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)    # superuser → real password
        user.save(using=self._db)
        return user
    
    def get_queryset(self):
        """Return a queryset filtered to only include active (non-soft-deleted) objects."""
        return super().get_queryset().filter(is_active=True)


class User(AbstractBaseUser,PermissionsMixin, BaseModel):
    """
    Unified user model for all platform actors: Customer, Vendor, and Admin.

    Phone number is the primary identifier — there is no username or
    email-based login.  The user's :class:`Role` (assigned via
    :class:`UserRoleAssignment`) determines their capabilities.

    Attributes:
        phone_number (str): Primary identifier; unique and indexed.
        first_name (str): Optional given name.
        last_name (str): Optional family name.
        email (str | None): Optional e-mail address.
        status (str): Current account lifecycle state (see
            :class:`AccountStatus`).
        address (str): Optional postal/delivery address.
        suspended_at (datetime | None): Timestamp of the most recent
            suspension event.
        suspension_reason (str): Free-text explanation for the suspension.
        banned_at (datetime | None): Timestamp when the account was banned.
        ban_reason (str): Free-text explanation for the ban.
        deletion_requested_at (datetime | None): When the user requested
            account deletion (US-C22 / DPDP Act).
        is_anonymised (bool): ``True`` once PII has been scrubbed but the
            row is retained for legal/financial compliance.
        anonymised_at (datetime | None): Timestamp of anonymisation.
        is_phone_blocked (bool): ``True`` when the phone number must not be
            re-registered (post ban-then-delete edge case US-A09).
        is_staff (bool): Grants access to the Django admin site.
        is_active (bool): Controls whether the account can authenticate.
    """

    class AccountStatus(models.TextChoices):
        """Lifecycle states for a user account."""

        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        BANNED = "BANNED", "Banned"
        PENDING_DELETION = "PENDING_DELETION", "Pending Deletion"
        DELETED = "DELETED", "Deleted"

    phone_number = models.CharField(max_length=15, unique=True, db_index=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_index=True,
    )

    address = models.TextField(blank=True)

    # Timestamps for status changes
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)
    banned_at = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)

    # Soft-delete / DPDP Act compliance (US-C22 / US-A10)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    is_anonymised = models.BooleanField(default=False)
    anonymised_at = models.DateTimeField(null=True, blank=True)

    # Block re-registration after ban-then-delete (US-A09)
    is_phone_blocked = models.BooleanField(default=False)

    # Django auth hooks
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        """Return phone number and full name for display purposes."""
        return str(f"{self.phone_number} ({self.get_full_name()})")

    def get_full_name(self) -> str:
        """
        Return the user's full name, falling back to the phone number.
        """
        return f"{self.first_name} {self.last_name}".strip() or self.phone_number

    def get_short_name(self) -> str:
        """
        Return the user's first name.

        Required by Django's ``AbstractBaseUser`` contract.

        Returns:
            str: The value of ``first_name``, or ``phone_number`` if empty.
        """
        return self.first_name or self.phone_number

    def has_role(self, role_name: str) -> bool:
        """
        Check whether the user currently holds a role with the given name.

        Args:
            role_name (str): The ``custom_name`` of the role to check.

        Returns:
            bool: ``True`` if at least one active assignment exists for
                ``role_name``, ``False`` otherwise.
        """
        return self.role_assignments.filter(role__custom_name=role_name).exists()


class UserRoleAssignment(BaseModel):
    """
    Associates a :class:`User` with a :class:`Role` and captures the
    optional scope context for city- or vendor-scoped roles.

    This model replaces the simpler ``UserRole`` join table by adding
    ``assigned_cities`` and ``assigned_vendors`` M2M fields so that, for
    example, a city-scoped support agent's access can be restricted to
    specific cities.

    Attributes:
        user (User): The user receiving the role.
        role (Role): The role being assigned.
        assigned_cities (QuerySet[City]): Cities in scope when the role's
            ``data_scope`` is ``CITY_SCOPED``.
        assigned_vendors (QuerySet[Vendor]): Vendors in scope when the role's
            ``data_scope`` is ``VENDOR_SCOPED``.
        assigned_by (User | None): The admin user who created this assignment;
            set to ``NULL`` on deletion of the assigning user.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )

    # Only populated for CITY_SCOPED roles
    assigned_cities = models.ManyToManyField(
        City,
        blank=True,
        related_name="scoped_admins",
    )

    # Only populated for VENDOR_SCOPED roles
    # assigned_vendors = models.ManyToManyField(
    #     "vendor.Vendor",
    #     blank=True,
    #     related_name="scoped_agents",
    # )

    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="role_assignments_given",
    )

    class Meta:  
        """Ensure a user cannot be assigned the same role twice."""

        unique_together = ("user", "role")

    def __str__(self) -> str:
        """Return a readable summary of the user-to-role mapping."""
        return f"{self.user.phone_number if self.user else 'Unknown User'} → {self.role}"