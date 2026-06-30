from django.db import migrations


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS viol_user_logged_at_idx
            ON device_violations (user_id, logged_at DESC);
        """)
        schema_editor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS viol_status_logged_at_idx
            ON device_violations (status, logged_at DESC);
        """)
        schema_editor.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS vioann_annotator_date_idx
            ON violation_annotations (annotated_by, created_at DESC);
        """)
    else:
        schema_editor.execute("""
            CREATE INDEX IF NOT EXISTS viol_user_logged_at_idx
            ON device_violations (user_id, logged_at DESC);
        """)
        schema_editor.execute("""
            CREATE INDEX IF NOT EXISTS viol_status_logged_at_idx
            ON device_violations (status, logged_at DESC);
        """)
        schema_editor.execute("""
            CREATE INDEX IF NOT EXISTS vioann_annotator_date_idx
            ON violation_annotations (annotated_by, created_at DESC);
        """)


def drop_indexes(apps, schema_editor):
    schema_editor.execute("DROP INDEX IF EXISTS viol_user_logged_at_idx;")
    schema_editor.execute("DROP INDEX IF EXISTS viol_status_logged_at_idx;")
    schema_editor.execute("DROP INDEX IF EXISTS vioann_annotator_date_idx;")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('devices', '0022_heartbeat_date_functional_index'),
    ]

    operations = [
        migrations.RunPython(create_indexes, drop_indexes),
    ]
