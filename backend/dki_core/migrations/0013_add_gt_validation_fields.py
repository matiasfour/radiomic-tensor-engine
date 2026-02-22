"""
Migration: Add Ground Truth validation fields to ProcessingResult.
Adds gt_mask (FileField) and gt_validation (JSONField) for expert comparison.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dki_core', '0012_study_uuid_primary_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingresult',
            name='gt_mask',
            field=models.FileField(blank=True, help_text='Expert ground truth mask as NIfTI', null=True, upload_to='results/gt_mask/'),
        ),
        migrations.AddField(
            model_name='processingresult',
            name='gt_validation',
            field=models.JSONField(blank=True, help_text='GT vs MART comparison metrics (sensitivity, dice, volumes)', null=True),
        ),
    ]
