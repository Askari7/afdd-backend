from rest_framework import status, serializers


class AnalyticsRequestSerializer(serializers.Serializer):
    user_id  = serializers.IntegerField(required=True,  help_text="ID of the user")
    date     = serializers.DateField(required=False, format="%Y-%m-%d", input_formats=["%Y-%m-%d"], help_text="From date (YYYY-MM-DD). Defaults to today.")
    to_date  = serializers.DateField(required=False, format="%Y-%m-%d", input_formats=["%Y-%m-%d"], help_text="To date (YYYY-MM-DD). Defaults to now when date is supplied.")


class AnalyticsResponseSerializer(serializers.Serializer):
    vehicle_count = serializers.IntegerField()
    driver_count = serializers.IntegerField()
    violation_count = serializers.IntegerField()
    online_vehicle_count = serializers.IntegerField()


class AnnotationLeaderboardRequestSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False, format="%Y-%m-%d", input_formats=["%Y-%m-%d"], help_text="Start date (YYYY-MM-DD). Defaults to 6 days ago.")
    end_date   = serializers.DateField(required=False, format="%Y-%m-%d", input_formats=["%Y-%m-%d"], help_text="End date (YYYY-MM-DD). Defaults to today.")


class AnnotatorLeaderboardEntrySerializer(serializers.Serializer):
    annotator_id   = serializers.IntegerField()
    annotator_name = serializers.CharField()
    total          = serializers.IntegerField()
    by_date        = serializers.DictField(child=serializers.IntegerField(), help_text="Map of YYYY-MM-DD -> annotation count")


class AnnotationLeaderboardResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField(format="%Y-%m-%d")
    end_date   = serializers.DateField(format="%Y-%m-%d")
    annotators = AnnotatorLeaderboardEntrySerializer(many=True)


class UnevaluatedViolationTypeColumnSerializer(serializers.Serializer):
    violation_type_id = serializers.IntegerField()
    title              = serializers.CharField()
    category_id        = serializers.IntegerField(allow_null=True)
    category_name      = serializers.CharField(allow_null=True, allow_blank=True)


class UnevaluatedContractorRowSerializer(serializers.Serializer):
    user_id         = serializers.IntegerField(allow_null=True)
    contractor_name = serializers.CharField()
    total           = serializers.IntegerField()
    by_type         = serializers.DictField(child=serializers.IntegerField(), help_text="Map of violation_type_id (as string) -> count")


class UnevaluatedViolationsSummaryResponseSerializer(serializers.Serializer):
    violation_types = UnevaluatedViolationTypeColumnSerializer(many=True)
    contractors     = UnevaluatedContractorRowSerializer(many=True)

