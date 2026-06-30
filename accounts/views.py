from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from rest_framework import generics, permissions, status, throttling
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    AssignUsersToManagerSerializer, RegisterSerializer, LoginSerializer, UserManagementSerializer, UserMinimalSerializer, UserSerializer,
    ChangePasswordSerializer, RequestPasswordResetSerializer,
    ResetPasswordConfirmSerializer, VerifyEmailSerializer,
)
from .tokens import email_verification_token, password_reset_token
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db.models import Q
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiExample,
    OpenApiParameter,OpenApiResponse
)
from devices.serializers import UserWithVehiclesSerializer
from django.db.models import Prefetch
from devices.models import Vehicle
from rest_framework.decorators import action

User = get_user_model()
# ---- drf-spectacular imports ----

@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Register a new user or users",
        request=RegisterSerializer,
        responses={201: UserSerializer},
        examples=[
            OpenApiExample(
                "Register payload",
                value={"username": "ali", "email": "ali@example.com",
                       "password": "StrongPass!23", "role": "manager"}
            ),
            OpenApiExample(
                "Bulk register (array)",
                value=[
                    {"username": "ali", "email": "ali@example.com", "password": "StrongPass!23", "role": "manager"},
                    {"username": "sara", "email": "sara@example.com", "password": "StrongPass!23", "role": "user"}
                ]
            ),
            OpenApiExample(
                "Bulk register (wrapped)",
                value={
                    "users": [
                        {"username": "tom", "email": "tom@example.com", "password": "StrongPass!23", "role": "admin"},
                        {"username": "jane", "email": "jane@example.com", "password": "StrongPass!23", "role": "user"}
                    ]
                }
            )
        ],
    )
)
class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_classes = [throttling.AnonRateThrottle]

    # Support both single and bulk payloads
    # - raw list: [{user1}, {user2}, ...]
    # - wrapped list: {"users": [{...}, {...}]}
    def get_serializer(self, *args, **kwargs):
        data = kwargs.get("data")
        if isinstance(data, dict) and "users" in data and isinstance(data["users"], list):
            kwargs["data"] = data["users"]
            kwargs["many"] = True
        elif isinstance(data, list):
            kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    def perform_create(self, serializer):
        created = serializer.save()
        # created can be a single instance or a list when many=True
        if isinstance(created, list):
            for u in created:
                self.send_verify_email(u)
        else:
            self.send_verify_email(created)

    def send_verify_email(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        # Frontend route should capture these params:
        verify_url = f"{self.request.build_absolute_uri('/')}verify-email?uid={uid}&token={token}"
        send_mail(
            subject="Verify your email",
            message=f"Click to verify: {verify_url}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )

@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Login (JWT) — obtain access & refresh tokens",
        request=LoginSerializer,
        responses={
            200: OpenApiTypes.OBJECT
        },
        examples=[
            OpenApiExample(
                "Login request",
                value={"username": "ali", "password": "StrongPass!23"},
            ),
            OpenApiExample(
                "Login success",
                value={"access": "<jwt_access>", "refresh": "<jwt_refresh>"},
                response_only=True
            ),
            OpenApiExample(
                "Login failure",
                value={"detail": "No active account found with the given credentials"},
                response_only=True
            ),
        ],
    )
)
class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.AnonRateThrottle]

@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Refresh access token",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Refresh request",
                value={"refresh": "<jwt_refresh>"}
            ),
            OpenApiExample(
                "Refresh success",
                value={"access": "<new_jwt_access>"}, response_only=True
            ),
        ],
    )
)
class TokenRefreshView_(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
@extend_schema(
    tags=["Auth"],
    summary="Logout — blacklist refresh token",
    responses={
        205: None,
        400: OpenApiTypes.OBJECT,
    },
    examples=[
        OpenApiExample(
            "Logout request",
            value={"refresh": "<jwt_refresh>"}
        ),
        OpenApiExample(
            "Invalid token",
            value={"detail": "Invalid refresh token"},
            response_only=True
        ),
    ],
)
class LogoutView(APIView):
    def post(self, request):
        try:
            refresh = request.data["refresh"]
            token = RefreshToken(refresh)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"detail": "Invalid refresh token"}, status=400)


