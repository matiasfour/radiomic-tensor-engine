"""
Migration: Change Study.id from BigAutoField to UUIDField.

Uses Django-native operations (no raw SQL) so it works with
both SQLite and PostgreSQL.

This clears all existing Study/Result/Log data (PK type change).
"""
from django.db import migrations, models
import uuid
import django.db.models.deletion


def clear_all_data(apps, schema_editor):
    """Clear all data before PK type change."""
    ProcessingLog = apps.get_model('dki_core', 'ProcessingLog')
    ProcessingResult = apps.get_model('dki_core', 'ProcessingResult')
    Study = apps.get_model('dki_core', 'Study')
    ProcessingLog.objects.all().delete()
    ProcessingResult.objects.all().delete()
    Study.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dki_core', '0011_remove_processingresult_estimated_mpap_and_more'),
    ]

    operations = [
        # Step 1: Clear all data (required for PK type change)
        migrations.RunPython(clear_all_data, migrations.RunPython.noop),
        
        # Step 2: Remove FK fields from child tables (drops constraints automatically)
        migrations.RemoveField(
            model_name='processingresult',
            name='study',
        ),
        migrations.RemoveField(
            model_name='processinglog',
            name='study',
        ),
        
        # Step 3: Change Study.id from BigAutoField to UUIDField
        migrations.RemoveField(
            model_name='study',
            name='id',
        ),
        migrations.AddField(
            model_name='study',
            name='id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
        
        # Step 4: Re-add FK fields pointing to the new UUID PK
        migrations.AddField(
            model_name='processingresult',
            name='study',
            field=models.OneToOneField(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='results',
                to='dki_core.study',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='processinglog',
            name='study',
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='logs',
                to='dki_core.study',
            ),
            preserve_default=False,
        ),
    ]
