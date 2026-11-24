"""Booking writes share one resource lock; callers cannot skip conflict checks through the API."""

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import Booking, Resource


class Conflict(APIException):
    status_code = 409
    default_detail = (
        "This resource is already booked during that time. Choose another slot."
    )


def local_datetime(day, clock, zone_name):
    naive = datetime.combine(day, clock)
    zone = ZoneInfo(zone_name)
    aware = naive.replace(tzinfo=zone)
    if aware.astimezone(ZoneInfo("UTC")).astimezone(zone).replace(tzinfo=None) != naive:
        raise ValidationError(
            "That local time does not exist because the clocks change. Choose another time."
        )
    if (
        naive.replace(tzinfo=zone, fold=0).utcoffset()
        != naive.replace(tzinfo=zone, fold=1).utcoffset()
    ):
        raise ValidationError(
            "That local time is ambiguous because the clocks change. Choose another time."
        )
    return aware


def create_booking(
    *, owner, resource, date, start_time, end_time, title, attendees, request_key=None
):
    start = local_datetime(date, start_time, resource.workspace.timezone)
    end = local_datetime(date, end_time, resource.workspace.timezone)
    fingerprint = hashlib.sha256(
        json.dumps(
            [str(resource.id), start.isoformat(), end.isoformat(), title, attendees]
        ).encode()
    ).hexdigest()

    def replay():
        existing = (
            Booking.objects.filter(owner=owner, request_key=request_key).first()
            if request_key
            else None
        )
        if existing and existing.request_fingerprint != fingerprint:
            raise Conflict(
                "This Idempotency-Key was already used for a different booking."
            )
        return existing

    try:
        with transaction.atomic():
            resource = Resource.objects.select_for_update().get(pk=resource.pk)
            previous = replay()
            if previous:
                return previous, False
            if not resource.active:
                raise ValidationError(
                    {"resource": "This resource is not available for booking."}
                )
            if start < timezone.now():
                raise ValidationError({"start_time": "Choose a time in the future."})
            if end <= start:
                raise ValidationError(
                    {"end_time": "End time must be after start time on the same day."}
                )
            if (
                start_time < resource.workspace.opens_at
                or end_time > resource.workspace.closes_at
            ):
                raise ValidationError(
                    "Choose a time within the workspace opening hours."
                )
            if attendees > resource.capacity:
                raise ValidationError(
                    {
                        "attendees": f"This resource has capacity for {resource.capacity} people."
                    }
                )
            if Booking.objects.filter(
                resource=resource,
                status=Booking.Status.CONFIRMED,
                starts_at__lt=end,
                ends_at__gt=start,
            ).exists():
                raise Conflict()
            return Booking.objects.create(
                resource=resource,
                owner=owner,
                starts_at=start,
                ends_at=end,
                title=title,
                attendees=attendees,
                request_key=request_key,
                request_fingerprint=fingerprint,
            ), True
    except IntegrityError:
        previous = replay()
        if previous:
            return previous, False
        raise


@transaction.atomic
def cancel_booking(booking):
    # Same lock order as creation prevents a cancel/create race on the same room.
    Resource.objects.select_for_update().get(pk=booking.resource_id)
    booking = Booking.objects.select_for_update().get(pk=booking.pk)
    if booking.status != Booking.Status.CANCELLED:
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["status", "cancelled_at"])
    return booking