@extend_schema_view(
    get=extend_schema(
        tags=["Auth"], summary="Current user profile (GET)",
        responses={200: UserSerializer}
    ),
    patch=extend_schema(
        tags=["Auth"], summary="Update current user (PATCH)",
        request=UserSerializer, responses={200: UserSerializer}
    ),
    put=extend_schema(
        tags=["Auth"], summary="Replace current user (PUT)",
        request=UserSerializer, responses={200: UserSerializer}
    ),
)
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user
@extend_schema(
    tags=["Auth"],
    summary="Change password",
    request=ChangePasswordSerializer,
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    examples=[
        OpenApiExample(
            "Change password payload",
            value={"old_password": "OldPass123!", "new_password": "NewPass#456"}
        ),
        OpenApiExample(
            "Old password incorrect",
            value={"detail": "Old password incorrect"},
            response_only=True
        ),
        OpenApiExample(
            "Success",
            value={"detail": "Password changed"},
            response_only=True
        ),
    ],
)
class ChangePasswordView(APIView):
    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        user = request.user
        if not check_password(ser.validated_data["old_password"], user.password):
            return Response({"detail": "Old password incorrect"}, status=400)
        user.set_password(ser.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password changed"})

@extend_schema(
    tags=["Auth"],
    summary="Request password reset (email with link)",
    request=RequestPasswordResetSerializer,
    responses={200: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Request payload",
            value={"email": "ali@example.com"}
        ),
        OpenApiExample(
            "Success (generic response)",
            value={"detail": "Email sent if account exists."},
            response_only=True
        ),
    ],
)
class RequestPasswordResetView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        ser = RequestPasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=ser.validated_data["email"])
        except User.DoesNotExist:
            return Response({"detail": "If the email exists, a link will be sent."})
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = password_reset_token.make_token(user)
        reset_url = f"{request.build_absolute_uri('/')}reset-password?uid={uid}&token={token}"
        send_mail(
            subject="Reset your password",
            message=f"Reset link: {reset_url}",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )
        return Response({"detail": "Email sent if account exists."})



@extend_schema(
    tags=["Auth"],
    summary="Confirm password reset",
    request=ResetPasswordConfirmSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Confirm payload",
            value={"user_id": 2, "new_password": "NewPass#456"}
        ),
        OpenApiExample(
            "Invalid user",
            value={"detail": "Invalid user"},
            response_only=True
        ),
        OpenApiExample(
            "Not authorized",
            value={"detail": "Not authorized"},
            response_only=True
        ),
        OpenApiExample(
            "Success",
            value={"detail": "Password reset successful"},
            response_only=True
        ),
    ],
)
class ResetPasswordConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        # Only admin/staff may reset other users' passwords via this endpoint
        if not (request.user.is_staff or getattr(request.user, "role", None) == "admin"):
            return Response({"detail": "Not authorized"}, status=403)

        ser = ResetPasswordConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = User.objects.get(pk=ser.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "Invalid user"}, status=400)

        user.set_password(ser.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password reset successful"})



@extend_schema(
    tags=["Auth"],
    summary="Verify email",
    request=VerifyEmailSerializer,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Verify payload",
            value={"uid": "Mg", "token": "abcdef"}
        ),
        OpenApiExample(
            "Invalid link",
            value={"detail": "Invalid link"},
            response_only=True
        ),
        OpenApiExample(
            "Token invalid/expired",
            value={"detail": "Token invalid/expired"},
            response_only=True
        ),
        OpenApiExample(
            "Success",
            value={"detail": "Email verified"},
            response_only=True
        ),
    ],
)
class VerifyEmailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            uid = force_str(urlsafe_base64_decode(ser.validated_data["uid"]))
            user = User.objects.get(pk=uid)
        except Exception:
            return Response({"detail": "Invalid link"}, status=400)
        if not email_verification_token.check_token(user, ser.validated_data["token"]):
            return Response({"detail": "Token invalid/expired"}, status=400)
        user.email_verified = True
        user.save()
        return Response({"detail": "Email verified"})



class IsAdminUserOrStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.is_staff or request.user.role == "admin"))




