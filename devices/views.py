import logging
import threading
import paramiko
import io
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated, IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import transaction,IntegrityError
from django.db.models import Q, Case, When, F, DateTimeField, DecimalField
from django.utils.dateparse import parse_datetime
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
from rest_framework.decorators import action
from django.db.models import OuterRef, Subquery
from django.db.models.functions import JSONObject
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q
from .models import Device
from .serializers import DeviceSerializer
logger = logging.getLogger(__name__)
from .serializers import VehicleMapSerializer, ViolationDashboardSerializer
from django.utils import timezone
from datetime import timedelta
import json
from .models import Device, Event, Heartbeat, Violation, Vehicle, Driver, DriverAssignment, ViolationAnnotation, Broadcast
from .serializers import DeviceSerializer, EventSerializer, HeartbeatSerializer, MultipleUserVehicleSerializer, VehicleCamSerializer, VehicleListSerializer, ViolationMinimalSerializer, ViolationSerializer, VehicleSerializer, DriverSerializer, DriverAssignmentSerializer, ViolationSearchSerializer, BroadcastSerializer
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
from accounts.models import User
from rest_framework.exceptions import ValidationError
class HeartbeatPagination(PageNumberPagination):
    page_size = 1000
    page_size_query_param = "page_size"
    max_page_size = 1000

class DefaultPagination(PageNumberPagination):
    page_size = 500
    page_size_query_param = "page_size"
    max_page_size = 1000

from .serializers import ViolationFilterSerializer
from .gpsgate import send_violation_event, CONTRACTOR_USER_ID as GPSGATE_CONTRACTOR_ID

def _device_id_from_payload(payload):
    """Return the device UUID string from any supported payload shape, or 'unknown'."""
    if isinstance(payload, dict):
        d = payload.get("device") or payload.get("deviceId")
        if d:
            return d
        items = payload.get("data")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0].get("device") or items[0].get("deviceId") or "unknown"
    elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0].get("device") or payload[0].get("deviceId") or "unknown"
    return "unknown"

# ---------- Devices ----------

@extend_schema_view(
    list=extend_schema(
        tags=["Devices"],
        summary="List devices",
        description="List devices with optional filters: `uuid`, `type`, and `search` (matches name/uuid/type).",
        parameters=[
            OpenApiParameter(name="uuid", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="type", description="Filter by device type", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="search", description="Substring match on name/uuid/type", required=False, type=OpenApiTypes.STR),
        ],
        responses={200: DeviceSerializer(many=True)},
    ),

    retrieve=extend_schema(
        tags=["Devices"],
        summary="Get a device by ID",
        responses={200: DeviceSerializer},
    ),
    create=extend_schema(
        tags=["Devices"],
        summary="Create device(s)",
        description="Create a single device **or** bulk create with `{\"data\": [...]}` or raw JSON array.",
        request=DeviceSerializer,  # drf-spectacular will also accept lists via examples below
        responses={201: DeviceSerializer(many=False)},
        examples=[
            OpenApiExample(
                "Create single device",
                value={
                    "uuid": "123431",
                    "name": "tttt",
                    "type": "rrr",
                    "rearCameraUrl": "http",
                    "frontCameraUrl": "http",
                    "features": {
                        "camera": {
                            "front_camera": True,
                            "cabin_camera": True,
                            "right_camera": True,
                            "left_camera": True
                        },
                        "sensor": {
                            "fuel_sensor": True,
                            "gps_sensor": True,
                            "dellas_key_sensor": True
                        }
                    }
                },
            ),
            OpenApiExample(
                "Bulk create (wrapper with data)",
                value={
                    "data": [
                        {
                            "uuid": "ABC-1",
                            "name": "Truck 1",
                            "type": "rrr",
                            "rearCameraUrl": "http://rear-1",
                            "frontCameraUrl": "http://front-1",
                            "features": {}
                        },
                        {
                            "uuid": "ABC-2",
                            "name": "Truck 2",
                            "type": "rrr",
                            "rearCameraUrl": None,
                            "frontCameraUrl": None,
                            "features": {"sensor": {"gps_sensor": True}}
                        }
                    ]
                },
            ),
            OpenApiExample(
                "Bulk create (raw array)",
                value=[
                    {"uuid": "A-1", "name": "A", "type": "truck"},
                    {"uuid": "A-2", "name": "B", "type": "van"}
                ],
            ),
        ],
    ),
    update=extend_schema(
        tags=["Devices"],
        summary="Replace a device",
        request=DeviceSerializer,
        responses={200: DeviceSerializer},
    ),
    partial_update=extend_schema(
        tags=["Devices"],
        summary="Update a device (partial)",
        request=DeviceSerializer,
        responses={200: DeviceSerializer},
    ),
    destroy=extend_schema(
        tags=["Devices"],
        summary="Delete a device",
        responses={204: None},
    ),
)




