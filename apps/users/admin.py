from django.contrib import admin

from apps.core.admin import SoftDeleteAdmin
from apps.users.models import Role, Permission, RolePermission, User, UserRoleAssignment


@admin.register(Role)
class RoleAdmin(SoftDeleteAdmin):
    list_display = ("system_role", "custom_name", "data_scope", "is_system", "is_deleted_display")
    list_filter = ("is_system", "data_scope")
    search_fields = ("system_role", "custom_name", "description")
    readonly_fields = ("is_deleted_display",)


@admin.register(Permission)
class PermissionAdmin(SoftDeleteAdmin):
    list_display = ("codename", "name", "is_vendor_permission", "is_deleted_display")
    list_filter = ("is_vendor_permission",)
    search_fields = ("codename", "name", "description")
    readonly_fields = ("is_deleted_display",)


@admin.register(RolePermission)
class RolePermissionAdmin(SoftDeleteAdmin):
    list_display = ("role", "permission", "is_granted", "is_deleted_display")
    list_filter = ("is_granted",)
    search_fields = ("role__custom_name", "permission__codename")
    readonly_fields = ("is_deleted_display",)


@admin.register(User)
class UserAdmin(SoftDeleteAdmin):
    list_display = ("phone_number", "first_name", "last_name", "email", "status", "is_staff", "is_deleted_display")
    list_filter = ("status", "is_staff", "is_anonymised", "is_phone_blocked")
    search_fields = ("phone_number", "first_name", "last_name", "email")
    readonly_fields = ("is_deleted_display",)


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(SoftDeleteAdmin):
    list_display = ("user", "role", "assigned_by", "is_deleted_display")
    list_filter = ("role",)
    search_fields = ("user__phone_number", "role__custom_name")
    readonly_fields = ("is_deleted_display",)
    filter_horizontal = ("assigned_cities",)
