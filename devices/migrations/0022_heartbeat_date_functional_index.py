from django.db import migrations


def create_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                devices_heartbeat_device_date_idx
            ON device_heartbeats (device_id, logged_at DESC);
        """)
    else:
        schema_editor.execute("""
            CREATE INDEX IF NOT EXISTS
                devices_heartbeat_device_date_idx
            ON device_heartbeats (device_id, logged_at DESC);
        """)


def drop_index(apps, schema_editor):
    schema_editor.execute("DROP INDEX IF EXISTS devices_heartbeat_device_date_idx;")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("devices", "0021_device_sim"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
