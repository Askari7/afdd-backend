from datetime import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model

from accounts.serializers import UserMinimalSerializer
from .models import Device, Event, Heartbeat, Violation, Vehicle, Driver, DriverAssignment, Broadcast
from violations.models import ViolationType
from django.utils.dateparse import parse_datetime
from django.utils import timezone as django_timezone
from datetime import datetime, timedelta
from violations.serializers import ViolationTypeSerializerForAnnotation
User = get_user_model()

# Read-only nested representation for device shown in GET responses
class DeviceReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ("uuid", "name", "type", "rear_camera_url", "front_camera_url", "features")
class DeviceReadSerializerForAnnotation(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ("uuid", "name", "type")

class VehicleReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ("id", "name", "registration_number")

class VehicleReadSerializerForAnnotation(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = ("id", "name", "registration_number", "user_info")

    def get_user_info(self, obj):
        if obj.user_id:
            return {
                "id": obj.user_id.id,
                "username": obj.user_id.username
            }
        return None

# Read-only nested representation for violation type shown in GET responses
class ViolationTypesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ViolationType
        fields = "__all__"


class DeviceSerializer(serializers.ModelSerializer):
    # expose camelCase keys while mapping to snake_case model fields
    rearCameraUrl = serializers.URLField(source="rear_camera_url", allow_null=True, allow_blank=True, required=False)
    frontCameraUrl = serializers.URLField(source="front_camera_url", allow_null=True, allow_blank=True, required=False)
    vehicle_info = serializers.SerializerMethodField()

    class Meta:
        model = Device
        # keep timestamps snake_case; URLs exposed as camelCase
        fields = [
            "id",
            "uuid",
            "name",
            "type",
            "rearCameraUrl",
            "frontCameraUrl",
            "features",
            'vehicle_info',  # Add vehicle info to response
            "sim",  
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
   
    def get_vehicle_info(self, obj):
        try:
            vehicle = getattr(obj, "vehicles", None)  # 👈 direct access (no query)

            if vehicle:
                user = vehicle.user_id

                return {
                    "id": vehicle.id,
                    "name": vehicle.name,
                    "registration_number": vehicle.registration_number,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                    } if user else None
                }

            return None

        except Exception:
            return None
    def validate_features(self, value):
        """
        Optional: light schema check to keep structure predictable.
        Accepts empty/missing, but if present, must be dict with optional 'camera' and 'sensor' dicts.
        """
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("features must be an object.")
        for k in ("camera", "sensor"):
            if k in value and not isinstance(value[k], dict):
                raise serializers.ValidationError(f"features.{k} must be an object when provided.")
        return value
    


class EventSerializer(serializers.ModelSerializer):
    # expose device_id (uuid string) while mapping to FK "device"
    device = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=Device.objects.all(),
        required=True
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "device",     # uuid string
            "latitude",
            "longitude",
            "accuracy",
            "speed",
            "altitude",
            "logged_at",
            "created_at",
            "type",
            "value",
        ]
        read_only_fields = ["id", "created_at"]


class HeartbeatSerializer(serializers.ModelSerializer):
    # accept device by its uuid for write; still return uuid in responses
    device = serializers.SlugRelatedField(slug_field="uuid", queryset=Device.objects.all())
    # include full device fields in GET responses
    # device_info = DeviceReadSerializer(source="device", read_only=True)

    class Meta:
        model = Heartbeat
        fields = (
            "id",
            "device",
            # "device_info",
            "latitude",
            "longitude",
            "speed",
            "altitude",
            "bearing",
            "logged_at",
            "created_at",
        )
        read_only_fields = ("created_at",)
from rest_framework import serializers
from .models import Vehicle


class VehicleListSerializer(serializers.ModelSerializer):
    latest_logged_at = serializers.DateTimeField(read_only=True)
    today_logged_at = serializers.DateTimeField(read_only=True, required=False)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "name",
            "registration_number",
            "latest_logged_at",
            "today_logged_at",
        ]
class VehicleCamSerializer(serializers.ModelSerializer):
    latest_logged_at = serializers.DateTimeField(read_only=True)
    today_logged_at = serializers.DateTimeField(read_only=True, required=False)
    device_info = DeviceReadSerializer(source="device", read_only=True)
    latest_heartbeat = serializers.SerializerMethodField()
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "name",
            "registration_number",
            "latest_logged_at",
            "today_logged_at",
            "device_info",
            "latest_heartbeat",   # 👈 added here
        ]
    def get_latest_heartbeat(self, obj):
        if not getattr(obj, "latest_logged_at", None):
            return None

        dt = obj.latest_logged_at

        # Ensure datetime is UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        iso = dt.isoformat().replace("+00:00", "Z")

        return {
            "logged_at": iso,
            "latitude": obj.latest_latitude,
            "longitude": obj.latest_longitude,
            "speed": obj.latest_speed,
            "altitude": obj.latest_altitude,
            "bearing": obj.latest_bearing,
        }

class ViolationSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(slug_field="uuid", queryset=Device.objects.all())
    device_info = DeviceReadSerializer(source="device", read_only=True)
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all(), required=False, allow_null=True)
    vehicle_info = VehicleReadSerializer(source='vehicle', read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    violation_type_id = serializers.PrimaryKeyRelatedField(queryset=ViolationType.objects.all())
    violation_type = ViolationTypesSerializer(source="violation_type_id", read_only=True)

    class Meta:
        model = Violation
        fields = (
            "id",
            "device",
            "device_info",
            "latitude",
            "longitude",
            "speed",
            "vehicle",
            "vehicle_info",
            "user",
            "logged_at",
            "created_at",
            "violation_type_id",
            "violation_type",
            "front_camera_video_file_name",
            "cabin_camera_video_file_name",
            "driver_id",
            "status",
        )
        read_only_fields = ("created_at",)

class ViolationDashboardSerializer(serializers.ModelSerializer):
    device_info = DeviceReadSerializerForAnnotation(source="device", read_only=True)
    vehicle_info = VehicleReadSerializerForAnnotation(source='vehicle', read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    violation_type = ViolationTypeSerializerForAnnotation(source="violation_type_id", read_only=True)
    class Meta:
        model = Violation
        fields = [
            "id",
            "device_info",
            "speed",
            "vehicle_info",
            "user",
            "logged_at",
            "created_at",
            "violation_type",
            "front_camera_video_file_name",
            "cabin_camera_video_file_name",
            "status",
        ]

class ViolationFilterSerializer(serializers.ModelSerializer):
    device_info = DeviceReadSerializerForAnnotation(source="device", read_only=True)
    vehicle_info = VehicleReadSerializerForAnnotation(source='vehicle', read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    violation_type = ViolationTypeSerializerForAnnotation(source="violation_type_id", read_only=True)
    class Meta:
        model = Violation
        fields = [
            "id",
            "device_info",
            "speed",
            "vehicle_info",
            "user",
            "logged_at",
            "created_at",
            "violation_type",
            "front_camera_video_file_name",
            "cabin_camera_video_file_name",
            "status",
            "latitude",
            "longitude",
        ]
class ViolationMinimalSerializer(serializers.ModelSerializer):
    device = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    user = UserMinimalSerializer(read_only=True)
    violation_type_id = serializers.PrimaryKeyRelatedField(queryset=ViolationType.objects.all())
    # include full violation type object in GET responses
    violation_type = ViolationTypesSerializer(source="violation_type_id", read_only=True)
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all(), required=False, allow_null=True)
    vehicle_info = VehicleReadSerializer(source='vehicle', read_only=True)

    class Meta:
        model = Violation
        fields = (
            "id",
            "device",
            "user",
            "logged_at",
            "status",
            "vehicle",
            "vehicle_info",
            "violation_type_id",
            "violation_type",
            "front_camera_video_file_name",
            "rear_camera_video_file_name",
        )
class ViolationSearchSerializer(serializers.Serializer):
    # All filters are optional; if omitted, they’re ignored
    startDate = serializers.CharField(required=False)  # ISO string
    endDate = serializers.CharField(required=False)    # ISO string
    status = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    userIds = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    violationCategoryIds = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    violationTypeIds = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    vehicleIds = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=1000)
    role = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        # Parse datetimes if provided (keeps timezone offsets like +05:00)
        for fld in ("startDate", "endDate"):
            if fld in data and data[fld] is not None:
                dt = parse_datetime(data[fld])
                if not dt:
                    raise serializers.ValidationError({fld: "Invalid datetime format. Use ISO 8601, e.g. 2025-11-03 00:00:00+05:00"})
                data[fld] = dt
        return data
class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email")

class VehicleMapSerializer(serializers.ModelSerializer):
    latest_heartbeat = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = ("id", "name", "latest_heartbeat")

    def get_latest_heartbeat(self, obj):
        if not getattr(obj, "latest_logged_at", None):
            return None

        dt = obj.latest_logged_at

        # Ensure datetime is UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        iso = dt.isoformat().replace("+00:00", "Z")

        return {
            "logged_at": iso,
            "latitude": obj.latest_latitude,
            "longitude": obj.latest_longitude,
            "speed": obj.latest_speed,
            "altitude": obj.latest_altitude,
            "bearing": obj.latest_bearing,
        }


class VehicleSerializer(serializers.ModelSerializer):
    # write: accept device by uuid, user by PK
    device = serializers.SlugRelatedField(slug_field="uuid", queryset=Device.objects.all())
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    # read-only nested representations
    device_info = DeviceReadSerializer(source="device", read_only=True)
    user_info = UserReadSerializer(source="user_id", read_only=True)
    latest_heartbeat = serializers.SerializerMethodField()
    t_hb = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "device",
            "device_info",
            "user_id",
            "user_info",
            "name",
            "registration_number",
            "model_name",
            "model_year",
            "chasis_number",
            "engine_number",
            "color",
            "manufacturer",
            "type",
            "latest_heartbeat",   # 👈 added here
            "t_hb",
            
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
    def get_latest_heartbeat(self, obj):
        if not getattr(obj, "latest_logged_at", None):
            return None

        dt = obj.latest_logged_at

        # Ensure datetime is UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        iso = dt.isoformat().replace("+00:00", "Z")

        return {
            "logged_at": iso,
            "latitude": obj.latest_latitude,
            "longitude": obj.latest_longitude,
            "speed": obj.latest_speed,
            "altitude": obj.latest_altitude,
            "bearing": obj.latest_bearing,
        }
    def get_streams(self, obj):
        if not obj.device_info or not getattr(obj.device_info, "features", None):
            return []
        cams = obj.device_info.features
        uuid = obj.device_info.uuid
        streams: list[str] = []
        if cams.frontCamera: streams.append(f"{uuid}-cam1")
        if cams.cabinCamera: streams.append(f"{uuid}-cam2")
        if cams.rearCamera: streams.append(f"{uuid}-cam3")
        if cams.leftCamera: streams.append(f"{uuid}-cam4")
        if cams.rightCamera: streams.append(f"{uuid}-cam5")
        return streams

    def get_status(self, obj):
        return "NR" if obj.is_nr else "Reporting"
    
    def get_t_hb(self, obj):
        # Cache per object so get_avg_speed / get_total_distance share the same result
        cache_key = f"_t_hb_{obj.pk}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        # Skip the per-vehicle DB query on list actions — only compute for single retrieve
        view = self.context.get("view")
        if view and getattr(view, "action", None) in ("list", "cam_simple", "list_simple", "map_simple", "multiple_users_vehicles"):
            return []

        request = self.context.get("request")
        device = getattr(obj, "device", None)
        if not device:
            return []

        # Get date from query params, fallback to today
        date_str = request.query_params.get("date") if request else None
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                target_date = django_timezone.localdate()
        else:
            target_date = django_timezone.localdate()

        # Use range filter instead of a date-cast so the (device_id, logged_at DESC)
        # B-tree index is usable without requiring an IMMUTABLE expression index.
        day_start = django_timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        hbs = (
            Heartbeat.objects
            .filter(device=device, logged_at__gte=day_start, logged_at__lt=day_end)
            .order_by("logged_at")
            .values("logged_at", "latitude", "longitude", "speed")[:12640]
        )

        out = []
        for hb in hbs:
            dt = hb["logged_at"]

            if dt is None:
                logged_iso = None
            else:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)

                logged_iso = dt.isoformat().replace("+00:00", "Z")

            out.append({
                "dt": logged_iso,
                "lat": hb["latitude"],
                "lng": hb["longitude"],
                "speed": hb["speed"],
            })

        setattr(self, cache_key, out)
        return out

    def get_avg_speed(self, obj):
        hbs = self.get_t_hb(obj)
        if not hbs:
            return 0
        speeds = [hb["speed"] for hb in hbs if hb["speed"] is not None and hb["speed"] > 0]
        if not speeds:
            return 0
        return sum(speeds) / len(speeds)

    def get_total_distance(self, obj):
        hbs = self.get_t_hb(obj)
        if not hbs or len(hbs) < 2:
            return 0

        total_km = 0
        prev_lat, prev_lng = hbs[0]["lat"], hbs[0]["lng"]

        for hb in hbs[1:]:
            lat, lng = hb["lat"], hb["lng"]
            if lat is None or lng is None or prev_lat is None or prev_lng is None:
                prev_lat, prev_lng = lat, lng
                continue
            if lat == prev_lat and lng == prev_lng:
                continue
            total_km += haversine_distance(float(prev_lat), float(prev_lng), float(lat), float(lng))
            prev_lat, prev_lng = lat, lng

        return round(total_km, 3)
