from django.urls import path
from .views import (
    ContractorAnalyticsView,
    ContractorVehicleStatsView,
    AnnotationLeaderboardView,
    UnevaluatedViolationsSummaryView,
)

urlpatterns = [
    path('contractor/summary/', ContractorAnalyticsView.as_view(), name='contractor-analytics'),
    path('contractor/summary/vehicles/', ContractorVehicleStatsView.as_view(), name='contractor-vehicle-stats'),
    path('annotation-leaderboard/', AnnotationLeaderboardView.as_view(), name='annotation-leaderboard'),
    path('unevaluated-violations-summary/', UnevaluatedViolationsSummaryView.as_view(), name='unevaluated-violations-summary'),
]