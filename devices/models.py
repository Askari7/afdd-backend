from django.db import models
from accounts.models import User
from violations.models import ViolationType
class Device(models.Model):
    uuid = models.CharField(max_length=255, unique=True)   # external device UUID
    name = models.CharField(max_length=255,blank=True, null=True)
    type = models.CharField(max_length=100)
    sim = models.CharField(max_length=50, null=True, blank=True)
    rear_camera_url = models.URLField(max_length=500, blank=True, null=True)
    front_camera_url = models.URLField(max_length=500, blank=True, null=True)

    # Store features (camera + sensor) in JSON format
    features = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.uuid})"
    
class Vehicle(models.Model):
    device = models.OneToOneField(
        Device,
        to_field="uuid",
        db_column="device_id",
        on_delete=models.CASCADE,
        related_name="vehicles"
    )
    user_id = models.ForeignKey(
        'accounts.User',
        to_field="id",
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="vehicles"
    )
    name = models.CharField(max_length=255,blank=True, null=True)
    registration_number = models.CharField(max_length=100)
    model_name=models.CharField(max_length=100,blank=True, null=True)
    model_year=models.IntegerField(blank=True, null=True)
    chasis_number=models.CharField(max_length=100,blank=True, null=True)
    engine_number=models.CharField(max_length=100,blank=True, null=True)
    color=models.CharField(max_length=50,blank=True, null=True)
    manufacturer=models.CharField(max_length=100,blank=True, null=True)
    type = models.CharField(max_length=100,blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.registration_number})"



class Driver(models.Model):

    user_id=models.ForeignKey(
        'accounts.User',
        to_field="id",            # 👈 use the uuid field instead of PK id
        db_column="user_id",      
        on_delete=models.CASCADE,
        related_name="drivers"
    )

    name = models.CharField(max_length=255,blank=True, null=True)
    email = models.CharField(max_length=100,unique=True)
    phone_number = models.CharField(max_length=15,blank=True, null=True)
    address = models.CharField(max_length=255,blank=True, null=True)
    cnic_number = models.CharField(max_length=20,unique=True,blank=True, null=True)
    rfid_tag = models.CharField(max_length=100,unique=True, null=True, blank=True)

    dob = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.email})" 
    
