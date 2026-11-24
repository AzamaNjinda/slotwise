from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from bookings.models import Booking, Resource, Workspace
from bookings.services import Conflict, create_booking


@skipUnless(
    connection.vendor == "postgresql",
    "Concurrency guarantees require PostgreSQL row locks; CI runs this test against PostgreSQL.",
)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def test_only_one_of_two_simultaneous_overlapping_requests_succeeds(self):
        user = get_user_model().objects.create_user("concurrent-user")
        workspace = Workspace.objects.create(name="Concurrency test")
        room = Resource.objects.create(
            workspace=workspace, name="Only room", capacity=4
        )
        barrier = Barrier(2)

        def attempt():
            close_old_connections()
            try:
                local_user = get_user_model().objects.get(pk=user.pk)
                local_room = Resource.objects.select_related("workspace").get(
                    pk=room.pk
                )
                barrier.wait(timeout=10)
                try:
                    create_booking(
                        owner=local_user,
                        resource=local_room,
                        date=timezone.now().date() + timedelta(days=2),
                        start_time=time(9),
                        end_time=time(10),
                        title="Contested slot",
                        attendees=2,
                    )
                    return 201
                except Conflict:
                    return 409
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(outcomes), [201, 409])
        self.assertEqual(Booking.objects.count(), 1)
