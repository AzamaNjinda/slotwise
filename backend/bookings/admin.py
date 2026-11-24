from django.contrib import admin

from .models import Booking, Membership, Resource, Workspace

admin.site.register([Workspace, Membership, Resource])


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # Writes belong to the conflict-checked service. Admin is an audit view.
    list_display = ["title", "resource", "owner", "starts_at", "ends_at", "status"]
    list_filter = ["status", "resource__workspace"]
    readonly_fields = [field.name for field in Booking._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
