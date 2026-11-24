"""Explicit, repeatable, development-only data; never creates staff users."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from bookings.models import Booking, Membership, Resource, Workspace


class Command(BaseCommand):
    help = "Create fictional local demo data. Refuses to run when DEBUG=false."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            required=True,
            help="Password for newly created demo users; existing passwords are never reset.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding is only available with DEBUG=true.")
        password = options["password"]
        if len(password) < 12:
            raise CommandError("Choose a demo password with at least 12 characters.")
        workspace, _ = Workspace.objects.get_or_create(
            name="Northstar Workspace", defaults={"timezone": "Africa/Douala"}
        )
        users = []
        for username, name, role in [
            ("manager@example.invalid", "Alex", "manager"),
            ("member@example.invalid", "Sam", "member"),
        ]:
            user, created = get_user_model().objects.get_or_create(
                username=username,
                defaults={"email": username, "first_name": name, "last_name": "Demo"},
            )
            if created:
                user.set_password(password)
                user.save()
            Membership.objects.get_or_create(
                workspace=workspace, user=user, defaults={"role": role}
            )
            users.append(user)
        definitions = [
            (
                "The Atelier",
                "room",
                6,
                "Ground floor",
                "A bright room for thoughtful conversations and your next big idea.",
                ["Wi-Fi", "Display", "Whiteboard"],
            ),
            (
                "Focus Pod",
                "desk",
                1,
                "First floor",
                "A quiet corner to get into the flow, one task at a time.",
                ["Wi-Fi", "Quiet zone"],
            ),
            (
                "Boardroom",
                "room",
                10,
                "First floor",
                "Bring everyone together, in the room or on the screen.",
                ["Display", "Video calls", "Whiteboard"],
            ),
            (
                "Studio B",
                "studio",
                4,
                "Ground floor",
                "A flexible space for creating, recording, and making things happen.",
                ["Wi-Fi", "Natural light"],
            ),
            (
                "Window Desk",
                "desk",
                1,
                "Ground floor",
                "A dedicated desk with daylight and a little breathing room.",
                ["Wi-Fi", "Natural light"],
            ),
            (
                "Project Hub",
                "room",
                4,
                "First floor",
                "A comfortable spot for small teams to plan their next move.",
                ["Wi-Fi", "Whiteboard"],
            ),
        ]
        spaces = []
        for name, kind, capacity, floor, description, amenities in definitions:
            resource, _ = Resource.objects.get_or_create(
                workspace=workspace,
                name=name,
                defaults={
                    "kind": kind,
                    "capacity": capacity,
                    "floor": floor,
                    "description": description,
                    "amenities": amenities,
                },
            )
            spaces.append(resource)
        zone = ZoneInfo(workspace.timezone)
        day = timezone.localdate(timezone=zone)
        samples = [
            (0, 1, "Design workshop", "09:00", "10:30", 4),
            (0, 0, "Client catch-up", "13:00", "14:00", 3),
            (2, 1, "Quarterly planning", "10:00", "11:30", 8),
            (4, 0, "Deep work", "09:00", "12:00", 1),
            (5, 1, "Product sync", "15:00", "16:00", 3),
        ]
        for resource_index, owner_index, title, start, end, attendees in samples:
            start = datetime.combine(day, time.fromisoformat(start), zone)
            end = datetime.combine(day, time.fromisoformat(end), zone)
            Booking.objects.get_or_create(
                resource=spaces[resource_index],
                owner=users[owner_index],
                title=title,
                starts_at=start,
                defaults={"ends_at": end, "attendees": attendees},
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Demo workspace ready. Users: manager@example.invalid and member@example.invalid. Existing passwords were preserved."
            )
        )
