import uuid
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValidationError(
            "Use a valid IANA time zone, such as Africa/Douala."
        ) from error


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    timezone = models.CharField(
        max_length=64, default="Africa/Douala", validators=[validate_timezone]
    )
    opens_at = models.TimeField(default=time(8))
    closes_at = models.TimeField(default=time(18))

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        MEMBER = "member", "Member"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"], name="one_membership_per_workspace"
            )
        ]


class Resource(models.Model):
    class Kind(models.TextChoices):
        ROOM = "room", "Meeting room"
        DESK = "desk", "Desk"
        STUDIO = "studio", "Studio"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="resources"
    )
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ROOM)
    capacity = models.PositiveSmallIntegerField(default=1)
    floor = models.CharField(max_length=50, default="Ground floor")
    description = models.CharField(max_length=300, blank=True)
    amenities = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"], name="unique_resource_name"
            ),
            models.CheckConstraint(
                condition=models.Q(capacity__gte=1), name="positive_resource_capacity"
            ),
        ]

    def __str__(self):
        return self.name


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="bookings"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    title = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    attendees = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    request_key = models.CharField(max_length=128, null=True, blank=True)
    request_fingerprint = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="booking_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(attendees__gte=1), name="positive_booking_attendees"
            ),
            models.UniqueConstraint(
                fields=["owner", "request_key"],
                condition=models.Q(request_key__isnull=False),
                name="unique_booking_request_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["resource", "status", "starts_at", "ends_at"],
                name="booking_conflict_lookup",
            )
        ]
