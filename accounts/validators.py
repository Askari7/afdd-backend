from rest_framework import serializers

def validate_role_and_manager(role, manager):
    # if role == "user" and not manager:
    #     raise serializers.ValidationError("A user must be assigned to a manager.")
    if role in ("admin", "manager") and manager:
        raise serializers.ValidationError("Admins/Managers cannot have a manager.")
