from rest_framework import serializers

from .models import Booking, Membership, Resource, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "timezone", "opens_at", "closes_at", "role"]

    def get_role(self, obj) -> str:
        return Membership.objects.get(
            workspace=obj, user=self.context["request"].user
        ).role


class ResourceSerializer(serializers.ModelSerializer):
    capacity = serializers.IntegerField(min_value=1, max_value=100)
    amenities = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[
                "Wi-Fi",
                "Display",
                "Whiteboard",
                "Video calls",
                "Natural light",
                "Quiet zone",
            ]
        ),
        max_length=6,
        required=False,
    )

    class Meta:
        model = Resource
        fields = [
            "id",
            "name",
            "kind",
            "capacity",
            "floor",
            "description",
            "amenities",
            "active",
        ]
        read_only_fields = ["id"]
        validators = []

    def validate_name(self, value):
        queryset = Resource.objects.filter(
            workspace=self.context["request"].workspace, name__iexact=value.strip()
        )
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A space with this name already exists in this workspace."
            )
        return value.strip()


class BookingSerializer(serializers.ModelSerializer):
    resource_name = serializers.CharField(source="resource.name", read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_id = serializers.IntegerField(read_only=True)
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "resource",
            "resource_name",
            "owner_id",
            "owner_name",
            "title",
            "starts_at",
            "ends_at",
            "attendees",
            "status",
            "created_at",
            "cancelled_at",
            "can_cancel",
        ]
        read_only_fields = fields

    def get_owner_name(self, obj) -> str:
        return obj.owner.get_full_name() or obj.owner.username

    def get_can_cancel(self, obj) -> bool:
        request = self.context["request"]
        return obj.status == Booking.Status.CONFIRMED and (
            obj.owner_id == request.user.id
            or request.membership.role == Membership.Role.MANAGER
        )


class CreateBookingSerializer(serializers.Serializer):
    resource = serializers.UUIDField()
    title = serializers.CharField(max_length=100, trim_whitespace=True)
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    attendees = serializers.IntegerField(min_value=1, max_value=100)


class SessionSerializer(serializers.Serializer):
    user = serializers.JSONField(allow_null=True)
    workspaces = WorkspaceSerializer(many=True)
