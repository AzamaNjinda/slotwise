import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.db import connection, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Booking, Membership, Resource
from .serializers import (
    BookingSerializer,
    CreateBookingSerializer,
    ResourceSerializer,
    SessionSerializer,
    WorkspaceSerializer,
)
from .services import cancel_booking, create_booking


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
@csrf_protect
def sign_in(request):
    # A small local-cache throttle protects the development deployment. Use a shared
    # cache and edge rate limiting when running multiple production processes.
    key = f"login:{request.META.get('REMOTE_ADDR', 'unknown')}"
    attempts = cache.get(key, 0)
    if attempts >= 15:
        return JsonResponse(
            {"detail": "Too many attempts. Try again in a minute."}, status=429
        )
    cache.set(key, attempts + 1, 60)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"detail": "Send a JSON object."}, status=400)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("username"), str)
        or not isinstance(data.get("password"), str)
    ):
        return JsonResponse(
            {"detail": "Username and password are required."}, status=400
        )
    user = authenticate(request, username=data["username"], password=data["password"])
    if user is None:
        return JsonResponse(
            {"detail": "Your username or password is incorrect."}, status=400
        )
    login(request, user)
    cache.delete(key)
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
@csrf_protect
def sign_out(request):
    logout(request)
    return JsonResponse({"detail": "Signed out.", "csrfToken": get_token(request)})


@extend_schema(responses=SessionSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])
def session(request):
    if not request.user.is_authenticated:
        return Response({"user": None, "workspaces": []})
    workspaces = [
        membership.workspace
        for membership in request.user.memberships.select_related("workspace").order_by(
            "workspace__name"
        )
    ]
    return Response(
        {
            "user": {
                "id": request.user.id,
                "name": request.user.get_full_name() or request.user.username,
                "username": request.user.username,
            },
            "workspaces": WorkspaceSerializer(
                workspaces, many=True, context={"request": request}
            ).data,
        }
    )


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


class WorkspaceScope:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        workspace_id = request.query_params.get("workspace")
        memberships = request.user.memberships.select_related("workspace")
        if workspace_id:
            workspace_id = serializers.UUIDField().run_validation(workspace_id)
            memberships = memberships.filter(workspace_id=workspace_id)
        membership = memberships.order_by("workspace__name").first()
        if membership is None:
            raise PermissionDenied("You do not have access to this workspace.")
        request.workspace = membership.workspace
        request.membership = membership

    def require_manager(self):
        if self.request.membership.role != Membership.Role.MANAGER:
            raise PermissionDenied("Only workspace managers can manage spaces.")


class ResourceViewSet(WorkspaceScope, viewsets.ModelViewSet):
    serializer_class = ResourceSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Resource.objects.none()
        queryset = Resource.objects.filter(workspace=self.request.workspace)
        if self.request.membership.role != Membership.Role.MANAGER:
            queryset = queryset.filter(active=True)
        return queryset

    def perform_create(self, serializer):
        self.require_manager()
        serializer.save(workspace=self.request.workspace)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        self.require_manager()
        instance = self.get_queryset().select_for_update().get(pk=self.get_object().pk)
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        capacity = serializer.validated_data.get("capacity", instance.capacity)
        if instance.bookings.filter(
            status=Booking.Status.CONFIRMED,
            ends_at__gt=timezone.now(),
            attendees__gt=capacity,
        ).exists():
            raise ValidationError(
                {
                    "capacity": "An upcoming booking needs the current capacity. Cancel or move it first."
                }
            )
        serializer.save()
        return Response(serializer.data)


class BookingViewSet(WorkspaceScope, viewsets.ReadOnlyModelViewSet):
    serializer_class = BookingSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        queryset = Booking.objects.select_related("resource", "owner").filter(
            resource__workspace=self.request.workspace
        )
        if self.action == "list":
            date_value = self.request.query_params.get("date")
            day = (
                serializers.DateField().run_validation(date_value)
                if date_value
                else timezone.localdate(
                    timezone=ZoneInfo(self.request.workspace.timezone)
                )
            )
            start = datetime.combine(
                day, time.min, ZoneInfo(self.request.workspace.timezone)
            )
            end = datetime.combine(
                day + timedelta(days=1),
                time.min,
                ZoneInfo(self.request.workspace.timezone),
            )
            queryset = queryset.filter(starts_at__lt=end, ends_at__gt=start)
        return queryset

    @extend_schema(
        request=CreateBookingSerializer,
        responses={201: BookingSerializer, 200: BookingSerializer},
    )
    def create(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        resource = get_object_or_404(
            Resource, id=data.pop("resource"), workspace=request.workspace
        )
        request_key = request.headers.get("Idempotency-Key") or None
        if request_key and len(request_key) > 128:
            raise ValidationError("Idempotency-Key must be at most 128 characters.")
        booking, created = create_booking(
            owner=request.user, resource=resource, request_key=request_key, **data
        )
        return Response(
            self.get_serializer(booking).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if (
            booking.owner_id != request.user.id
            and request.membership.role != Membership.Role.MANAGER
        ):
            raise PermissionDenied("You can only cancel your own bookings.")
        return Response(self.get_serializer(cancel_booking(booking)).data)