import math

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
class MultipleUserVehicleSerializer(serializers.ModelSerializer):
    # Only include essential fields
    latest_heartbeat = serializers.SerializerMethodField()
    user_info = UserReadSerializer(source="user_id", read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "name",
            "registration_number",
            "device",
            "user_id",
            "latest_heartbeat",
            "user_info",
        )

    def get_latest_heartbeat(self, obj):
        if not getattr(obj, "latest_logged_at", None):
            return None

        dt = obj.latest_logged_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        iso = dt.isoformat().replace("+00:00", "Z")
        return {
            "logged_at": iso,
            "latitude": obj.latest_latitude,
            "longitude": obj.latest_longitude,
            "speed": obj.latest_speed,
            "altitude": obj.latest_altitude,
            "bearing": obj.latest_bearing,
        }
    
    
def parse_dob(value: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    if not value:
        return value

    value = str(value).strip()

    # Already correct
    if len(value) == 10 and value[4] == "-":
        return value

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise serializers.ValidationError(f"Unrecognized date format: '{value}'. Use YYYY-MM-DD.")


class DriverSerializer(serializers.ModelSerializer):

    # ── write: accept username string OR pk ──────────────────────────────────
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    # ── read: nested user info ────────────────────────────────────────────────
    user_info = UserReadSerializer(source="user_id", read_only=True)

    class Meta:
        model = Driver
        fields = (
            "id",
            "user_id",
            "user_info",
            "name",
            "email",
            "phone_number",
            "address",
            "cnic_number",
            "rfid_tag",
            "dob",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    # ── normalize dob before Django's DateField validation runs ──────────────
    def to_internal_value(self, data):
        raw_dob = data.get("dob")
        if raw_dob and isinstance(raw_dob, str):
            # Mutate a copy so we never touch the original payload dict
            data = data.copy()
            data["dob"] = parse_dob(raw_dob)        # → "YYYY-MM-DD"
        return super().to_internal_value(data)      # DateField now happy ✅

    # ── resolve username → User instance (keeps view clean) ──────────────────
    def to_internal_value(self, data):
        raw_dob = data.get("dob")
        username = data.get("user_id")

        data = data.copy()

        # 1. Resolve username string → PK so PrimaryKeyRelatedField can handle it
        if isinstance(username, str) and not username.isdigit():
            user = User.objects.filter(username=username).first()
            if not user:
                raise serializers.ValidationError({"user_id": f"User '{username}' not found."})
            data["user_id"] = user.pk          # PrimaryKeyRelatedField expects PK

        # 2. Normalize dob
        if raw_dob and isinstance(raw_dob, str):
            data["dob"] = parse_dob(raw_dob)

        return super().to_internal_value(data)


class DriverAssignmentSerializer(serializers.ModelSerializer):
    driver = serializers.PrimaryKeyRelatedField(
        queryset=Driver.objects.all(), allow_null=True, required=False
    )
    device = serializers.SlugRelatedField(slug_field="uuid", queryset=Device.objects.all())

    driver_info = DriverSerializer(source="driver", read_only=True)
    device_info = serializers.ModelSerializer(source="device", read_only=True)

    try:
        device_info = DeviceReadSerializer(source="device", read_only=True)
    except NameError:
        pass

    class Meta:
        model = DriverAssignment
        fields = (
            "id",
            "driver",
            "driver_info",
            "device",
            "device_info",
            "status",
            "latitude",
            "longitude",
            "speed",
            "assigned_at",
            "unassigned_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

class VehicleNestedSerializer(serializers.ModelSerializer):
    device_info = DeviceReadSerializer(source="device", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "name",
            "registration_number",
            "model_name",
            "model_year",
            "chasis_number",
            "engine_number",
            "color",
            "manufacturer",
            "type",
            "device_info",
        ]

class UserWithVehiclesSerializer(serializers.ModelSerializer):
    vehicles = VehicleNestedSerializer(many=True, read_only=True)  # uses related_name="vehicles"

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "vehicles",
        ]


class BroadcastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Broadcast
        fields = (
            "id",
            "user_id",
            "vehicle_id",
            "vehicle_uuid",
            "vehicle_name",
            "date",
            "file_name",
            "duration",
            "created_at",
        )
        read_only_fields = ("id", "created_at")