from rest_framework import serializers
from .models import ViolationType, ViolationCategory

class ViolationCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ViolationCategory
        fields = (
            'id',
            'violation_category_name',
            'description',
            'created_at'
        )
        read_only_fields = ('created_at',)


class ViolationTypeSerializer(serializers.ModelSerializer):
    # Include nested category data in GET responses
    category_info = ViolationCategorySerializer(source='category', read_only=True)

    class Meta:
        model = ViolationType
        fields = (
            'id',
            'title',
            'description',
            'category',
            'category_info',
            'is_annotatable',
            'severity',
            'created_at'
        )
        read_only_fields = ('created_at',)

class ViolationCategorySerializerForAnnotation(serializers.ModelSerializer):
    class Meta:
        model = ViolationCategory
        fields = (
            'id',
            'violation_category_name',
            'created_at'
        )
        read_only_fields = ('created_at',)


class ViolationTypeSerializerForAnnotation(serializers.ModelSerializer):
    # Include nested category data in GET responses
    category_info = ViolationCategorySerializerForAnnotation(source='category', read_only=True)

    class Meta:
        model = ViolationType
        fields = (
            'id',
            'title',
            'category',
            'category_info',
            'is_annotatable',
            'severity',
            'created_at'
        )
        read_only_fields = ('created_at',)