@extend_schema(
    tags=["Admin"],
    summary="Assign users to a manager",
    request=AssignUsersToManagerSerializer,
    responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "Assign payload",
            value={"manager_id": 5, "user_ids": [10, 11, 12]}
        ),
        OpenApiExample(
            "Success",
            value={"assigned": 3, "skipped": []},
            response_only=True
        ),
    ],
)
class AssignUsersToManagerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        POST body:
        {
          "manager_id": <manager_pk>,
          "user_ids": [<user_pk>, ...],
          "replace": false   # optional; default false (append). If true -> replace all existing associations for this manager.
        }
        """
        ser = AssignUsersToManagerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = ser.save()
        return Response(result, status=status.HTTP_200_OK)
@extend_schema_view(
    list=extend_schema(
        tags=["Users"],
        summary="List users",
        description="List users. Admin/staff only. Supports filtering by role, is_active and search (username/email).",
        parameters=[
            OpenApiParameter(name="role", description="Filter by user role", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="is_active", description="Filter by active status (true/false)", required=False, type=OpenApiTypes.BOOL),
            OpenApiParameter(name="search", description="Search username or email", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page", description="Page number (if pagination enabled)", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="page_size", description="Page size (capped by global settings)", required=False, type=OpenApiTypes.INT),
        ],
        responses={200: UserSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Users"],
        summary="Get a user by ID",
        responses={200: UserSerializer},
    ),
        update=extend_schema(
        tags=["Users"],
        summary="Update a user (Full)",
        description="Update user details. Admin/staff only.",
        request=UserSerializer,
        responses={
            200: UserSerializer,
            403: OpenApiResponse(description="Not authorized"),
            404: OpenApiResponse(description="User not found")
        },
        examples=[
            OpenApiExample(
                "Update user",
                value={
                    "username": "updated_username",
                    "email": "updated@example.com",
                    "role": "manager",
                    "is_active": True,
                    "first_name": "Updated",
                    "last_name": "User"
                }
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Users"],
        summary="Update a user (Partial)",
        description="Partially update user details. Admin/staff only.",
        request=UserSerializer,
        responses={
            200: UserSerializer,
            403: OpenApiResponse(description="Not authorized"),
            404: OpenApiResponse(description="User not found")
        },
        examples=[
            OpenApiExample(
                "Partial update",
                value={
                    "role": "manager",
                    "is_active": False
                }
            ),
        ],
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    Read-only CRUD for users (list, retrieve).
    Access: IsAdminUserOrStaff
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.all().order_by("-id")

    def get_serializer_class(self):
        if self.action == "management":
            return UserManagementSerializer

        if self.action == "dropdown":
            return UserMinimalSerializer

        if self.action in ["list", "retrieve"]:
            return UserMinimalSerializer

        return UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # If user is a manager, only show associated users
        if self.request.user.role == "manager":
            from .models import ManagerUserAssociation

            associated_user_ids = ManagerUserAssociation.objects.filter(
                manager=self.request.user
            ).values_list("user_id", flat=True)

            qs = qs.filter(id__in=associated_user_ids)

        role = self.request.query_params.get("role")
        is_active = self.request.query_params.get("is_active")
        search = self.request.query_params.get("search")

        if role:
            qs = qs.filter(role=role)

        if is_active is not None:
            is_active = is_active.lower()
            if is_active in ("true", "1", "yes"):
                qs = qs.filter(is_active=True)
            elif is_active in ("false", "0", "no"):
                qs = qs.filter(is_active=False)

        if search:
            qs = qs.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search)
            )

        return qs
    @action(detail=False, methods=["get"], url_path="edit")
    def edit(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
    @action(detail=False, methods=["get"], url_path="management")
    def management(self, request, *args, **kwargs):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
    @action(detail=False, methods=["get"], url_path="dropdown")
    def dropdown(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # optional: restrict fields further if needed
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        # Prevent password updates here
        if "password" in request.data:
            return Response(
                {"detail": "Password cannot be updated through this endpoint. Use /api/auth/change-password/ instead."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

class ContractorViewSet(viewsets.ModelViewSet):
    serializer_class = UserWithVehiclesSerializer
    queryset = User.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        # Filter only users with role 'user'
        qs = qs.filter(role="user")

        # Manager filter: if the logged-in user is a manager, show only associated users
        if self.request.user.role == "manager":
            from .models import ManagerUserAssociation
            associated_user_ids = ManagerUserAssociation.objects.filter(
                manager=self.request.user
            ).values_list('user_id', flat=True)
            qs = qs.filter(id__in=associated_user_ids)

        # Optional query params
        is_active = self.request.query_params.get("is_active")
        search = self.request.query_params.get("search")

        if is_active is not None:
            if is_active.lower() in ("true", "1", "yes"):
                qs = qs.filter(is_active=True)
            elif is_active.lower() in ("false", "0", "no"):
                qs = qs.filter(is_active=False)

        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))

        # Prefetch vehicles with related device info
        qs = qs.prefetch_related(
            Prefetch(
                "vehicles",
                queryset=Vehicle.objects.select_related("device")
            )
        )

        return qs