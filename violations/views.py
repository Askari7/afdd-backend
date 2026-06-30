from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated,AllowAny
from django.db.models import Q
from .models import ViolationType, ViolationCategory
from .serializers import ViolationCategorySerializerForAnnotation, ViolationTypeSerializer, ViolationCategorySerializer, ViolationTypeSerializerForAnnotation
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

@extend_schema_view(
    list=extend_schema(
        tags=["Violation Categories"],
        summary="List violation categories",
        description="List all violation categories with optional search filter.",
        parameters=[
            OpenApiParameter(
                name="search",
                description="Search in name and description",
                required=False,
                type=OpenApiTypes.STR
            ),
        ],
        responses={200: ViolationCategorySerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Violation Categories"],
        summary="Get a violation category",
        responses={200: ViolationCategorySerializer},
    ),
    create=extend_schema(
        tags=["Violation Categories"],
        summary="Create a violation category",
        request=ViolationCategorySerializer,
        responses={201: ViolationCategorySerializer},
    ),
)
class ViolationCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]  # Adjust as needed
    serializer_class = ViolationCategorySerializerForAnnotation
    queryset = ViolationCategory.objects.all().order_by('violation_category_name')

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(violation_category_name__icontains=search) |
                Q(description__icontains=search)
            )
        return qs


@extend_schema_view(
    list=extend_schema(
        tags=["Violation Types"],
        summary="List violation types",
        description="List all violation types with optional filters.",
        parameters=[
            OpenApiParameter(
                name="category",
                description="Filter by category ID",
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name="search",
                description="Search in title and description",
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name="is_annotatable",
                description="Filter by annotatable status",
                required=False,
                type=OpenApiTypes.BOOL
            ),
        ],
        responses={200: ViolationTypeSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Violation Types"],
        summary="Get a violation type",
        responses={200: ViolationTypeSerializer},
    ),
    create=extend_schema(
        tags=["Violation Types"],
        summary="Create a violation type",
        request=ViolationTypeSerializer,
        responses={201: ViolationTypeSerializer},
        examples=[
            OpenApiExample(
                "Create violation type",
                value={
                    "title": "Speed Violation",
                    "description": "Vehicle exceeding speed limit",
                    "category": 1,
                    "is_annotatable": True,
                    "severity": 2
                },
            ),
        ],
    ),
)
class ViolationTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]  # Adjust as needed
    serializer_class = ViolationTypeSerializerForAnnotation
    queryset = ViolationType.objects.select_related('category').all().order_by('title')

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        search = self.request.query_params.get('search')
        is_annotatable = self.request.query_params.get('is_annotatable')

        if category:
            qs = qs.filter(category_id=category)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        if is_annotatable is not None:
            is_annotatable = is_annotatable.lower() in ('true', '1', 'yes')
            qs = qs.filter(is_annotatable=is_annotatable)
        return qs
