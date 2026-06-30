# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db import models


from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
username_validator = RegexValidator(
    regex=r"^(?!\s)[\w.@+\-&\s]+(?<!\s)$",
    message=_(
        "Enter a valid username. Spaces are allowed inside, but not at the beginning or end."
    ),
    code="invalid_username",
)

class User(AbstractUser):
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_("Required. 150 characters or fewer."),
        validators=[username_validator],   # 👈 our custom validator
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    # username retained; email unique for login & verification
    email = models.EmailField(unique=True)
    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("manager", "Manager"),
        ("user", "User"),
        ("annotator", "Annotator"),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    email_verified = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    registration_number = models.CharField(max_length=100, blank=True, null=True)
    plan=models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    def __str__(self):
        return self.username or self.email


class ManagerUserAssociation(models.Model):
    manager = models.ForeignKey(
        User,
        to_field="id",
        db_column="manager_id",
        on_delete=models.CASCADE,
        related_name="managed_users", db_index=True
    )
    user = models.ForeignKey(
        User,
        to_field="id",
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="user_manager", db_index=True  
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["manager", "user"], name="uniq_manager_user_pair")
        ]
    def __str__(self):
        return f"Manager: {self.manager.username} - User: {self.user.username}"