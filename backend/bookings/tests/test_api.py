from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import Booking, Membership, Resource, Workspace


class BookingApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.manager = get_user_model().objects.create_user(
            "manager", password="test-password-391"
        )
        self.member = get_user_model().objects.create_user(
            "member", password="test-password-392"
        )
        self.outsider = get_user_model().objects.create_user(
            "outsider", password="test-password-393"
        )
        self.workspace = Workspace.objects.create(name="Test team")
        self.other = Workspace.objects.create(name="Another team")
        Membership.objects.create(
            user=self.manager, workspace=self.workspace, role="manager"
        )
        Membership.objects.create(user=self.member, workspace=self.workspace)
        Membership.objects.create(
            user=self.outsider, workspace=self.other, role="manager"
        )
        self.room = Resource.objects.create(
            workspace=self.workspace, name="Meeting room", capacity=6
        )
        self.other_room = Resource.objects.create(
            workspace=self.other, name="Private room", capacity=6
        )
        self.day = timezone.localdate(timezone=ZoneInfo("Africa/Douala")) + timedelta(
            days=1
        )
        self.data = {
            "resource": str(self.room.id),
            "title": "Planning",
            "date": str(self.day),
            "start_time": "09:00",
            "end_time": "10:00",
            "attendees": 3,
        }
        self.client.force_authenticate(self.member)

    def book(self, **changes):
        return self.client.post("/api/bookings/", {**self.data, **changes})

    def test_authentication_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/resources/").status_code, 403)

    def test_other_workspaces_cannot_be_read_or_booked(self):
        self.assertEqual(
            self.client.get(f"/api/resources/?workspace={self.other.id}").status_code,
            403,
        )
        self.assertEqual(self.book(resource=str(self.other_room.id)).status_code, 404)
        self.assertEqual(len(self.client.get("/api/resources/").data), 1)

    def test_workspace_local_time_is_stored_in_utc(self):
        response = self.book()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Booking.objects.get().starts_at.hour, 8)

    def test_conflicting_slot_returns_409_and_adjacent_slot_is_allowed(self):
        self.assertEqual(self.book().status_code, 201)
        self.assertEqual(
            self.book(start_time="09:30", end_time="10:30").status_code, 409
        )
        self.assertEqual(
            self.book(start_time="10:00", end_time="11:00").status_code, 201
        )
        self.assertEqual(Booking.objects.count(), 2)

    def test_same_idempotency_key_replays_without_duplicate(self):
        first = self.client.post(
            "/api/bookings/", self.data, HTTP_IDEMPOTENCY_KEY="request-123"
        )
        replay = self.client.post(
            "/api/bookings/", self.data, HTTP_IDEMPOTENCY_KEY="request-123"
        )
        changed = self.client.post(
            "/api/bookings/",
            {**self.data, "title": "Other meeting"},
            HTTP_IDEMPOTENCY_KEY="request-123",
        )
        self.assertEqual(
            (first.status_code, replay.status_code, changed.status_code),
            (201, 200, 409),
        )
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(Booking.objects.count(), 1)

    def test_cancel_releases_slot_and_is_idempotent(self):
        booking_id = self.book().data["id"]
        for _ in range(2):
            self.assertEqual(
                self.client.post(f"/api/bookings/{booking_id}/cancel/").status_code, 200
            )
        self.assertEqual(self.book().status_code, 201)

    def test_members_cannot_cancel_another_members_booking(self):
        self.client.force_authenticate(self.manager)
        booking_id = self.book().data["id"]
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.post(f"/api/bookings/{booking_id}/cancel/").status_code, 403
        )

    def test_manager_can_cancel_team_booking(self):
        booking_id = self.book().data["id"]
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.post(f"/api/bookings/{booking_id}/cancel/").status_code, 200
        )

    def test_unrelated_manager_cannot_cancel_booking(self):
        booking_id = self.book().data["id"]
        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.post(f"/api/bookings/{booking_id}/cancel/").status_code, 404
        )

    def test_capacity_time_order_and_opening_hours_are_enforced(self):
        for changes in [
            {"attendees": 7},
            {"attendees": 0},
            {"end_time": "08:00"},
            {"start_time": "07:00"},
            {"end_time": "19:00"},
            {"date": str(self.day - timedelta(days=3))},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(self.book(**changes).status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_resource_management_is_manager_only(self):
        payload = {"name": "New room", "capacity": 4, "kind": "room"}
        self.assertEqual(self.client.post("/api/resources/", payload).status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post("/api/resources/", payload).status_code, 201)

    def test_capacity_cannot_be_reduced_below_upcoming_booking(self):
        self.book()
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.patch(
                f"/api/resources/{self.room.id}/", {"capacity": 2}
            ).status_code,
            400,
        )

    def test_archived_resources_cannot_receive_new_bookings(self):
        self.room.active = False
        self.room.save()
        self.assertEqual(self.book().status_code, 400)

    def test_invalid_day_and_workspace_are_validation_errors(self):
        self.assertEqual(
            self.client.get("/api/bookings/?date=not-a-date").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/resources/?workspace=not-an-id").status_code, 400
        )


class LoginCsrfTests(TestCase):
    def test_login_requires_csrf_and_rotates_token(self):
        cache.clear()
        get_user_model().objects.create_user("demo", password="test-password-394")
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(
                "/api/login/",
                {"username": "demo", "password": "test-password-394"},
                content_type="application/json",
            ).status_code,
            403,
        )
        token = client.get("/api/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/login/",
            {"username": "demo", "password": "test-password-394"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["csrfToken"], token)
        self.assertEqual(client.get("/api/session/").json()["user"]["username"], "demo")
