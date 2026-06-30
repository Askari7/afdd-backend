from django.db import models


class ViolationCategory(models.Model):
    violation_category_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.violation_category_name

class ViolationType(models.Model):
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(
        ViolationCategory,
        on_delete=models.CASCADE,
        related_name='violations'
    )
    is_annotatable = models.BooleanField(default=False)
    severity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.category.violation_category_name})"