class DriverAssignment(models.Model):

    class DriverStatus(models.IntegerChoices):
        ASSIGNED = 1, "Assigned Driver"
        NOT_DETECTED = -1, "Driver Not Detected"
        EMPTY_SEAT = 0, "Empty Seat"

    driver = models.ForeignKey(
        Driver,
        to_field="id",
        db_column="driver_id",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="driver_assignments"
    )
    device = models.ForeignKey(
        Device,
        to_field="uuid",
        db_column="device_id",
        on_delete=models.CASCADE,
        related_name="driver_assignments"
    )
    status = models.IntegerField(
        choices=DriverStatus.choices,
        default=DriverStatus.ASSIGNED
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    assigned_at = models.DateTimeField(help_text="Driver Assign time from device (original source)")
    unassigned_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Driver {self.driver_id} assigned to Device {self.device_id} (status={self.status})"

class Event(models.Model):
    # Link to Device by UUID field
    device = models.ForeignKey(
        Device,
        to_field="uuid",            
        db_column="device_id",      # column name in DB will be device_id
        on_delete=models.CASCADE,
        related_name="events"
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)

    logged_at = models.DateTimeField(help_text="Event time from device (original source)")
    created_at = models.DateTimeField(auto_now_add=True)

    type = models.CharField(max_length=100)
    value = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "device_events"
        indexes = [
            models.Index(fields=["device", "logged_at"]),
            models.Index(fields=["type"]),
        ]

    def __str__(self):
        return f"Event {self.type} for {self.device_id} at {self.logged_at}"
    



class Heartbeat(models.Model):
    # Link to Device by UUID field
    device = models.ForeignKey(
        Device,
        to_field="uuid",            # 👈 use the uuid field instead of PK id
        db_column="device_id",      # column name in DB will be device_id
        on_delete=models.CASCADE,
        related_name="heartbeats"
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    bearing = models.FloatField(null=True, blank=True)

    logged_at = models.DateTimeField(help_text="Event time from device (original source)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "device_heartbeats"
        indexes = [
            models.Index(fields=["device", "logged_at"]),
        ]

    def __str__(self):
        return f"Heartbeat for {self.device_id} at {self.logged_at}"
    



class Violation(models.Model):
    # Link to Device by UUID field
    device = models.ForeignKey(
        Device,
        to_field="uuid",            # 👈 use the uuid field instead of PK id
        db_column="device_id",      # column name in DB will be device_id
        on_delete=models.CASCADE,
        related_name="violations"
    )
    vehicle= models.ForeignKey( 
        Vehicle, 
        to_field="id",            
        db_column="vehicle_id",   
        on_delete=models.CASCADE,
        related_name="violations",blank=True, null=True
    ) 
    user= models.ForeignKey( 
        'accounts.User', 
        to_field="id",            
        db_column="user_id",       
        on_delete=models.CASCADE,
        related_name="violations",blank=True, null=True 
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    altitude = models.FloatField(null=True, blank=True)
    logged_at = models.DateTimeField(help_text="Event time from device (original source)")
    created_at = models.DateTimeField(auto_now_add=True)
    violation_type_id=models.ForeignKey(
        ViolationType,
        to_field="id",            # 👈 use the uuid field instead of PK id
        db_column="violation_id",      
        on_delete=models.CASCADE,
        related_name="violations"
    )
    front_camera_video_file_name = models.CharField(max_length=255, null=True, blank=True)
    rear_camera_video_file_name = models.CharField(max_length=255, null=True, blank=True)
    left_camera_video_file_name = models.CharField(max_length=255, null=True, blank=True)
    right_camera_video_file_name = models.CharField(max_length=255, null=True, blank=True)
    cabin_camera_video_file_name = models.CharField(max_length=255, null=True, blank=True)
    driver_id = models.CharField(max_length=100, null=True, blank=True)
    meta=models.CharField(max_length=100, null=True, blank=True)
    status=models.CharField(max_length=100, default="unevaluated")
    class Meta:
        db_table = "device_violations"
        indexes = [
            models.Index(fields=["logged_at"]), models.Index(fields=["status"]), models.Index(fields=["user"]), models.Index(fields=["vehicle"]), models.Index(fields=["violation_type_id"]),
            models.Index(fields=["device", "logged_at", "violation_type_id"]),
            # Composite indexes for annotation/dashboard queries
            models.Index(fields=["user", "-logged_at"], name="viol_user_logged_at_idx"),
            models.Index(fields=["status", "-logged_at"], name="viol_status_logged_at_idx"),
        ]

    def __str__(self):
        return f"Violations for {self.device_id} at {self.logged_at}"
    

class Broadcast(models.Model):
    user = models.ForeignKey(
        'accounts.User',
        to_field="id",
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="broadcasts"
    )
    vehicle = models.ForeignKey(
        Vehicle,
        to_field="id",
        db_column="vehicle_id",
        on_delete=models.CASCADE,
        related_name="broadcasts"
    )
    vehicle_uuid = models.CharField(max_length=255)
    vehicle_name = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateField()
    file_name = models.CharField(max_length=500)
    duration = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "broadcasts"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["vehicle", "-created_at"]),
        ]

    def __str__(self):
        return f"Broadcast {self.id} for vehicle {self.vehicle_uuid} on {self.date}"


class ViolationAnnotation(models.Model):
    violation = models.ForeignKey(
        Violation,
        to_field="id",            
        db_column="violation_id",      
        on_delete=models.CASCADE,
        related_name="annotations"
    )
    annotated_by = models.ForeignKey(
        User,
        to_field="id",            
        db_column="annotated_by",      
        on_delete=models.CASCADE,
        related_name="violation_annotations"
    )
    status = models.CharField(max_length=100)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "violation_annotations"
        indexes = [
            models.Index(fields=["violation", "annotated_by", "status", "created_at"]),
            models.Index(fields=["annotated_by", "-created_at"], name="vioann_annotator_date_idx"),
        ]

    def __str__(self):
        return f"Annotation for Violation {self.violation_id} by User {self.annotated_by_id}"