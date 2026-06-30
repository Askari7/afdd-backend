from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
from analytics.serializers import (
    AnalyticsRequestSerializer, AnalyticsResponseSerializer,
    AnnotationLeaderboardRequestSerializer, AnnotationLeaderboardResponseSerializer,
    UnevaluatedViolationsSummaryResponseSerializer,
)
from accounts.permissions import IsAdmin
from devices.models import Vehicle, Driver, DriverAssignment, Heartbeat, Violation, ViolationAnnotation
from devices.serializers import ViolationSearchSerializer
import math
import pytz
User = get_user_model()



@extend_schema(
    tags=["Analytics"],
    summary="Get summary counts for a user",
    description=(
        "Given a user_id returns counts:\n"
        "- vehicle_count: number of vehicles owned by the user\n"
        "- driver_count: distinct drivers associated (direct + assigned to user's vehicles)\n"
        "- violation_count: violations related to this user (either violation.user or vehicle.owner)\n"
        "- online_vehicle_count: user's vehicles with heartbeats in last 24 hours"
    ),
    request=AnalyticsRequestSerializer,
    responses={200: AnalyticsResponseSerializer},
    examples=[
        OpenApiExample(
            "Request example",
            value={"user_id": 5},
            request_only=True
        ),
        OpenApiExample(
            "Response example",
            value={"vehicle_count": 10, "driver_count": 4, "violation_count": 123, "online_vehicle_count": 3},
            response_only=True
        ),
    ],
)
# class ContractorAnalyticsView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, *args, **kwargs):
#         serializer = AnalyticsRequestSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         user_id = serializer.validated_data["user_id"]

#         # ensure user exists
#         if not User.objects.filter(id=user_id).exists():
#             return Response({"detail": "user not found"}, status=status.HTTP_404_NOT_FOUND)

#         # vehicles owned by user
#         vehicle_qs = Vehicle.objects.filter(user_id=user_id)
#         vehicle_count = vehicle_qs.count()

#         # drivers:
#         # - drivers directly associated (Driver.user_id)
#         # - drivers assigned to user's vehicles (DriverAssignment.vehicle -> vehicle.user_id)
#         direct_driver_ids = set(Driver.objects.filter(user_id=user_id).values_list("id", flat=True))
#         # assigned_driver_ids = set(DriverAssignment.objects.filter(vehicle__user_id=user_id).values_list("driver_id", flat=True))
#         # union and remove None
# #       driver_ids = {d for d in (direct_driver_ids | assigned_driver_ids) if d}
#         driver_count = len(direct_driver_ids)

#         # violations: only today's violations for this user (by user OR by user's vehicles)
#         now = timezone.now()
#         start_of_day = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
#         violation_count = Violation.objects.filter(
#             Q(user_id=user_id),
#             logged_at__gte=start_of_day,
#             logged_at__lte=now,
#             status='true'
#         ).distinct().count()

#         # online vehicles: vehicles owned by user whose device has heartbeats in last 24 hours
#         threshold = timezone.now() - timedelta(minutes=3)
#         recent_device_ids = Heartbeat.objects.filter(logged_at__gte=threshold).values_list("device_id", flat=True).distinct()
#         online_vehicle_count = Vehicle.objects.filter(user_id=user_id, device_id__in=recent_device_ids).distinct().count()

#         resp = {
#             "vehicle_count": vehicle_count,
#             "driver_count": driver_count,
#             "violation_count": violation_count,
#             "online_vehicle_count": online_vehicle_count,
#         }
#         return Response(resp, status=status.HTTP_200_OK)
# --- Helper: Haversine distance between two points in km ---
def haversine_distance(lat1, lon1, lat2, lon2):
    # Earth radius in kilometers
    R = 6371.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c  # in kilometers
class ContractorAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AnalyticsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data["user_id"]
        requested_date = serializer.validated_data.get("date")  # optional date string "YYYY-MM-DD"

        # Ensure user exists
        if not User.objects.filter(id=user_id).exists():
            return Response({"detail": "user not found"}, status=status.HTTP_404_NOT_FOUND)

        # Vehicles owned by user
        vehicles = Vehicle.objects.filter(user_id=user_id)
        vehicle_count = vehicles.count()

        # Drivers directly associated
        direct_driver_ids = set(Driver.objects.filter(user_id=user_id).values_list("id", flat=True))
        driver_count = len(direct_driver_ids)

        # Violations
        import pytz
        PKT = pytz.timezone('Asia/Karachi')
        now = timezone.now()
        now_pkt = now.astimezone(PKT)

        if requested_date:
            try:
                target_date = timezone.datetime.strptime(requested_date, "%Y-%m-%d").date()
            except ValueError:
                return Response({"detail": "Invalid date format. Use YYYY-MM-DD"}, status=400)

            start_of_day = PKT.localize(timezone.datetime.combine(target_date, timezone.datetime.min.time()))
            end_of_day = PKT.localize(timezone.datetime.combine(target_date, timezone.datetime.max.time()))
        else:
            start_of_day = now_pkt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now

        violation_count = Violation.objects.filter(
            Q(user_id=user_id),
            logged_at__gte=start_of_day,
            logged_at__lte=end_of_day,
            status='true'
        ).distinct().count()

        # Online vehicles (heartbeat in last 3 minutes)
        threshold = timezone.now() - timedelta(minutes=3)
        recent_device_ids = Heartbeat.objects.filter(
            logged_at__gte=threshold
        ).values_list("device_id", flat=True).distinct()
        online_vehicle_count = Vehicle.objects.filter(user_id=user_id, device_id__in=recent_device_ids).distinct().count()

        resp = {
            "vehicle_count": vehicle_count,
            "driver_count": driver_count,
            "violation_count": violation_count,
            "online_vehicle_count": online_vehicle_count,
        }
        return Response(resp, status=status.HTTP_200_OK)

class ContractorVehicleStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AnalyticsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id      = serializer.validated_data["user_id"]
        from_date    = serializer.validated_data.get("date")
        to_date_val  = serializer.validated_data.get("to_date")

        if not User.objects.filter(id=user_id).exists():
            return Response({"detail": "user not found"}, status=status.HTTP_404_NOT_FOUND)

        vehicles = list(Vehicle.objects.filter(user_id=user_id).values("id", "name", "device_id"))
        if not vehicles:
            return Response({"vehicles": []}, status=status.HTTP_200_OK)

        now = timezone.now()

        if from_date:
            day_start = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
        else:
            day_start = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()))

        if to_date_val:
            # end of the specified to_date
            day_end = timezone.make_aware(datetime.combine(to_date_val, datetime.max.time()))
        elif from_date:
            # from selected date → up to right now
            day_end = now
        else:
            # no dates given → full today
            day_end = day_start + timedelta(days=1)

        device_ids = [v["device_id"] for v in vehicles]

        # Single query for all vehicles — range filter uses the (device_id, logged_at DESC) index.
        # .values() avoids constructing ORM objects for thousands of rows.
        all_hbs = list(
            Heartbeat.objects
            .filter(
                device_id__in=device_ids,
                logged_at__gte=day_start,
                logged_at__lt=day_end,
                latitude__isnull=False,
                longitude__isnull=False,
            )
            .exclude(latitude=0, longitude=0)
            .order_by("device_id", "logged_at")
            .values("device_id", "logged_at", "latitude", "longitude", "speed")
        )

        # Group rows by device in one pass (query is already sorted by device_id)
        hbs_by_device: dict = {}
        for hb in all_hbs:
            hbs_by_device.setdefault(hb["device_id"], []).append(hb)

        # Bulk violation counts per vehicle.
        # The violations tab reliably uses user_id to find violations.
        # We filter by user_id + date range, then resolve each violation's
        # vehicle by trying vehicle_id first, then falling back to device_id.
        device_to_vehicle = {v["device_id"]: v["id"] for v in vehicles}

        all_violations = (
            Violation.objects
            .filter(user_id=user_id, logged_at__gte=day_start, logged_at__lt=day_end)
            .values("vehicle_id", "device_id")
        )

        violation_counts: dict = {}
        for viol in all_violations:
            # Resolve which vehicle this violation belongs to
            vid = viol.get("vehicle_id") or device_to_vehicle.get(viol.get("device_id"))
            if vid:
                violation_counts[vid] = violation_counts.get(vid, 0) + 1

        vehicle_stats = []
        for v in vehicles:
            hbs = hbs_by_device.get(v["device_id"], [])

            total_distance = 0.0
            total_speed = 0.0
            speed_count = 0
            max_speed = 0.0
            total_driving_seconds = 0
            first_time = last_time = None
            prev_lat = prev_lng = prev_time = None

            for hb in hbs:
                lat = float(hb["latitude"])
                lng = float(hb["longitude"])
                spd = hb["speed"]
                ts  = hb["logged_at"]

                # Track elapsed time across all points (used for fallback avg speed)
                if first_time is None:
                    first_time = ts
                last_time = ts

                if spd and spd > 0:
                    total_speed += spd
                    speed_count += 1
                    if spd > max_speed:
                        max_speed = spd
                    if prev_time is not None:
                        total_driving_seconds += (ts - prev_time).total_seconds()

                if prev_lat is not None and (lat != prev_lat or lng != prev_lng):
                    step = haversine_distance(prev_lat, prev_lng, lat, lng)
                    if step <= 1:
                        total_distance += step

                prev_lat, prev_lng, prev_time = lat, lng, ts

            # Avg speed from speed field; fall back to distance/elapsed_time when
            # the device never reports speed > 0 but position still changed.
            if speed_count:
                average_speed = round(total_speed / speed_count, 2)
            elif total_distance > 0 and first_time and last_time:
                elapsed_hours = (last_time - first_time).total_seconds() / 3600
                average_speed = round(total_distance / elapsed_hours, 2) if elapsed_hours > 0 else 0
                # use elapsed time as driving time too
                total_driving_seconds = int((last_time - first_time).total_seconds())
            else:
                average_speed = 0

            hours, rem = divmod(int(total_driving_seconds), 3600)
            minutes, secs = divmod(rem, 60)

            vehicle_stats.append({
                "vehicle_id": v["id"],
                "name": v["name"],
                "total_distance": round(total_distance, 3),
                "average_speed": average_speed,
                "max_speed": round(max_speed, 2),
                "driving_time": f"{hours}h {minutes}m {secs}s",
                "violation_count": violation_counts.get(v["id"], 0),
            })

        return Response({"vehicles": vehicle_stats}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Analytics"],
    summary="Annotation leaderboard",
    description=(
        "Admin-only. Counts ViolationAnnotation records per annotator per day over a date range, "
        "ranked by total descending. Every user with role='annotator' is included even with zero "
        "activity in range, so idle annotators stay visible."
    ),
    request=AnnotationLeaderboardRequestSerializer,
    responses={200: AnnotationLeaderboardResponseSerializer},
    examples=[
        OpenApiExample(
            "Request example",
            value={"start_date": "2026-06-13", "end_date": "2026-06-19"},
            request_only=True,
        ),
        OpenApiExample(
            "Response example",
            value={
                "start_date": "2026-06-13",
                "end_date": "2026-06-19",
                "annotators": [
                    {
                        "annotator_id": 5,
                        "annotator_name": "John Doe",
                        "total": 42,
                        "by_date": {"2026-06-13": 10, "2026-06-14": 8},
                    }
                ],
            },
            response_only=True,
        ),
    ],
)
class AnnotationLeaderboardView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        serializer = AnnotationLeaderboardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PKT = pytz.timezone('Asia/Karachi')
        today_pkt = timezone.now().astimezone(PKT).date()

        start_date = serializer.validated_data.get("start_date") or (today_pkt - timedelta(days=6))
        end_date = serializer.validated_data.get("end_date") or today_pkt

        if start_date > end_date:
            return Response({"detail": "start_date must not be after end_date"}, status=status.HTTP_400_BAD_REQUEST)

        day_start = PKT.localize(datetime.combine(start_date, datetime.min.time()))
        day_end = PKT.localize(datetime.combine(end_date, datetime.max.time()))

        # Seed every annotator at zero so idle annotators stay visible in the ranking.
        entries = {}
        for a in User.objects.filter(role="annotator").values("id", "username", "first_name", "last_name"):
            entries[a["id"]] = {
                "annotator_id": a["id"],
                "annotator_name": f"{a['first_name']} {a['last_name']}".strip() or a["username"],
                "total": 0,
                "by_date": {},
            }

        annotations = (
            ViolationAnnotation.objects
            .filter(created_at__gte=day_start, created_at__lte=day_end)
            .values(
                "annotated_by_id",
                "annotated_by__username",
                "annotated_by__first_name",
                "annotated_by__last_name",
                "created_at",
            )
        )

        for a in annotations:
            aid = a["annotated_by_id"]
            date_key = a["created_at"].astimezone(PKT).date().isoformat()

            entry = entries.get(aid)
            if entry is None:
                name = (
                    f"{a['annotated_by__first_name']} {a['annotated_by__last_name']}".strip()
                    or a["annotated_by__username"]
                    or "Unknown"
                )
                entry = {"annotator_id": aid, "annotator_name": name, "total": 0, "by_date": {}}
                entries[aid] = entry

            entry["by_date"][date_key] = entry["by_date"].get(date_key, 0) + 1
            entry["total"] += 1

        ranked = sorted(entries.values(), key=lambda e: e["total"], reverse=True)

        response_serializer = AnnotationLeaderboardResponseSerializer({
            "start_date": start_date,
            "end_date": end_date,
            "annotators": ranked,
        })
        return Response(response_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Analytics"],
    summary="Unevaluated violations per contractor",
    description=(
        "Admin-only. Counts violations with status='unevaluated' grouped by contractor (user) "
        "and violation type, using the same filters as /api/violations/search/ (startDate, endDate, "
        "userIds, vehicleIds, violationCategoryIds, violationTypeIds). Contractors are ranked by "
        "total backlog descending; only contractors with at least one matching violation are included."
    ),
    request=ViolationSearchSerializer,
    responses={200: UnevaluatedViolationsSummaryResponseSerializer},
    examples=[
        OpenApiExample(
            "Request example",
            value={
                "startDate": "2025-11-03 00:00:00+05:00",
                "endDate": "2025-11-03 23:59:59+05:00",
                "userIds": [5],
                "violationCategoryIds": [2],
                "violationTypeIds": [7],
                "vehicleIds": [216],
            },
            request_only=True,
        ),
        OpenApiExample(
            "Response example",
            value={
                "violation_types": [
                    {"violation_type_id": 7, "title": "Phone Usage", "category_id": 2, "category_name": "Driver Distraction"},
                ],
                "contractors": [
                    {"user_id": 5, "contractor_name": "ACME Logistics", "total": 23, "by_type": {"7": 23}},
                ],
            },
            response_only=True,
        ),
    ],
)
class UnevaluatedViolationsSummaryView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        serializer = ViolationSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        qs = Violation.objects.filter(status="unevaluated").select_related(
            "user", "violation_type_id", "violation_type_id__category"
        )

        if v.get("startDate"):
            qs = qs.filter(logged_at__gte=v["startDate"])
        if v.get("endDate"):
            qs = qs.filter(logged_at__lte=v["endDate"])
        if v.get("userIds"):
            qs = qs.filter(user_id__in=v["userIds"])
        if v.get("vehicleIds"):
            qs = qs.filter(vehicle_id__in=v["vehicleIds"])
        if v.get("violationTypeIds"):
            qs = qs.filter(violation_type_id__in=v["violationTypeIds"])
        if v.get("violationCategoryIds"):
            qs = qs.filter(violation_type_id__category_id__in=v["violationCategoryIds"])

        rows = qs.values(
            "user_id",
            "user__username",
            "user__first_name",
            "user__last_name",
            "violation_type_id",
            "violation_type_id__title",
            "violation_type_id__category_id",
            "violation_type_id__category__violation_category_name",
        ).annotate(count=Count("id"))

        contractors = {}
        types_seen = {}

        for r in rows:
            uid = r["user_id"]
            name = (
                "Unknown"
                if uid is None
                else (f"{r['user__first_name']} {r['user__last_name']}".strip() or r["user__username"])
            )

            contractor = contractors.setdefault(uid, {
                "user_id": uid,
                "contractor_name": name,
                "total": 0,
                "by_type": {},
            })

            tid = r["violation_type_id"]
            contractor["by_type"][str(tid)] = contractor["by_type"].get(str(tid), 0) + r["count"]
            contractor["total"] += r["count"]

            if tid not in types_seen:
                types_seen[tid] = {
                    "violation_type_id": tid,
                    "title": r["violation_type_id__title"],
                    "category_id": r["violation_type_id__category_id"],
                    "category_name": r["violation_type_id__category__violation_category_name"],
                }

        ranked_contractors = sorted(contractors.values(), key=lambda c: c["total"], reverse=True)
        ranked_types = sorted(types_seen.values(), key=lambda t: (t["category_name"] or "", t["title"]))

        response_serializer = UnevaluatedViolationsSummaryResponseSerializer({
            "violation_types": ranked_types,
            "contractors": ranked_contractors,
        })
        return Response(response_serializer.data, status=status.HTTP_200_OK)