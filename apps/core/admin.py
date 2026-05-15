from django.contrib import admin
from django.utils.html import format_html


class SoftDeleteAdmin(admin.ModelAdmin):
    """Base admin class for all models with soft delete"""
    
    def get_queryset(self, request):
        return self.model.all_objects.all()

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete(deleted_by=request.user)

    def is_deleted_display(self, obj):
        if obj.is_deleted:
            return format_html('<span style="color:red;">🗑 Deleted</span>')
        return format_html('<span style="color:green;">✔ Active</span>')
    
    is_deleted_display.short_description = 'Status'