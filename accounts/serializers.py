from django.contrib.auth import authenticate, password_validation, get_user_model
from rest_framework import serializers
from .validators import validate_role_and_manager
from .models import ManagerUserAssociation
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    assigned_users = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "role",
            "email_verified",
            "first_name",
            "last_name",
            "phone_number",
            "address",
            "plan",
            "description",
            "registration_number",
            "updated_at",
            "assigned_users",   # 👈 NEW
        )

    def get_assigned_users(self, obj):
        # Only for managers
        if obj.role != "manager":
            return []

        from .models import ManagerUserAssociation

        return list(
            ManagerUserAssociation.objects.filter(manager=obj)
            .values_list("user_id", flat=True)
        )
class UserMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username")

class UserManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username","email", "role",  "phone_number", )

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES, default="user")  # 👈 added
    # manager = serializers.PrimaryKeyRelatedField(
    #     queryset=User.objects.filter(role="manager"),
    #     required=False, allow_null=True
    # )
    class Meta:
        model = User
        fields = ('id',"username", "email", "password","role", "phone_number",'registration_number',"address","plan","description")  # 👈 added phone_number
    def validate(self, attrs):
        role = attrs.get("role", "user")
        manager = attrs.get("manager")
        request = self.context.get("request")

        # Only staff/admin can create admin/manager accounts
        # if role in ("admin", "manager"):
        #     if not request or not (request.user.is_staff or request.user.role == "admin"):
        #         raise serializers.ValidationError("Only admins can create admin/manager accounts.")

        validate_role_and_manager(role, manager)
        return attrs
    def create(self, validated):
        user = User.objects.create_user(
            username=validated["username"],
            email=validated["email"],
            password=validated["password"],
            role=validated.get("role", "user"),
            # manager=validated.get("manager"),
            phone_number=validated.get("phone_number", ""),
            is_active=True,
        )
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        if not user.is_active:
            raise serializers.ValidationError("User disabled")
        attrs["user"] = user
        return attrs

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()
    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value

class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordConfirmSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    new_password = serializers.CharField()

    def validate_new_password(self, value):
        # run Django's password validators
        password_validation.validate_password(value)
        return value

class VerifyEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class AssignUsersToManagerSerializer(serializers.Serializer):
    manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role="manager"),
        source="manager"
    )
    user_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role="user")),
        allow_empty=False
    )
    # If true: replace existing associations for this manager with exactly the provided users
    replace = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        manager = attrs["manager"]
        users = attrs["user_ids"]
        # (Optional) guard: ensure none of the users equals the manager id
        if any(u.id == manager.id for u in users):
            raise serializers.ValidationError("Manager cannot be associated with themselves.")
        return attrs

    def save(self, **kwargs):
        manager = self.validated_data["manager"]
        users = list(self.validated_data["user_ids"])
        replace = self.validated_data.get("replace", False)

        removed = []
        created = []
        skipped_existing = []

        if replace:
            # delete all current associations for this manager that aren't in the new list
            keep_ids = [u.id for u in users]
            to_delete_qs = ManagerUserAssociation.objects.filter(manager=manager).exclude(user_id__in=keep_ids)
            removed = list(to_delete_qs.values_list("user_id", flat=True))
            to_delete_qs.delete()

        # find which pairs already exist
        existing = set(
            ManagerUserAssociation.objects
            .filter(manager=manager, user__in=users)
            .values_list("user_id", flat=True)
        )

        to_create = [
            ManagerUserAssociation(manager=manager, user=u)
            for u in users if u.id not in existing
        ]

        # bulk create (ignore_conflicts keeps idempotency when unique constraint exists)
        ManagerUserAssociation.objects.bulk_create(to_create, ignore_conflicts=True)

        created = [u.user.id for u in ManagerUserAssociation.objects.filter(
            manager=manager, user__in=users
        ).only("user") if u.user.id not in existing]

        skipped_existing = list(existing)

        return {
            "manager": manager.id,
            "assigned_created": created,
            "assigned_skipped_existing": skipped_existing,
            "removed" if replace else "removed_skipped": removed if replace else [],
            "total_current_for_manager": ManagerUserAssociation.objects.filter(manager=manager).count()
        }