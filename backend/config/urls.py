from bookings import views
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("resources", views.ResourceViewSet, basename="resource")
router.register("bookings", views.BookingViewSet, basename="booking")
urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health),
    path("api/csrf/", views.csrf),
    path("api/login/", views.sign_in),
    path("api/logout/", views.sign_out),
    path("api/session/", views.session),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/", include(router.urls)),
]
