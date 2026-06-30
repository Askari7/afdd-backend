import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0024_driver_assignment_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Broadcast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_uuid', models.CharField(max_length=255)),
                ('vehicle_name', models.CharField(blank=True, max_length=255, null=True)),
                ('date', models.DateField()),
                ('file_name', models.CharField(max_length=500)),
                ('duration', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    db_column='user_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='broadcasts',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('vehicle', models.ForeignKey(
                    db_column='vehicle_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='broadcasts',
                    to='devices.vehicle',
                )),
            ],
            options={
                'db_table': 'broadcasts',
            },
        ),
        migrations.AddIndex(
            model_name='broadcast',
            index=models.Index(fields=['user', '-created_at'], name='broadcasts_user_created_idx'),
        ),
        migrations.AddIndex(
            model_name='broadcast',
            index=models.Index(fields=['vehicle', '-created_at'], name='broadcasts_vehicle_created_idx'),
        ),
    ]
