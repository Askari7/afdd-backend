from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AssignUsersToManagerView, ContractorViewSet, RegisterView, LoginView, TokenRefreshView_, LogoutView,
    MeView, ChangePasswordView, RequestPasswordResetView, ResetPasswordConfirmView, 
    VerifyEmailView, UserViewSet, ContractorViewSet
)

# Create a router and register our viewset
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'contractors', ContractorViewSet, basename='contractor')

urlpatterns = [
    # Include the router URLs
    path('', include(router.urls)),
    
    # Auth endpoints
    path("register/", RegisterView.as_view()),
    path("login/", LoginView.as_view()),
    path("token/refresh/", TokenRefreshView_.as_view()),
    path("logout/", LogoutView.as_view()),
    path("me/", MeView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("password-reset/", RequestPasswordResetView.as_view()),
    path("password-reset/confirm/", ResetPasswordConfirmView.as_view()),
    path("verify-email/", VerifyEmailView.as_view()),
    path("assign-users-to-manager/", AssignUsersToManagerView.as_view()),
]
