from datetime import date, time

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from bookings.services import local_datetime


class WorkspaceTimeTests(SimpleTestCase):
    def test_dst_spring_gap_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "does not exist"):
            local_datetime(date(2027, 3, 14), time(2, 30), "America/New_York")

    def test_dst_autumn_ambiguity_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "ambiguous"):
            local_datetime(date(2027, 11, 7), time(1, 30), "America/New_York")

    def test_workspace_offset_is_applied(self):
        value = local_datetime(date(2027, 3, 14), time(9), "Africa/Douala")
        self.assertEqual(value.utcoffset().total_seconds(), 3600)
