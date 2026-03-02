# Generated manually — adds downsampled 3D volume fields for WebGL performance

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dki_core', '0014_add_vmtk_mesh_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingresult',
            name='source_volume_3d',
            field=models.FileField(blank=True, help_text='Downsampled source volume for 3D WebGL viewer (128³ int16)', null=True, upload_to='results/tep_source_3d/'),
        ),
        migrations.AddField(
            model_name='processingresult',
            name='tep_heatmap_3d',
            field=models.FileField(blank=True, help_text='Downsampled heatmap for 3D WebGL viewer (128³ float32)', null=True, upload_to='results/tep_heatmap_3d/'),
        ),
    ]
