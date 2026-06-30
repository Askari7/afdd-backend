from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # your APIs
    path("api/auth/", include("accounts.urls")),
    path("api/", include("devices.urls")),
path("api/", include("violations.urls")),
path("api/", include("analytics.urls")),

    # existing (non-prefixed) schema & docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # ---------- NEW: prefixed copies to match the public /afdd/ mount ----------
    path("afdd/api/schema/", SpectacularAPIView.as_view(), name="schema_prefixed"),
    path(
        "afdd/api/docs/",
        SpectacularSwaggerView.as_view(url="/afdd/api/schema/"),  # hardcode correct path
        name="swagger-ui-prefixed",
    ),
    path(
        "afdd/api/redoc/",
        SpectacularRedocView.as_view(url="/afdd/api/schema/"),
        name="redoc-prefixed",
    ),
]
