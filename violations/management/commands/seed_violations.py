from django.core.management.base import BaseCommand
from violations.models import ViolationCategory, ViolationType


class Command(BaseCommand):
    help = "Seed database with violation categories and types"

    def handle(self, *args, **options):
        data = [
            # violation_id, title, description, category_name, is_annotatable, severity
            (1, "Harsh Acceleration", "Harsh Acceleration", "GPS", True, 1),
            (2, "Harsh Brake", "Harsh Brake", "GPS", True, 1),
            (3, "Harsh Cornering", "Harsh Cornering", "GPS", True, 1),
            (4, "Roll over", "Roll over", "Accidents", True, 4),
            (5, "Overspeeding", "Overspeeding", "GPS", True, 3),
            (6, "Distraction", "Distraction", "Fatigue", True, 3),
            (8, "Yawning", "Yawning", "Fatigue", True, 2),
            (9, "Cigarette", "Cigarette", "Distractions", True, 3),
            (10, "Mobile", "Mobile", "Distractions", True, 3),
            (11, "Low Drowsy", "Low Drowsy", "Fatigue", True, 1),
            (12, "Moderate drowsy", "Moderate drowsy", "Fatigue", True, 2),
            (13, "Hands not on Steering", "Hands not on Steering", "Distractions", True, 3),
            (7, "Severe Drowsy", "Severe Drowsy", "Fatigue", True, 3),
            (14, "Lane Change (Left)", "Lane Change Left", "GPS", True, 1),
            (15, "Lane Change (Right)", "Lane Change Right", "GPS", True, 1),
            (19, "Tampering", "Tampering", "Distractions", True, 3),
            (16, "Near Collision", "Near Collision", "GPS", True, 1),
            (17, "Emergency Lane Departure", "Emergency Lane Departure", "Fatigue", True, 2),
            (18, "Unsafe Lane Change", "Unsafe Lane Change", "Distractions", True, 3),
            (20, "Close Following", "Close Following", "Distractions", True, 2),
            (21, "Fire/Smoke Alert", "Fire/Smoke Alert", "Accidents", True, 1),
            (22, "Intruder Alert", "Intruder Alert", "Alarm", True, 1),
        ]

        self.stdout.write(self.style.WARNING("Seeding violation data..."))

        # First create / fetch categories
        categories = {}
        for _, _, _, category_name, _, _ in data:
            if category_name not in categories:
                categories[category_name], _ = ViolationCategory.objects.get_or_create(
                    violation_category_name=category_name
                )

        # Now create/update types with fixed IDs
        for violation_id, title, description, category_name, is_annotatable, severity in data:
            ViolationType.objects.update_or_create(
                id=violation_id,  # force this ID
                defaults={
                    "title": title,
                    "description": description,
                    "category": categories[category_name],
                    "is_annotatable": is_annotatable,
                    "severity": severity,
                },
            )

        self.stdout.write(self.style.SUCCESS("✅ Violations seeded successfully!"))