class DeviceViewSet(viewsets.ModelViewSet):
    """
    CRUD for devices.
    - GET /api/devices/               (list, with filters)
    - POST /api/devices/              (create single or bulk)
    - GET /api/devices/{id}/          (retrieve)
    - PUT /api/devices/{id}/          (full update)
    - PATCH /api/devices/{id}/        (partial update)
    - DELETE /api/devices/{id}/       (delete)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DeviceSerializer
    queryset = Device.objects.all().order_by("-created_at")
 
    # Simple filtering & search
    def get_queryset(self):
        qs = super().get_queryset().select_related("vehicles__user_id")
 
        uuid = self.request.query_params.get("uuid")
        dtype = self.request.query_params.get("type")
        search = self.request.query_params.get("search")
 
        if uuid:
            qs = qs.filter(uuid=uuid)
        if dtype:
            qs = qs.filter(type=dtype)
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(uuid__icontains=search) |
                Q(type__icontains=search)
            )
 
        return qs
 
    # =========================================================================
    # BULK-AWARE CREATE: CSV Support with Debug Tracking
    # =========================================================================
    # Handles:
    # 1. Single object: {"name": "Device 1", "type": "test", ...}
    # 2. Raw list: [{"name": "Device 1"}, {"name": "Device 2"}]
    # 3. Wrapped list: {"data": [{"name": "Device 1"}, {"name": "Device 2"}]}
    #
    # CSV-Parsed Format (from React csvFeatureHandler):
    # {
    #   "name": "Device 1",
    #   "type": "test",
    #   "uuid": "12345",
    #   "sim": "SIM123",
    #   "rearCameraUrl": "http://...",
    #   "frontCameraUrl": "http://...",
    #   "features": {
    #     "frontCamera": true,
    #     "cabinCamera": true,
    #     ...
    #   }
    # }
    # =========================================================================
    def create(self, request, *args, **kwargs):
        print("\n" + "="*80)
        print("🔵 [CREATE] DeviceViewSet.create() called")
        print("="*80)
        
        payload = request.data
        
        # =====================================================
        # STEP 1: DETECT AND EXTRACT ITEMS
        # =====================================================
        print("\n📊 STEP 1: DETECT PAYLOAD FORMAT")
        print(f"  Payload type: {type(payload).__name__}")
        print(f"  Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'N/A (not dict)'}")
        
        # Support multiple payload formats
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            # Format: {"data": [...]}
            items = payload["data"]
            many = True
            print(f"  ✅ Detected format: WRAPPED LIST - {{'data': [...]}}")
            print(f"  📦 Found {len(items)} items in 'data' wrapper")
        elif isinstance(payload, list):
            # Format: [...]
            items = payload
            many = True
            print(f"  ✅ Detected format: RAW LIST")
            print(f"  📦 Found {len(items)} items")
        else:
            # Format: {...} (single object)
            items = payload
            many = isinstance(items, list)
            if many:
                print(f"  ✅ Detected format: SINGLE OBJECT that is a list")
            else:
                print(f"  ✅ Detected format: SINGLE OBJECT")
 
        # Ensure items_list is always a list for consistent processing
        items_list = items if isinstance(items, list) else [items]
        print(f"  📋 Processing {len(items_list)} device(s)")
 
        # =====================================================
        # STEP 2: NORMALIZE FEATURES STRUCTURE
        # =====================================================
        print("\n🔧 STEP 2: NORMALIZE FEATURES STRUCTURE")
        
        normalized_items = []
        
        for idx, item in enumerate(items_list):
            print(f"\n  Device #{idx}:")
            
            # Make a copy to avoid mutating original request data
            normalized_item = dict(item) if isinstance(item, dict) else {}
            print(f"    📝 Original keys: {list(normalized_item.keys())}")
            
            # Initialize features if missing
            if "features" not in normalized_item:
                print(f"    ⚠️  No 'features' field found - initializing empty dict")
                normalized_item["features"] = {}
            else:
                print(f"    ✅ Found 'features' field")
                print(f"       Type: {type(normalized_item['features']).__name__}")
                print(f"       Content: {json.dumps(normalized_item['features'], indent=8) if normalized_item['features'] else '{}'}")
            
            # Ensure features is a valid dict
            if not isinstance(normalized_item["features"], dict):
                print(f"    ⚠️  'features' is not a dict ({type(normalized_item['features']).__name__}) - resetting to {{}}")
                normalized_item["features"] = {}
            
            # Set default values for missing feature keys
            default_features = {
                "frontCamera": False,
                "cabinCamera": False,
                "rightCamera": False,
                "leftCamera": False,
                "rearCamera": False,
                "topCamera": False,
                "fuel": False,
                "gps": False,
                "dellasKey": False,
                "panicButton": False,
                "seatbelt": False,
                "ignition": False,
                "temperature": False,
                "immobilizer": False,
            }
            
            # Count provided features
            provided_features = {k: v for k, v in normalized_item["features"].items() if k in default_features}
            missing_features = [k for k in default_features.keys() if k not in normalized_item["features"]]
            
            print(f"    📊 Features provided: {len(provided_features)}/14")
            print(f"    📊 Features missing: {len(missing_features)}/14 - {missing_features if missing_features else 'None'}")
            
            # Merge: defaults + provided features (provided takes precedence)
            normalized_item["features"] = {**default_features, **normalized_item["features"]}
            
            print(f"    ✅ After normalization: {len(normalized_item['features'])} features total")
            print(f"       Features: {list(normalized_item['features'].keys())}")
            
            normalized_items.append(normalized_item)
 
        print(f"\n  ✅ All {len(normalized_items)} devices normalized successfully")
 
        # =====================================================
        # STEP 3: VALIDATE & SERIALIZE
        # =====================================================
        print("\n✔️  STEP 3: VALIDATE WITH SERIALIZER")
        
        serializer = self.get_serializer(data=normalized_items, many=True)
        print(f"  📋 Serializer initialized with many={True}")
        
        is_valid = serializer.is_valid(raise_exception=False)
        
        if is_valid:
            print(f"  ✅ Validation PASSED")
            print(f"  📊 Validated data for {len(serializer.validated_data)} device(s)")
            
            # Show sample of first device validated data
            if serializer.validated_data:
                first_device = serializer.validated_data[0]
                print(f"\n  Sample (Device #0):")
                print(f"    name: {first_device.get('name')}")
                print(f"    type: {first_device.get('type')}")
                print(f"    uuid: {first_device.get('uuid')}")
                print(f"    features keys: {list(first_device.get('features', {}).keys())}")
        else:
            print(f"  ❌ Validation FAILED")
            print(f"  Errors: {json.dumps(serializer.errors, indent=4)}")
            raise Exception(f"Serializer validation failed: {serializer.errors}")
 
        # =====================================================
        # STEP 4: ATOMIC TRANSACTION
        # =====================================================
        print("\n💾 STEP 4: SAVE TO DATABASE (ATOMIC TRANSACTION)")
        print(f"  ⏳ Starting transaction...")
        
        try:
            with transaction.atomic():
                print(f"  🔒 Transaction locked")
                
                self.perform_create(serializer)
                
                print(f"  ✅ perform_create() completed")
                print(f"  📊 {len(serializer.data)} device(s) saved successfully")
                
                # Show sample of created device
                if serializer.data:
                    first_saved = serializer.data[0]
                    print(f"\n  Sample (Device #0 - saved with ID):")
                    print(f"    id: {first_saved.get('id')}")
                    print(f"    name: {first_saved.get('name')}")
                    print(f"    type: {first_saved.get('type')}")
                    print(f"    uuid: {first_saved.get('uuid')}")
                    print(f"    features: {list(first_saved.get('features', {}).keys())}")
                
                print(f"  🔓 Transaction committed successfully")
        except Exception as e:
            print(f"  ❌ Transaction FAILED: {str(e)}")
            print(f"  🔄 Rolling back...")
            raise
 
        # =====================================================
        # STEP 5: RETURN RESPONSE
        # =====================================================
        print("\n📤 STEP 5: PREPARE RESPONSE")
        
        headers = self.get_success_headers(serializer.data)
        status_code = status.HTTP_201_CREATED
        
        print(f"  ✅ Status code: {status_code}")
        print(f"  📊 Response includes {len(serializer.data)} device(s)")
        
        print("\n" + "="*80)
        print("✅ [CREATE] Operation completed successfully!")
        print("="*80 + "\n")
        
        return Response(serializer.data, status=status_code, headers=headers)
 
    # =========================================================================
    # OPTIONAL: BULK UPDATE ENDPOINT
    # =========================================================================
    # If you want to support PUT/PATCH for multiple devices at once
    # uncomment this and wire it in your router with @action decorator
    # =========================================================================
    # @action(detail=False, methods=['put', 'patch'])
    # def bulk_update(self, request, *args, **kwargs):
    #     """
    #     Update multiple devices in a single request.
    #     
    #     Expected format:
    #     {
    #       "devices": [
    #         {"id": 1, "name": "Updated Device 1", ...},
    #         {"id": 2, "name": "Updated Device 2", ...}
    #       ]
    #     }
    #     """
    #     payload = request.data
    #     if isinstance(payload, dict) and "devices" in payload:
    #         devices_data = payload["devices"]
    #     else:
    #         return Response(
    #             {"error": "Expected format: {\"devices\": [...]}"},
    #             status=status.HTTP_400_BAD_REQUEST
    #         )
    #     
    #     updated_devices = []
    #     with transaction.atomic():
    #         for device_data in devices_data:
    #             device_id = device_data.get("id")
    #             try:
    #                 device = Device.objects.get(id=device_id)
    #                 serializer = self.get_serializer(
    #                     device, 
    #                     data=device_data, 
    #                     partial=(request.method == 'PATCH')
    #                 )
    #                 serializer.is_valid(raise_exception=True)
    #                 serializer.save()
    #                 updated_devices.append(serializer.data)
    #             except Device.DoesNotExist:
    #                 return Response(
    #                     {"error": f"Device with id {device_id} not found"},
    #                     status=status.HTTP_404_NOT_FOUND
    #                 )
    #     
    #     return Response(updated_devices, status=status.HTTP_200_OK)


# ---------- Events ----------

