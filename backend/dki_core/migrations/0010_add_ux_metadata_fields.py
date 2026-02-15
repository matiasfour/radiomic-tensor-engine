# Generated manually - Add UX metadata JSONFields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dki_core', '0009_processingresult_tep_coherence_map'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingresult',
            name='slices_meta',
            field=models.JSONField(blank=True, null=True, help_text='Smart Scrollbar: alert Z-indices for heatmap and flow'),
        ),
        migrations.AddField(
            model_name='processingresult',
            name='findings_pins',
            field=models.JSONField(blank=True, null=True, help_text='Diagnostic Pins: coordinate markers with score tooltips'),
        ),
    ]
