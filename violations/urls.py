from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ViolationTypeViewSet, ViolationCategoryViewSet

router = DefaultRouter()
router.register(r'categories', ViolationCategoryViewSet, basename='violationcategory')
router.register(r'types', ViolationTypeViewSet, basename='violationtype')

urlpatterns = [
    path('', include(router.urls)),
]