@extend_schema_view(
    list=extend_schema(
        tags=["Events"],
        summary="List events",
        description=(
            "List events with filters. "
            "`device_id` filters by device UUID (FK to `Device.uuid`). "
            "`from`/`to` filter by `logged_at` (ISO-8601). "
            "`search` matches `type` or `value`."
        ),
        parameters=[
            OpenApiParameter(name="device_id", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="type", description="Filter by event type", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="from", description="Start datetime (logged_at >= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to", description="End datetime (logged_at <= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="search", description="Substring match on type/value", required=False, type=OpenApiTypes.STR),
        ],
        responses={200: EventSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Events"],
        summary="Get an event by ID",
        responses={200: EventSerializer},
    ),
    create=extend_schema(
        tags=["Events"],
        summary="Create event(s)",
        description="Create a single event **or** bulk create with `{\"data\": [...]}` or raw JSON array.",
        request=EventSerializer,
        responses={201: EventSerializer},
        examples=[
            OpenApiExample(
                "Create single event",
                value={
                    "device_id": "123431",
                    "latitude": 24.8615,
                    "longitude": 67.0099,
                    "accuracy": 3.2,
                    "speed": 55.4,
                    "altitude": 15.0,
                    "logged_at": "2025-10-02T14:30:00Z",
                    "type": "gps_update",
                    "value": "OK"
                },
            ),
            OpenApiExample(
                "Bulk create (wrapper with data)",
                value={
                    "data": [
                        {
                            "device_id": "123431",
                            "logged_at": "2025-10-02T14:30:00Z",
                            "type": "gps_update",
                            "latitude": 24.8615,
                            "longitude": 67.0099
                        },
                        {
                            "device_id": "123431",
                            "logged_at": "2025-10-02T14:31:10Z",
                            "type": "speed",
                            "speed": 62.3
                        }
                    ]
                },
            ),
            OpenApiExample(
                "Bulk create (raw array)",
                value=[
                    {"device_id": "123431", "logged_at": "2025-10-02T14:32:00Z", "type": "ignition", "value": "ON"},
                    {"device_id": "123431", "logged_at": "2025-10-02T14:33:00Z", "type": "ignition", "value": "OFF"}
                ],
            ),
        ],
    ),
    update=extend_schema(
        tags=["Events"],
        summary="Replace an event",
        request=EventSerializer,
        responses={200: EventSerializer},
    ),
    partial_update=extend_schema(
        tags=["Events"],
        summary="Update an event (partial)",
        request=EventSerializer,
        responses={200: EventSerializer},
    ),
    destroy=extend_schema(
        tags=["Events"],
        summary="Delete an event",
        responses={204: None},
    ),
)
class EventViewSet(viewsets.ModelViewSet):
    """
    CRUD for events.

    - GET    /api/events/                           (list with filters)
    - POST   /api/events/                           (create single or bulk)
    - GET    /api/events/{id}/                      (retrieve)
    - PUT    /api/events/{id}/                      (full update)
    - PATCH  /api/events/{id}/                      (partial update)
    - DELETE /api/events/{id}/                      (delete)

    Filters:
      ?device_id=<uuid>
      ?type=<type>
      ?from=<iso-datetime>&to=<iso-datetime>   -> filters by logged_at range
      ?search=<text>                           -> type/value contains
    """
    permission_classes = [AllowAny]
    serializer_class = EventSerializer
    queryset = Event.objects.select_related("device").all().order_by("-logged_at", "-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device_id")
        etype = self.request.query_params.get("type")
        dt_from = self.request.query_params.get("from")
        dt_to = self.request.query_params.get("to")
        search = self.request.query_params.get("search")

        if device_id:
            qs = qs.filter(device__uuid=device_id)
        if etype:
            qs = qs.filter(type=etype)

        # logged_at range
        if dt_from:
            dfrom = parse_datetime(dt_from)
            if dfrom:
                qs = qs.filter( logged_at__gte=dfrom )
        if dt_to:
            dto = parse_datetime(dt_to)
            if dto:
                qs = qs.filter( logged_at__lte=dto )

        if search:
            qs = qs.filter(Q(type__icontains=search) | Q(value__icontains=search))

        return qs

    # Bulk-aware create: single object, raw list, or {"data": [...]}
    def create(self, request, *args, **kwargs):
        payload = request.data

        # normalize/translate incoming "time" -> "logged_at" for all supported payload shapes
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            raw = payload["data"]
            items = []
            for entry in raw:
                # only transform dict entries
                if isinstance(entry, dict) and "time" in entry:
                    entry = dict(entry)  # copy to avoid mutating original
                    entry["logged_at"] = entry.pop("time")
                items.append(entry)
            data = items
            many = True
        elif isinstance(payload, list):
            items = []
            for entry in payload:
                if isinstance(entry, dict) and "time" in entry:
                    entry = dict(entry)
                    entry["logged_at"] = entry.pop("time")
                items.append(entry)
            data = items
            many = True
        else:
            # single object case
            if isinstance(payload, dict) and "time" in payload:
                payload = dict(payload)
                payload["logged_at"] = payload.pop("time")
            data = payload
            many = isinstance(data, list)

        serializer = self.get_serializer(data=data, many=many)
        if not serializer.is_valid():
            logger.warning(
                "400 /api/events/ device=%s errors=%s",
                _device_id_from_payload(payload),
                serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            self.perform_create(serializer)

        return HttpResponse("true", content_type="text/plain")

# ---------- Heartbeats ----------

@extend_schema_view(
    list=extend_schema(
        tags=["Heartbeats"],
        summary="List heartbeats",
        description=(
            "List heartbeats with optional filters. "
            "`device_id` filters by device UUID (FK to `Device.uuid`). "
            "`from`/`to` filter by `logged_at` (ISO-8601)."
        ),
        parameters=[
            OpenApiParameter(name="device_id", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="from", description="Start datetime (logged_at >= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to", description="End datetime (logged_at <= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
        ],
        responses={200: HeartbeatSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Heartbeats"],
        summary="Get a heartbeat by ID",
        responses={200: HeartbeatSerializer},
    ),
    create=extend_schema(
        tags=["Heartbeats"],
        summary="Create heartbeat(s)",
        description=(
            "Create heartbeat(s). Supported payloads:\n\n"
            "1) Standard single object matching HeartbeatSerializer.\n"
            "2) Bulk standard: {\"data\": [ ... ]} or a raw JSON array of heartbeat objects.\n"
            "3) Compact device-level payload (preferred for devices sending many points):\n\n"
            "   {\n"
            "     \"device\": \"<device-uuid>\",\n"
            "     \"data\": [\n"
            "       {\"lat\": <latitude>, \"long\": <longitude>, \"time\": <ISO-datetime>, \"speed\": ..., \"altitude\": ..., \"bearing\": ...},\n            ...\n"
            "     ]\n\n"
            "Note: the compact format maps `lat`->latitude, `long`->longitude, `time`->logged_at. "
            "Other keys are copied where possible (speed, altitude, bearing, accuracy). Unknown keys (e.g. cabin/front) are ignored.\n\n"
            "Responses:\n"
            "- 201: plain text `heartbeats added successfully` (content-type: text/plain)\n"
            "- 400: validation error — for bulk requests only the first object's error is returned."
        ),
        request=HeartbeatSerializer,
        responses={
            201: OpenApiResponse(response=OpenApiTypes.STR, description="Plain text success message"),
            400: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Validation error (first object's error only)")
        },
        examples=[
            OpenApiExample(
                "Create single heartbeat (standard)",
                value={
                    "device": "123431",
                    "latitude": 24.8615,
                    "longitude": 67.0099,
                    "speed": 55.4,
                    "altitude": 15.0,
                    "logged_at": "2025-10-02T14:30:00Z"
                },
            ),
            # OpenApiExample(
            #     "Bulk create (wrapper with data, standard)",
            #     value={
            #         "data": [
            #             {
            #                 "device": "123431",
            #                 "logged_at": "2025-10-02T14:30:00Z",
            #                 "latitude": 24.8615,
            #                 "longitude": 67.0099,
            #             },
            #             {
            #                 "device": "123431",
            #                 "logged_at": "2025-10-02T14:31:10Z",
            #                 "speed": 62.3
            #             }
            #         ]
            #     },
            # ),
            # OpenApiExample(
            #     "Bulk create (raw array, standard)",
            #     value=[
            #         {"device": "123431", "logged_at": "2025-10-02T14:32:00Z", "speed": 10.5},
            #         {"device": "123431", "logged_at": "2025-10-02T14:33:00Z", "speed": 0.0}
            #     ],
            # ),
            OpenApiExample(
                "Compact device payload (frontend/devices)",
                value={
                    "device": "5",
                    "data": [
                        {
                          "lat": 0.0,
                          "long": 0.0,
                          "speed": 0,
                          "time": "2025-10-20T15:17:22+05:00",
                          "altitude": 100,
                          "bearing": 10,
                          "cabin": 1,
                          "front": 1
                        },
                        {
                          "lat": 0.0,
                          "long": 0.0,
                          "speed": 0,
                          "time": "2025-10-20T15:17:23+05:00",
                          "altitude": 100,
                          "bearing": 10,
                          "cabin": 1,
                          "front": 1
                        }
                    ]
                },
            ),
            OpenApiExample(
                "Validation error (example)",
                value={"latitude": ["This field is required."], "logged_at": ["Datetime is invalid."]},
            ),
        ],
    ),
    update=extend_schema(
        tags=["Heartbeats"],
        summary="Replace a heartbeat",
        request=HeartbeatSerializer,
        responses={200: HeartbeatSerializer},
    ),
    partial_update=extend_schema(
        tags=["Heartbeats"],
        summary="Update a heartbeat (partial)",
        request=HeartbeatSerializer,
        responses={200: HeartbeatSerializer},
    ),
    destroy=extend_schema(
        tags=["Heartbeats"],
        summary="Delete a heartbeat",
        responses={204: None},
    ),
)
class HeartbeatViewSet(viewsets.ModelViewSet):
    """
    CRUD for Heartbeat.
    Accepts device as uuid (slug).
    """
    queryset = Heartbeat.objects.select_related("device").all().order_by("-logged_at")
    serializer_class = HeartbeatSerializer
    permission_classes = [AllowAny]
    pagination_class = HeartbeatPagination

    def perform_create(self, serializer):
        if getattr(serializer, "many", False):
            objs = [Heartbeat(**attrs) for attrs in serializer.validated_data]
            Heartbeat.objects.bulk_create(objs, ignore_conflicts=True)
        else:
            serializer.save()

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device_id")
        dt_from = self.request.query_params.get("from")
        dt_to = self.request.query_params.get("to")

        if device_id:
            qs = qs.filter(device__uuid=device_id)

        # Filter by datetime range if provided
        if dt_from:
            dfrom = parse_datetime(dt_from)
            if dfrom:
                qs = qs.filter(logged_at__gte=dfrom)
        if dt_to:
            dto = parse_datetime(dt_to)
            if dto:
                qs = qs.filter(logged_at__lte=dto)

        return qs

    # Bulk-aware create: single object, raw list, or {"data": [...]}
    # Also accepts the frontend-friendly payload:
    # {
    #   "device": "<device-uuid-or-id>",
    #   "data": [
    #     {"lat": ..., "long": ..., "time": "...", "speed": ..., "altitude": ..., "bearing": ...},
    #     ...
    #   ]
    # }
    def create(self, request, *args, **kwargs):
        payload = request.data

        # Case: frontend compact format with top-level device + data list
        if (
            isinstance(payload, dict)
            and "device" in payload
            and "data" in payload
            and isinstance(payload["data"], list)
        ):
            device_val = payload["device"]
            raw_items = payload["data"]
            items = []
            for entry in raw_items:
                mapped = {"device": device_val}
                # map incoming short names to model fields
                if "lat" in entry:
                    mapped["latitude"] = entry.get("lat")
                if "long" in entry:
                    mapped["longitude"] = entry.get("long")
                if "time" in entry:
                    mapped["logged_at"] = entry.get("time")
                # pass through numeric optional fields if present
                for f in ("speed", "altitude", "bearing", "accuracy"):
                    if f in entry:
                        mapped[f] = entry.get(f)
                # optionally ignore unknown keys like 'cabin', 'front' etc.
                items.append(mapped)

            data = items
            many = True

        # Existing bulk formats: wrapper {"data":[...]} without device key, raw list, or single object
        elif isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            data = payload["data"]
            many = True
        elif isinstance(payload, list):
            data = payload
            many = True
        else:
            data = payload
            many = isinstance(data, list)

        serializer = self.get_serializer(data=data, many=many)
        # validate without raising so we can control error shape
        is_valid = serializer.is_valid()
        if not is_valid:
            errs = serializer.errors
            logger.warning(
                "400 /api/heartbeats/ device=%s errors=%s",
                _device_id_from_payload(payload),
                errs,
            )
            # for bulk, choose the first non-empty error object to return
            if many and isinstance(errs, list):
                first_error = {}
                for e in errs:
                    if e:
                        first_error = e
                        break
                # fallback to first element if all are empty
                if not first_error and errs:
                    first_error = errs[0]
                return Response(first_error, status=status.HTTP_400_BAD_REQUEST)
            # single object error
            return Response(errs, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            self.perform_create(serializer)

        # On success return only the required text message
        return HttpResponse("true", content_type="text/plain")


# ---------- Violations ----------

@extend_schema_view(
    list=extend_schema(
        tags=["Violations"],
        summary="List violations",
        description=(
            "List violations with optional filters. "
            "`device_id` filters by device UUID (FK to `Device.uuid`). "
            "`violation_type_id` filters by ViolationType id. "
            "`from`/`to` filter by `logged_at` (ISO-8601)."
        ),
        parameters=[
            OpenApiParameter(name="device_id", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="violation_type_id", description="Filter by violation type id", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="from", description="Start datetime (logged_at >= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to", description="End datetime (logged_at <= this) in ISO-8601", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="status", description="Filter by violation status", required=False, type=OpenApiTypes.STR),
        ],
                responses={
            201: OpenApiResponse(response=OpenApiTypes.STR, description="Plain text success message"),
            400: OpenApiResponse(response=OpenApiTypes.OBJECT, description="Validation error (first object's error only)")
        },
    ),
    retrieve=extend_schema(
        tags=["Violations"],
        summary="Get a violation by ID",
        responses={200: ViolationSerializer},
    ),
    create=extend_schema(
        tags=["Violations"],
        summary="Create violation(s)",
        description="Create a single violation **or** bulk create with `{\"data\": [...]}` or raw JSON array.",
        request=ViolationSerializer,
        responses={201: ViolationSerializer},
        examples=[
            OpenApiExample(
                "Create single violation",
                value={
                    "device_id": "123431",
                    "violation_type_id": 1,
                    "latitude": 24.8615,
                    "longitude": 67.0099,
                    "speed": 70.0,
                    "logged_at": "2025-10-02T14:30:00Z",
                    "driver_id": "driver-123",
                    "front_camera_video_file_name": "front-20251002.mp4",
                    "status": "new"
                },
            ),
                   OpenApiExample(
                "Compact device payload (frontend/devices)",
                value={
                    "device": "5",
                    "data": [
                        {
                          "lat": 0.0,
                          "long": 0.0,
                          "speed": 0,
                          "time": "2025-10-20T15:17:22+05:00",
                          "frontCameraVideoFileName": "front-20251020.mp4",
                            "cabinCameraVideoFileName": "cabine-20251020.mp4",
                            "driverId": "driver-001",
                            "violationTypeId": 2,
                 
                        
                        },
                        {
                            "lat": 0.0,
                            "long": 0.0,
                            "speed": 0,
                            "time": "2025-10-20T15:17:23+05:00",
                            "frontCameraVideoFileName": "front-20251020.mp4",
                            "cabinCameraVideoFileName": "cabine-20251020.mp4",
                            "driverId": "driver-001",
                            "violationTypeId": 3,
                        }
                     
                    ]
                },
            ),
            OpenApiExample(
                "Validation error (example)",
                value={"latitude": ["This field is required."], "logged_at": ["Datetime is invalid."]},
            ),
        ],
    ),
    update=extend_schema(
        tags=["Violations"],
        summary="Replace a violation",
        request=ViolationSerializer,
        responses={200: ViolationSerializer},
    ),
    partial_update=extend_schema(
        tags=["Violations"],
        summary="Update a violation (partial)",
        request=ViolationSerializer,
        responses={200: ViolationSerializer},
    ),
    destroy=extend_schema(
        tags=["Violations"],
        summary="Delete a violation",
        responses={204: None},
    ),
)

class ViolationViewSet(viewsets.ModelViewSet):
    """
    CRUD for Violation.
    Accepts device as uuid and violation_type_id as PK of ViolationType.
    """
    queryset = Violation.objects.select_related(
        "device", "violation_type_id", "violation_type_id__category"
    ).all().order_by("-logged_at")
    serializer_class = ViolationSerializer
    permission_classes = [AllowAny]
    pagination_class = DefaultPagination

    def perform_create(self, serializer):
        if getattr(serializer, "many", False):
            objs = [Violation(**attrs) for attrs in serializer.validated_data]
            Violation.objects.bulk_create(objs, ignore_conflicts=True)
        else:
            serializer.save()
    def get_serializer_class(self):
        if self.action == "search_dashboard":
            return ViolationDashboardSerializer
        return ViolationSerializer
    
    @extend_schema(
        tags=["Violations"],
        summary="Search violations",
        description=(
            "Search violations by optional filters. "
            "All fields are optional; omitted filters are ignored.\n\n"
            "**Filters:**\n"
            "- `startDate`, `endDate` (ISO 8601, applied to `logged_at`)\n"
            "- `status` (list of strings)\n"
            "- `userIds` (list of ints)\n"
            "- `vehicleIds` (list of ints)\n"
            "- `violationTypeIds` (list of ints)\n"
            "- `violationCategoryIds` (list of ints; joins via `violation_type.category`)\n\n"
            "- `limit` (optional int; limits result count, disables pagination if set)\n\n"            
            "Returns a paginated list of `Violation` records ordered by `logged_at` desc."
        ),
        request=ViolationSearchSerializer,
        responses={
            200: ViolationSerializer(many=True),
        },
        examples=[
            OpenApiExample(
                "Minimal (no filters)",
                value={},
                request_only=True
            ),
            OpenApiExample(
                "Full filter set",
                value={
                    "startDate": "2025-11-03 00:00:00+05:00",
                    "endDate": "2025-11-03 23:59:59+05:00",
                    "status": ["unevaluated", "truthy", "falsy"],
                    "userIds": [5],
                    "violationCategoryIds": [2],
                    "violationTypeIds": [7],
                    "vehicleIds": [216],
                     "limit": 50
                },
                request_only=True
            ),
            OpenApiExample(
                "Sample success response (paginated results item)",
                value=[{
                    "id": 123,
                    "device": "5b0c8b5e-9f1f-4e0a-a2c9-1b2c3d4e5f60",
                    "device_info": {
                        "uuid": "5b0c8b5e-9f1f-4e0a-a2c9-1b2c3d4e5f60",
                        "name": "UEPL-TRK-001",
                        "model": "X7",
                        "created_at": "2025-10-30T12:00:00+05:00"
                    },
                    "latitude": 24.860966,
                    "longitude": 66.990501,
                    "speed": 42.5,
                    "vehicle": 216,
                    "user": 5,
                    "accuracy": 1.2,
                    "altitude": 12.3,
                    "logged_at": "2025-11-03T15:17:22+05:00",
                    "created_at": "2025-11-03T15:18:00+05:00",
                    "violation_type_id": 7,
                    "violation_type": {
                        "id": 7,
                        "title": "Phone Usage",
                        "description": "Driver using mobile phone while driving",
                        "severity": 2,
                        "is_annotatable": True,
                        "category": {
                            "id": 2,
                            "violation_category_name": "Driver Distraction",
                            "description": "Distraction-related violations",
                            "created_at": "2025-10-01T10:00:00+05:00"
                        },
                        "created_at": "2025-10-10T10:00:00+05:00"
                    },
                    "front_camera_video_file_name": "front-20251103-151722.mp4",
                    "rear_camera_video_file_name": "null",
                    "left_camera_video_file_name": "null",
                    "right_camera_video_file_name": "null",
                    "cabin_camera_video_file_name": "cabin-20251103-151722.mp4",
                    "driver_id": "driver-001",
                    "meta": "null",
                    "status": "unevaluated"
                }],
                response_only=True
            ),
        ],
    )
    @action(methods=["POST"], detail=False, url_path="search")
    def search(self, request, *args, **kwargs):
        """
        POST /api/violations/search/
        {
            "startDate":"2025-11-03 00:00:00+05:00",
            "endDate":"2025-11-03 23:59:59+05:00",
            "status":["unevaluated","truthy","falsy"],
            "userIds":[5],
            "violationCategoryIds":[2],
            "violationTypeIds":[7],
            "vehicleIds":[216]
        }
        """
        s = ViolationSearchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        qs = self.get_queryset()

        # Date range on logged_at
        if v.get("startDate"):
            qs = qs.filter(logged_at__gte=v["startDate"])
        if v.get("endDate"):
            qs = qs.filter(logged_at__lte=v["endDate"])

        # status[]
        if v.get("status"):
            qs = qs.filter(status__in=v["status"])

        # userIds[]
        if v.get("userIds"):
            qs = qs.filter(user_id__in=v["userIds"])

        # vehicleIds[]
        if v.get("vehicleIds"):
            qs = qs.filter(vehicle_id__in=v["vehicleIds"])

        # violationTypeIds[]
        if v.get("violationTypeIds"):
            qs = qs.filter(violation_type_id__in=v["violationTypeIds"])

        # violationCategoryIds[] (join via ViolationType.category)
        if v.get("violationCategoryIds"):
            qs = qs.filter(violation_type_id__category_id__in=v["violationCategoryIds"])
        
        # Frontend expects a flat array. Respect explicit limit; default to 1000.
        limit = v.get("limit", 1000)
        ser = self.get_serializer(qs[:limit], many=True)
        return Response(ser.data, status=status.HTTP_200_OK)
    
    @action(methods=["POST"], detail=False, url_path="search/dashboard")
    def search_dashboard(self, request, *args, **kwargs):
        s = ViolationSearchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        qs = (
            self.get_queryset()
            .select_related(
                "device",
                "vehicle__user_id",
                "violation_type_id__category",
                "user",
            )
            # Skip columns not used by ViolationDashboardSerializer
            .defer(
                "latitude", "longitude", "accuracy", "altitude",
                "rear_camera_video_file_name", "left_camera_video_file_name",
                "right_camera_video_file_name", "driver_id", "meta",
            )
        )

        if v.get("startDate"):
            qs = qs.filter(logged_at__gte=v["startDate"])

        if v.get("endDate"):
            qs = qs.filter(logged_at__lte=v["endDate"])

        if v.get("status"):
            qs = qs.filter(status__in=v["status"])

        if v.get("userIds"):
            qs = qs.filter(user_id__in=v["userIds"])

        if v.get("vehicleIds"):
            qs = qs.filter(vehicle_id__in=v["vehicleIds"])

        if v.get("violationTypeIds"):
            qs = qs.filter(violation_type_id__in=v["violationTypeIds"])

        if v.get("violationCategoryIds"):
            qs = qs.filter(violation_type_id__category_id__in=v["violationCategoryIds"])

        # Frontend expects a flat array. Respect explicit limit; default to 1000.
        limit = v.get("limit", 1000)
        serializer = ViolationDashboardSerializer(qs[:limit], many=True)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False, url_path="severe-violation")
    def severe_violation(self, request, *args, **kwargs):
        violation_id = request.data.get("violation_id")
        annotated_by_id = request.data.get("annotated_by")
        status_val = request.data.get("status", "true")

        if not violation_id:
            return Response(
                {"detail": "violation_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():

                violation = Violation.objects.select_related("violation_type_id").get(id=violation_id)

                # ensure only Severe Drowsy
                if violation.violation_type_id.title != "Severe Drowsy":
                    return Response(
                        {"detail": "Only Severe Drowsy can be converted"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 🔥 DIRECT CHANGE TO MOBILE (ID = 10 from your dataset)
                violation.violation_type_id_id = 10

                # update status
                violation.status = status_val

                violation.save(update_fields=["violation_type_id", "status"])

                # annotation log
                if annotated_by_id:
                    ViolationAnnotation.objects.create(
                        violation=violation,
                        annotated_by_id=annotated_by_id,
                        status=status_val,
                        comment="Severe Drowsy → Mobile (auto converted)"
                    )

            return Response(
                {
                    "success": True,
                    "message": "Violation converted to Mobile",
                    "violation_id": violation.id,
                    "new_type": "Mobile"
                },
                status=status.HTTP_200_OK
            )

        except Violation.DoesNotExist:
            return Response(
                {"detail": "Violation not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(methods=["POST"], detail=False, url_path="severe-drowsy-fix")
    def severe_drowsy_fix(self, request, *args, **kwargs):
        violation_id = request.data.get("violation_id")
        annotated_by_id = request.data.get("annotated_by")

        if not violation_id:
            return Response(
                {"detail": "violation_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                violation = Violation.objects.select_related("violation_type_id").get(id=violation_id)

                # Revert back to Severe Drowsy (ID = 7)
                violation.violation_type_id_id = 7
                violation.status = "true"
                violation.save(update_fields=["violation_type_id", "status"])

                if annotated_by_id:
                    ViolationAnnotation.objects.create(
                        violation=violation,
                        annotated_by_id=annotated_by_id,
                        status="true",
                        comment="Mobile → Severe Drowsy (fix applied)"
                    )

            return Response(
                {
                    "success": True,
                    "message": "Violation reverted to Severe Drowsy",
                    "violation_id": violation.id,
                    "new_type": "Severe Drowsy"
                },
                status=status.HTTP_200_OK
            )

        except Violation.DoesNotExist:
            return Response(
                {"detail": "Violation not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(methods=["POST"], detail=False, url_path="search/filter")
    def search_filter(self, request, *args, **kwargs):
        s = ViolationSearchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        qs = (
            self.get_queryset()
            .select_related(
                "device",
                "vehicle",
                "vehicle__user_id",
                "violation_type_id__category",
                "user",
            )
        )

        if v.get("startDate"):
            qs = qs.filter(logged_at__gte=v["startDate"])

        if v.get("endDate"):
            qs = qs.filter(logged_at__lte=v["endDate"])

        # user/manager roles may only see confirmed (true) violations
        if v.get("role") in ("user", "manager"):
            qs = qs.filter(status="true")
        elif v.get("status"):
            qs = qs.filter(status__in=v["status"])

        if v.get("userIds"):
            qs = qs.filter(user_id__in=v["userIds"])

        if v.get("vehicleIds"):
            qs = qs.filter(vehicle_id__in=v["vehicleIds"])

        if v.get("violationTypeIds"):
            qs = qs.filter(violation_type_id__in=v["violationTypeIds"])

        if v.get("violationCategoryIds"):
            qs = qs.filter(violation_type_id__category_id__in=v["violationCategoryIds"])

        paginator = DefaultPagination()
        paginated_qs = paginator.paginate_queryset(qs, request)
        serializer = ViolationFilterSerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)
    @action(methods=["POST"], detail=False, url_path="search/csv")
    def search_csv(self, request, *args, **kwargs):
        s = ViolationSearchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        qs = (
            self.get_queryset()
            .select_related(
                "device",
                "vehicle",
                "vehicle__user_id",
                "violation_type_id__category",
                "user",
            )
        )

        # --------------------
        # SAME FILTER LOGIC
        # --------------------
        if v.get("startDate"):
            qs = qs.filter(logged_at__gte=v["startDate"])

        if v.get("endDate"):
            qs = qs.filter(logged_at__lte=v["endDate"])

        if v.get("role") in ("user", "manager"):
            qs = qs.filter(status="true")
        elif v.get("status"):
            qs = qs.filter(status__in=v["status"])

        if v.get("userIds"):
            qs = qs.filter(user_id__in=v["userIds"])

        if v.get("vehicleIds"):
            qs = qs.filter(vehicle_id__in=v["vehicleIds"])

        if v.get("violationTypeIds"):
            qs = qs.filter(violation_type_id__in=v["violationTypeIds"])

        if v.get("violationCategoryIds"):
            qs = qs.filter(
                violation_type_id__category_id__in=v["violationCategoryIds"]
            )

        # --------------------
        # 🚨 NO PAGINATION HERE
        # --------------------
        serializer = ViolationFilterSerializer(qs, many=True)

        return Response({
            "count": qs.count(),
            "results": serializer.data
        })

    def create(self, request, *args, **kwargs):
        payload = request.data

        def normalize_entry(entry, top_device=None):
            if not isinstance(entry, dict):
                return entry
            mapped = dict(entry)  # copy to avoid mutating original keys

            # compact frontend keys -> model fields
            if "lat" in mapped:
                mapped["latitude"] = mapped.pop("lat")
            if "long" in mapped:
                mapped["longitude"] = mapped.pop("long")
            if "time" in mapped:
                mapped["logged_at"] = mapped.pop("time")
            if "deviceId" in mapped:
                mapped["device"] = mapped.pop("deviceId")
            if "violationTypeId" in mapped:
                mapped["violation_type_id"] = mapped.pop("violationTypeId")
            # accept either 'device' or top-level device
            if "frontCameraVideoFileName" in mapped:
                mapped["front_camera_video_file_name"] = mapped.pop("frontCameraVideoFileName")
            if "rearCameraVideoFileName" in mapped:
                mapped["rear_camera_video_file_name"] = mapped.pop("rearCameraVideoFileName")
            if "leftCameraVideoFileName" in mapped:
                mapped["left_camera_video_file_name"] = mapped.pop("leftCameraVideoFileName")
            if "rightCameraVideoFileName" in mapped:
                mapped["right_camera_video_file_name"] = mapped.pop("rightCameraVideoFileName")
            if "cabinCameraVideoFileName" in mapped:
                mapped["cabin_camera_video_file_name"] = mapped.pop("cabinCameraVideoFileName")
            if top_device is not None and "device" not in mapped:
                mapped["device"] = top_device

            return mapped

        # Support compact payload with top-level device + data list
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            top_device = payload.get("device") or payload.get("deviceId")
            items = [normalize_entry(e, top_device=top_device) for e in payload["data"]]
            data = items
            many = True
        # raw list
        elif isinstance(payload, list):
            items = [normalize_entry(e) for e in payload]
            data = items
            many = True
        else:
            # single object
            if isinstance(payload, dict):
                data = normalize_entry(payload)
            else:
                data = payload
            many = isinstance(data, list)

        # Populate vehicle and user from Vehicle table using device uuid (one bulk query)
        try:
            if many and isinstance(data, list):
                device_uuids = {
                    e["device"] for e in data
                    if isinstance(e, dict) and e.get("device") is not None
                }
                if device_uuids:
                    # Vehicle has OneToOneField to Device so at most 1 vehicle per uuid
                    vehicle_map = {
                        v.device_id: v
                        for v in Vehicle.objects
                            .filter(device__uuid__in=device_uuids)
                            .select_related("user_id")
                    }
                else:
                    vehicle_map = {}

                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    device_val = entry.get("device")
                    if device_val and device_val in vehicle_map:
                        v = vehicle_map[device_val]
                        if entry.get("vehicle") is None:
                            entry["vehicle"] = v.id
                        if entry.get("user") is None:
                            entry["user"] = v.user_id_id  # direct FK column, no extra query
            else:
                if isinstance(data, dict):
                    device_val = data.get("device")
                    if device_val:
                        try:
                            v = Vehicle.objects.select_related("user_id").get(device__uuid=device_val)
                            if data.get("vehicle") is None:
                                data["vehicle"] = v.id
                            if data.get("user") is None:
                                data["user"] = v.user_id_id
                        except Vehicle.DoesNotExist:
                            pass
        except Exception as e:
            logger.warning("Error during vehicle/user population: %s", e)

        serializer = self.get_serializer(data=data, many=many)
        if not serializer.is_valid():
            logger.warning(
                "400 /api/violations/ device=%s errors=%s",
                _device_id_from_payload(payload),
                serializer.errors,
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            self.perform_create(serializer)

        # On success return only the required text message
        return HttpResponse("true", content_type="text/plain")
    
    # Override partial_update to handle status update and create ViolationAnnotation
    def partial_update(self, request, *args, **kwargs):
        # PATCH: update status in Violation, then create ViolationAnnotation
        instance = self.get_object()
        status_val = request.data.get("status")
        annotated_by_id = request.data.get("user_id") or request.data.get("annotated_by")
        comment_val = request.data.get("comment")

        # Only update status in Violation
        if status_val is not None:
            instance.status = status_val
            instance.save(update_fields=["status"])

        # Create ViolationAnnotation
        if annotated_by_id and status_val:
            ViolationAnnotation.objects.create(
                violation=instance,
                annotated_by_id=annotated_by_id,
                status=status_val,
                comment=comment_val
            )

        # Fire GPSGate event for DP World Karachi violations confirmed as true
        if status_val == "true" and instance.user_id == GPSGATE_CONTRACTOR_ID:
            threading.Thread(
                target=send_violation_event,
                args=(instance,),
                daemon=True,
            ).start()

        # serializer = self.get_serializer(instance)
        return HttpResponse("true", content_type="text/plain")

    @extend_schema(
        tags=["Violations"],
        summary="Get violation annotation history",
        description="Fetch all annotations for a given violation ID, or all violations annotated by a specific user in the last 24 hours",
        parameters=[
            OpenApiParameter(name="violation_id", description="Violation ID (optional if annotator_id provided)", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="annotator_id", description="Filter by annotator user ID - returns violations annotated by this user in last 24 hours", required=False, type=OpenApiTypes.INT),
        ],
        responses={200: OpenApiResponse(description="List of annotations")},
        examples=[
            OpenApiExample(
                "Get annotations for a specific violation",
                value={
                    "violation_id": 123
                },
                request_only=True
            ),
            OpenApiExample(
                "Get violations annotated by user in last 24 hours",
                value={
                    "annotator_id": 5
                },
                request_only=True
            ),
            OpenApiExample(
                "Sample response",
                value=[
                    {
                        "id": 1,
                        "violation_id": 123,
                        "annotated_by_id": 5,
                        "annotated_by": "john_doe",
                        "status": "reviewed",
                        "comment": "Violation confirmed",
                        "created_at": "2025-11-06T10:30:00Z"
                    },
                    {
                        "id": 2,
                        "violation_id": 124,
                        "annotated_by_id": 5,
                        "annotated_by": "john_doe",
                        "status": "approved",
                        "comment": "Action taken",
                        "created_at": "2025-11-06T11:15:00Z"
                    }
                ],
                response_only=True
            ),
        ],
    )
    @action(methods=["GET"], detail=False, url_path="annotation-history")
    def annotation_history(self, request, *args, **kwargs):
        """
        GET /api/violations/annotation-history/?violation_id=123
        or
        GET /api/violations/annotation-history/?annotator_id=5
        
        Returns all ViolationAnnotation records for:
        - A specific violation (if violation_id provided)
        - All violations annotated by a user in last 24 hours (if annotator_id provided)
        """
        violation_id = request.query_params.get("violation_id")
        annotator_id = request.query_params.get("annotator_id")

        # Either violation_id or annotator_id must be provided
        if not violation_id and not annotator_id:
            return Response(
                {"detail": "Either violation_id or annotator_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Case 1: Get annotations for a specific violation
        if violation_id:
            try:
                violation = Violation.objects.get(id=violation_id)
            except Violation.DoesNotExist:
                return Response(
                    {"detail": "Violation not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            annotations = ViolationAnnotation.objects.filter(
                violation_id=violation_id
            ).select_related("annotated_by", "violation__violation_type_id").order_by("-created_at")

        # Case 2: Get all violations annotated by a specific user in last 24 hours
        elif annotator_id:
            threshold = timezone.now() - timedelta(hours=24)
            # Evaluate once ([:50] + list()) — avoids the exists() + iteration double-query
            annotations = list(
                ViolationAnnotation.objects
                .filter(annotated_by_id=annotator_id, created_at__gte=threshold)
                .select_related("annotated_by", "violation__violation_type_id")
                .order_by("-created_at")[:50]
            )

            if not annotations:
                return Response([], status=status.HTTP_200_OK)

        # Serialize the annotations — single list comprehension, no repeated attribute access
        data = [
            {
                "id": a.id,
                "violation_id": a.violation_id,
                "violation_type": a.violation.violation_type_id.title if a.violation else None,
                "annotated_by_id": a.annotated_by_id,
                "annotated_by": a.annotated_by.username if a.annotated_by else None,
                "status": a.status,
                "comment": a.comment,
                "created_at": a.created_at,
            }
            for a in annotations
        ]
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Violations"],
        summary="Get count of violations in last 6 hours with NULL status",
        description="Returns count of violations from the last 6 hours that have status=NULL",
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Count of violations",
                examples=[
                    OpenApiExample(
                        "Success response",
                        value={"count": 42},
                        response_only=True
                    )
                ]
            ),
        },
    )
    @action(methods=["GET"], detail=False, url_path="count-pending")
    def count_pending(self, request, *args, **kwargs):
        """
        GET /api/violations/count-pending/
        
        Returns count of violations from the last 6 hours with status=NULL
        """
        six_hours_ago = timezone.now() - timedelta(hours=6)
        
        count = Violation.objects.filter(
            logged_at__gte=six_hours_ago,
            status__isnull=True
        ).count()
        
        return Response({"count": count}, status=status.HTTP_200_OK)

# ---------- Vehicles ----------

@extend_schema_view(
    list=extend_schema(
        tags=["Vehicles"],
        summary="List vehicles",
        description="List vehicles with optional filters: `device_id`, `user_id`, and `search` (matches name/ID).",
        parameters=[
            OpenApiParameter(name="device_id", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="user_id", description="Filter by user ID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="search", description="Substring match on name/ID", required=False, type=OpenApiTypes.STR),
        ],
        responses={200: VehicleSerializer(many=True)},
    ),

    retrieve=extend_schema(
        tags=["Vehicles"],
        summary="Get a vehicle by ID",
        responses={200: VehicleSerializer},
    ),
    create=extend_schema(
        tags=["Vehicles"],
        summary="Create vehicle(s)",
        description="Create a single vehicle or bulk create with `{\"data\": [...]}` or raw JSON array.",
        request=VehicleSerializer,
        responses={201: VehicleSerializer},
        examples=[
            OpenApiExample(
                "Create single vehicle",
                value={
                    "device": "ABC-UUID-1",
                    "user_id": 12,
                    "name": "Truck 1",
                    "registration_number": "REG-001",
                    "type": "truck"
                },
            ),
            OpenApiExample(
                "Bulk create (wrapper with data)",
                value={
                    "data": [
                        {
                            "device": "ABC-UUID-1",
                            "user_id": 12,
                            "name": "Truck 1",
                            "registration_number": "REG-001",
                            "type": "truck"
                        },
                        {
                            "device": "ABC-UUID-2",
                            "user_id": 13,
                            "name": "Truck 2",
                            "registration_number": "REG-002",
                            "type": "van"
                        }
                    ]
                },
            ),
            OpenApiExample(
                "Bulk create (raw array)",
                value=[
                    {"device": "ABC-UUID-1", "user_id": 12, "name": "A", "registration_number": "REG-001", "type": "truck"},
                    {"device": "ABC-UUID-2", "user_id": 13, "name": "B", "registration_number": "REG-002", "type": "van"}
                ],
            ),
        ],
    ),
    update=extend_schema(
        tags=["Vehicles"],
        summary="Replace a vehicle",
        request=VehicleSerializer,
        responses={200: VehicleSerializer},
    ),
    partial_update=extend_schema(
        tags=["Vehicles"],
        summary="Update a vehicle (partial)",
        request=VehicleSerializer,
        responses={200: VehicleSerializer},
    ),
    destroy=extend_schema(
        tags=["Vehicles"],
        summary="Delete a vehicle",
        responses={204: None},
    ),
)
class VehicleViewSet(viewsets.ModelViewSet):
    """
    CRUD for Vehicle.

    - GET    /api/devices/vehicles/            (list with optional filters)
    - POST   /api/devices/vehicles/            (create)
    - GET    /api/devices/vehicles/{id}/       (retrieve)
    - PUT/PATCH/DELETE as usual
    """
    permission_classes = [IsAuthenticated]
    serializer_class = VehicleSerializer

    def get_queryset(self):
        # Base queryset
        qs = Vehicle.objects.select_related("device", "user_id")

        # ---- Annotate latest heartbeat fields (1 query for list & retrieve) ----
        latest_hb = (
            Heartbeat.objects
            .filter(device=OuterRef("device"))
            .order_by("-logged_at")
        )
        qs = qs.annotate(
                 latest_logged_at=Subquery(latest_hb.values("logged_at")[:1]),
        latest_latitude=Subquery(latest_hb.values("latitude")[:1]),
        latest_longitude=Subquery(latest_hb.values("longitude")[:1]),
        latest_speed=Subquery(latest_hb.values("speed")[:1]),
        latest_altitude=Subquery(latest_hb.values("altitude")[:1]),
        latest_bearing=Subquery(latest_hb.values("bearing")[:1]),
            
        )

        # Derive today_* from latest_* using Case/When — eliminates 3 correlated subqueries
        today = timezone.localdate()
        qs = qs.annotate(
            today_logged_at=Case(
                When(latest_logged_at__date=today, then=F("latest_logged_at")),
                default=None,
                output_field=DateTimeField(),
            ),
            today_latitude=Case(
                When(latest_logged_at__date=today, then=F("latest_latitude")),
                default=None,
                output_field=DecimalField(max_digits=9, decimal_places=6),
            ),
            today_longitude=Case(
                When(latest_logged_at__date=today, then=F("latest_longitude")),
                default=None,
                output_field=DecimalField(max_digits=9, decimal_places=6),
            ),
        ).order_by("-created_at")

        # ---- Access control: restrict to allowed contractors ----
        from accounts.permissions import get_allowed_contractor_ids
        allowed_ids = get_allowed_contractor_ids(self.request.user)
        if allowed_ids is not None:  # None = admin/unrestricted
            qs = qs.filter(user_id__in=allowed_ids)

        # ---- Optional filters ----
        device_id = self.request.query_params.get("device_id")
        user_id = self.request.query_params.get("user_id")
        if device_id:
            qs = qs.filter(device__uuid=device_id)
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs

    # Bulk-aware create: supports single object, raw list, or {"data": [...]} wrapper
    def create(self, request, *args, **kwargs):
        payload = request.data
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            items = payload["data"]
            many = True
        elif isinstance(payload, list):
            items = payload
            many = True
        else:
            items = payload
            many = isinstance(items, list)

        serializer = self.get_serializer(data=items, many=many)
        serializer.is_valid(raise_exception=True)
        
        try:
            with transaction.atomic():
                self.perform_create(serializer)
        except IntegrityError as e:
            # Handle UNIQUE constraint violations
            error_message = str(e)
            
            if "device_id" in error_message:
                return Response(
                    {
                        "error": "Device already assigned",
                        "detail": "This device is already associated with another vehicle. One device can only be mapped to one vehicle.",
                        "field": "device"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Generic integrity error
                return Response(
                    {
                        "error": "Data integrity error",
                        "detail": "The data violates database constraints. Please check your input.",
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        headers = self.get_success_headers(serializer.data if not many else [])
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    @action(detail=False, methods=["get"], url_path="list")
    def list_simple(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # You can reuse filters if needed
        device_id = request.query_params.get("device_id")
        user_id = request.query_params.get("user_id")

        if device_id:
            qs = qs.filter(device__uuid=device_id)
        if user_id:
            qs = qs.filter(user_id=user_id)

        serializer = VehicleListSerializer(qs, many=True)
        return Response(serializer.data)


    

    @action(detail=False, methods=["get"], url_path="map")
    def map_simple(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # You can reuse filters if needed
        device_id = request.query_params.get("device_id")
        user_id = request.query_params.get("user_id")

        if device_id:
            qs = qs.filter(device__uuid=device_id)
        if user_id:
            qs = qs.filter(user_id=user_id)

        serializer = VehicleMapSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="cam")
    def cam_simple(self, request, *args, **kwargs):
        qs = self.get_queryset()

        # You can reuse filters if needed
        device_id = request.query_params.get("device_id")
        user_id = request.query_params.get("user_id")

        if device_id:
            qs = qs.filter(device__uuid=device_id)
        if user_id:
            qs = qs.filter(user_id=user_id)

        serializer = VehicleCamSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="multiple-users")
    def multiple_users_vehicles(self, request):
        user_ids = request.data.get("user_ids", [])
        if not isinstance(user_ids, list) or not all(isinstance(i, int) for i in user_ids):
            return Response({"error": "user_ids must be a list of integers"}, status=400)

        if not user_ids:
            return Response([], status=200)

        latest_hb = Heartbeat.objects.filter(device=OuterRef('device')).order_by('-logged_at')

        vehicles = Vehicle.objects.select_related("device", "user_id").filter(user_id__in=user_ids).annotate(
            latest_logged_at=Subquery(latest_hb.values('logged_at')[:1]),
            latest_latitude=Subquery(latest_hb.values('latitude')[:1]),
            latest_longitude=Subquery(latest_hb.values('longitude')[:1]),
            latest_speed=Subquery(latest_hb.values('speed')[:1]),
            latest_altitude=Subquery(latest_hb.values('altitude')[:1]),
            latest_bearing=Subquery(latest_hb.values('bearing')[:1]),
        )

        serializer = MultipleUserVehicleSerializer(vehicles, many=True)
        return Response(serializer.data)

@extend_schema_view(
    list=extend_schema(
        tags=["Drivers"],
        summary="List drivers",
        description="List drivers. Supports filtering by user_id, email, phone and search (name/email/cnic).",
        parameters=[
            OpenApiParameter(name="user_id", description="Filter by user PK", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="email", description="Filter by email (exact)", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="phone", description="Filter by phone (substring)", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="search", description="Search name/email/cnic_number", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page", description="Page number", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="page_size", description="Page size", required=False, type=OpenApiTypes.INT),
        ],
        responses={200: OpenApiResponse(response=OpenApiTypes.OBJECT, description="List of drivers",)},
    ),
    retrieve=extend_schema(
        tags=["Drivers"],
        summary="Get a driver by ID",
        responses={200: DriverSerializer},
    ),
    create=extend_schema(
        tags=["Drivers"],
        summary="Create driver(s)",
        description="Create a single driver or bulk create with `{\"data\": [...]}` or raw JSON array.",
        request=DriverSerializer,
        responses={201: DriverSerializer},
        examples=[
            OpenApiExample(
                "Create driver",
                value={
                    "user_id": 12,
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "phone_number": "+923001234567",
                    "cnic_number": "12345-1234567-1",
                    "dob": "1985-01-01"
                },
            ),
            OpenApiExample(
                "Bulk create (wrapper with data)",
                value={
                    "data": [
                        {
                            "user_id": 12,
                            "name": "John Doe",
                            "email": "john.doe@example.com",
                            "phone_number": "+923001234567",
                            "cnic_number": "12345-1234567-1",
                            "dob": "1985-01-01"
                        },
                        {
                            "user_id": 13,
                            "name": "Jane Smith",
                            "email": "jane.smith@example.com",
                            "phone_number": "+923001111111",
                            "cnic_number": "98765-7654321-0",
                            "dob": "1990-05-10"
                        }
                    ]
                },
            ),
            OpenApiExample(
                "Bulk create (raw array)",
                value=[
                    {"user_id": 12, "name": "A", "email": "a@example.com", "phone_number": "+923001234567", "cnic_number": "12345-1234567-1", "dob": "1985-01-01"},
                    {"user_id": 13, "name": "B", "email": "b@example.com", "phone_number": "+923009999999", "cnic_number": "98765-7654321-0", "dob": "1991-02-02"}
                ],
            ),
        ],
    ),
    update=extend_schema(
        tags=["Drivers"],
        summary="Replace a driver",
        request=DriverSerializer,
        responses={200: DriverSerializer},
    ),
    partial_update=extend_schema(
        tags=["Drivers"],
        summary="Partially update a driver",
        request=DriverSerializer,
        responses={200: DriverSerializer},
    ),
    destroy=extend_schema(
        tags=["Drivers"],
        summary="Delete a driver",
        responses={204: None},
    ),
)
class DriverViewSet(viewsets.ModelViewSet):
    """
    CRUD for Driver.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DriverSerializer
    queryset = Driver.objects.select_related("user_id").all().order_by("-id")

    def get_queryset(self):
        qs = super().get_queryset()

        # Access control: restrict to allowed contractors
        from accounts.permissions import get_allowed_contractor_ids
        allowed_ids = get_allowed_contractor_ids(self.request.user)
        if allowed_ids is not None:  # None = admin/unrestricted
            qs = qs.filter(user_id__in=allowed_ids)

        user_id = self.request.query_params.get("user_id")
        email = self.request.query_params.get("email")
        phone = self.request.query_params.get("phone")
        search = self.request.query_params.get("search")

        if user_id:
            qs = qs.filter(user_id=user_id)
        if email:
            qs = qs.filter(email__iexact=email)
        if phone:
            qs = qs.filter(phone_number__icontains=phone)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search) | Q(cnic_number__icontains=search))
        return qs

    # Bulk-aware create: supports single object, raw list, or {"data": [...]} wrapper
    def create(self, request, *args, **kwargs):
        payload = request.data

        # -------------------------
        # Normalize input structure
        # -------------------------
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            items = payload["data"]
            many = True
        elif isinstance(payload, list):
            items = payload
            many = True
        else:
            items = [payload]
            many = False

        # -------------------------
        # Resolve user_id per item
        # -------------------------
        for item in items:
            user = item.get("user_id")

            if isinstance(user, str):
                user_obj = User.objects.filter(username=user).first()

                if not user_obj:
                    raise ValidationError(f"User '{user}' not found")

                item["user_id"] = user_obj.id   # IMPORTANT: assign FK id

        # -------------------------
        # Serialize
        # -------------------------
        serializer = self.get_serializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

# ---------- DriverAssignments ----------
@extend_schema_view(
    list=extend_schema(
        tags=["DriverAssignments"],
        summary="List driver assignments",
        description="List driver assignments. Filters: device_id (device.uuid), vehicle_id, driver_id, assigned_at range.",
        parameters=[
            OpenApiParameter(name="device_id", description="Filter by device UUID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="vehicle_id", description="Filter by vehicle id", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="driver_id", description="Filter by driver id", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="from", description="Assigned from (ISO-8601)", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to", description="Assigned to (ISO-8601)", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="page", description="Page number", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="page_size", description="Page size", required=False, type=OpenApiTypes.INT),
        ],
        responses={200: DriverAssignmentSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["DriverAssignments"],
        summary="Get a driver assignment by ID",
        responses={200: DriverAssignmentSerializer},
    ),
    create=extend_schema(
        tags=["DriverAssignments"],
        summary="Create a driver assignment",
        request=DriverAssignmentSerializer,
        responses={201: DriverAssignmentSerializer},
        examples=[
            OpenApiExample(
                "Create assignment",
                value={
                    "driver": 3,
                    "vehicle": 5,
                    "device": "device-uuid-123",
                    "latitude": 24.8615,
                    "longitude": 67.0099,
                    "speed": 0.0,
                    "assigned_at": "2025-10-20T10:00:00Z"
                },
            ),
        ],
    ),
    update=extend_schema(
        tags=["DriverAssignments"],
        summary="Replace a driver assignment",
        request=DriverAssignmentSerializer,
        responses={200: DriverAssignmentSerializer},
    ),
    partial_update=extend_schema(
        tags=["DriverAssignments"],
        summary="Partially update a driver assignment",
        request=DriverAssignmentSerializer,
        responses={200: DriverAssignmentSerializer},
    ),
    destroy=extend_schema(
        tags=["DriverAssignments"],
        summary="Delete a driver assignment",
        responses={204: None},
    ),
)
class DriverAssignmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for DriverAssignment.
    """
    permission_classes = [AllowAny]
    serializer_class = DriverAssignmentSerializer
    queryset = DriverAssignment.objects.select_related("driver",  "device").all().order_by("-assigned_at")

    def get_queryset(self):
        qs = super().get_queryset()
        device_id = self.request.query_params.get("device_id")
        # vehicle_id = self.request.query_params.get("vehicle_id")
        driver_id = self.request.query_params.get("driver_id")
        assigned_from = self.request.query_params.get("from")
        assigned_to = self.request.query_params.get("to")

        if device_id:
            qs = qs.filter(device__uuid=device_id)
        # if vehicle_id:
        #     qs = qs.filter(vehicle__id=vehicle_id)
        if driver_id:
            qs = qs.filter(driver__id=driver_id)

        if assigned_from:
            dfrom = parse_datetime(assigned_from)
            if dfrom:
                qs = qs.filter(assigned_at__gte=dfrom)
        if assigned_to:
            dto = parse_datetime(assigned_to)
            if dto:
                qs = qs.filter(assigned_at__lte=dto)

        return qs

    # Bulk-aware create that maps frontend keys:
    # - time -> assigned_at
    # - lat -> latitude
    # - long -> longitude
    # - driverId -> driver
    # - deviceId / device -> device
    def create(self, request, *args, **kwargs):
        payload = request.data

        def normalize_entry(entry, top_device=None):
            if not isinstance(entry, dict):
                return entry
            mapped = dict(entry)
            if "lat" in mapped:
                mapped["latitude"] = mapped.pop("lat")
            if "long" in mapped:
                mapped["longitude"] = mapped.pop("long")
            if "time" in mapped:
                mapped["assigned_at"] = mapped.pop("time")
            if "driverId" in mapped:
                driver_val = mapped.pop("driverId")
                try:
                    driver_val = int(driver_val)
                except (TypeError, ValueError):
                    driver_val = 0
                if driver_val > 0:
                    mapped["driver"] = driver_val
                    mapped["status"] = 1   # ASSIGNED
                elif driver_val == -1:
                    mapped["driver"] = None
                    mapped["status"] = -1  # NOT_DETECTED
                else:
                    mapped["driver"] = None
                    mapped["status"] = 0   # EMPTY_SEAT
            if "deviceId" in mapped:
                mapped["device"] = mapped.pop("deviceId")
            if top_device is not None and "device" not in mapped:
                mapped["device"] = top_device
            return mapped

        # compact payload with top-level device/deviceId and data list
        if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
            top_device = payload.get("device") or payload.get("deviceId")
            items = [normalize_entry(e, top_device=top_device) for e in payload["data"]]
            data = items
            many = True
        # raw list
        elif isinstance(payload, list):
            items = [normalize_entry(e) for e in payload]
            data = items
            many = True
        else:
            # single object
            if isinstance(payload, dict):
                data = normalize_entry(payload)
            else:
                data = payload
            many = isinstance(data, list)

        # Only validate real driver IDs (status=ASSIGNED, driver is not None).
        # driver=None means NOT_DETECTED or EMPTY_SEAT — skip FK check for those.
        try:
            if many and isinstance(data, list):
                driver_ids = {
                    d["driver"] for d in data
                    if isinstance(d, dict) and d.get("driver") is not None
                }
                if driver_ids:
                    existing = set(Driver.objects.filter(id__in=driver_ids).values_list("id", flat=True))
                    if existing != driver_ids:
                        return HttpResponse("true", content_type="text/plain")
            else:
                if isinstance(data, dict) and data.get("driver") is not None:
                    if not Driver.objects.filter(id=data["driver"]).exists():
                        return HttpResponse("true", content_type="text/plain")
        except Exception:
            return HttpResponse("true", content_type="text/plain")

        serializer = self.get_serializer(data=data, many=many)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data if not many else [])
        return HttpResponse("true", content_type="text/plain")





from google.oauth2 import service_account
from google.cloud import storage
import datetime
from django.http import JsonResponse
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
import os


@api_view(["GET"])
@drf_permission_classes([AllowAny])
def get_signed_url(request):
    file_name = request.GET.get("file")
    if not file_name:
        return JsonResponse({"error": "file param required"}, status=400)

    # Allow overriding via env; fall back to local repo file if present
    cred_path = (
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or os.environ.get("GCS_SERVICE_ACCOUNT_FILE")
    )
    if not cred_path:
        default_cred = os.path.join(settings.BASE_DIR, "devices", "auto-annotation-461106-c1934e2fdd95.json")
        if os.path.exists(default_cred):
            cred_path = default_cred

    bucket_name = os.environ.get("GCS_BUCKET_NAME", "afdd-storage")

    try:
        if cred_path and os.path.exists(cred_path):
            credentials = service_account.Credentials.from_service_account_file(cred_path)
            client = storage.Client(credentials=credentials, project=credentials.project_id)
        else:
            # Use default credentials if available (e.g., env or GCE default)
            client = storage.Client()

        blob = client.bucket(bucket_name).blob(file_name.lstrip("/"))
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(hours=12),
            method="GET",
        )
        return JsonResponse({"url": url})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


SFTP_HOST = "34.18.136.204"
SFTP_PORT = 22
SFTP_USER = "bcastuser"
SFTP_PASS = "cast%Monit67"
SFTP_BASE_DIR = "/broadcast"


def _sftp_makedirs(sftp, remote_path):
    """Recursively create remote directories if they don't exist."""
    parts = remote_path.strip("/").split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


class BroadcastViewSet(viewsets.ModelViewSet):
    serializer_class = BroadcastSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        user_id = self.request.query_params.get("user_id")
        qs = Broadcast.objects.all().order_by("-created_at")
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    def create(self, request, *args, **kwargs):
        audio_file = request.FILES.get("audio_file")
        vehicle_id = request.data.get("vehicle_id")
        user_id = request.data.get("user_id")
        duration = int(request.data.get("duration", 0))

        if not audio_file or not vehicle_id or not user_id:
            return Response(
                {"error": "audio_file, vehicle_id, and user_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vehicle = Vehicle.objects.select_related("device").get(pk=vehicle_id)
        except Vehicle.DoesNotExist:
            return Response({"error": "Vehicle not found."}, status=status.HTTP_404_NOT_FOUND)

        vehicle_uuid = vehicle.device.uuid
        vehicle_name = vehicle.name or vehicle.registration_number
        broadcast_date = timezone.localdate()
        date_str = broadcast_date.strftime("%Y-%m-%d")
        timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"broadcast_{timestamp_str}_{vehicle_uuid}.webm"
        remote_dir = f"{SFTP_BASE_DIR}/{vehicle_uuid}/{date_str}"
        remote_path = f"{remote_dir}/{file_name}"

        try:
            transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
            transport.connect(username=SFTP_USER, password=SFTP_PASS)
            sftp = paramiko.SFTPClient.from_transport(transport)
            _sftp_makedirs(sftp, remote_dir)
            file_bytes = audio_file.read()
            sftp.putfo(io.BytesIO(file_bytes), remote_path)
            sftp.close()
            transport.close()
        except Exception as e:
            logger.error("SFTP upload failed: %s", e)
            return Response({"error": f"SFTP upload failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        broadcast = Broadcast.objects.create(
            user_id=user_id,
            vehicle_id=vehicle_id,
            vehicle_uuid=vehicle_uuid,
            vehicle_name=vehicle_name,
            date=broadcast_date,
            file_name=remote_path,
            duration=duration,
        )
        return Response(BroadcastSerializer(broadcast).data, status=status.HTTP_201_CREATED)
