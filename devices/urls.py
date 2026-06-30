from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DeviceViewSet,
    EventViewSet,
    HeartbeatViewSet,
    ViolationViewSet,
    VehicleViewSet,
    DriverViewSet,
    DriverAssignmentViewSet,
    BroadcastViewSet,
    get_signed_url,
)

router = DefaultRouter()
router.register(r"devices", DeviceViewSet, basename="device")
router.register(r"events", EventViewSet, basename="event")
router.register(r"heartbeats", HeartbeatViewSet, basename="heartbeat")
router.register(r"violations", ViolationViewSet, basename="violation")
router.register(r"vehicles", VehicleViewSet, basename="vehicle")
router.register(r"drivers", DriverViewSet, basename="driver")
router.register(r"driver-assign", DriverAssignmentViewSet, basename="driverassignment")
router.register(r"broadcasts", BroadcastViewSet, basename="broadcast")
urlpatterns = [
    path("", include(router.urls)),
    path("signed-url/", get_signed_url, name="get_signed_url"),
]
