"""
Migration: Change Study.id from BigAutoField to UUIDField.

This is a destructive migration - it clears existing data in Study,
ProcessingResult, and ProcessingLog tables because changing a PK type
with existing foreign keys requires dropping and recreating constraints.
"""
from django.db import migrations, models
import uuid


def gen_uuid(apps, schema_editor):
    """Generate UUIDs for any existing Study rows (if any survive the type change)."""
    Study = apps.get_model('dki_core', 'Study')
    for study in Study.objects.all():
        study.id = uuid.uuid4()
        study.save(update_fields=['id'])


class Migration(migrations.Migration):

    dependencies = [
        ('dki_core', '0011_remove_processingresult_estimated_mpap_and_more'),
    ]

    operations = [
        # Step 1: Remove foreign keys that reference Study.id
        migrations.RunSQL(
            sql=[
                "DELETE FROM dki_core_processinglog;",
                "DELETE FROM dki_core_processingresult;",
                "DELETE FROM dki_core_study;",
                # Drop FK constraints
                "ALTER TABLE dki_core_processingresult DROP CONSTRAINT IF EXISTS dki_core_processingresult_study_id_fkey;",
                "ALTER TABLE dki_core_processingresult DROP CONSTRAINT IF EXISTS dki_core_processingresult_study_id_key;",
                "ALTER TABLE dki_core_processinglog DROP CONSTRAINT IF EXISTS dki_core_processinglog_study_id_fkey;",
                # Also drop by Django's auto-generated constraint names
                "ALTER TABLE dki_core_processingresult DROP CONSTRAINT IF EXISTS dki_core_processingre_study_id_e5cc07c1_fk_dki_core_;",
                "ALTER TABLE dki_core_processingresult DROP CONSTRAINT IF EXISTS dki_core_processingresult_study_id_e5cc07c1_fk;",
                "ALTER TABLE dki_core_processingresult DROP CONSTRAINT IF EXISTS dki_core_processingresult_study_id_e5cc07c1_uniq;",
                "ALTER TABLE dki_core_processinglog DROP CONSTRAINT IF EXISTS dki_core_processinglo_study_id_3a0bd0e5_fk_dki_core_;",
                "ALTER TABLE dki_core_processinglog DROP CONSTRAINT IF EXISTS dki_core_processinglog_study_id_3a0bd0e5_fk;",
                # Drop indexes
                "DROP INDEX IF EXISTS dki_core_processingresult_study_id_e5cc07c1;",
                "DROP INDEX IF EXISTS dki_core_processinglog_study_id_3a0bd0e5;",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        
        # Step 2: Change Study.id column from bigint to uuid
        migrations.RunSQL(
            sql=[
                "ALTER TABLE dki_core_study DROP CONSTRAINT IF EXISTS dki_core_study_pkey;",
                "ALTER TABLE dki_core_study DROP COLUMN id;",
                "ALTER TABLE dki_core_study ADD COLUMN id uuid PRIMARY KEY DEFAULT gen_random_uuid();",
            ],
            reverse_sql=[
                "ALTER TABLE dki_core_study DROP CONSTRAINT IF EXISTS dki_core_study_pkey;",
                "ALTER TABLE dki_core_study DROP COLUMN id;",
                "ALTER TABLE dki_core_study ADD COLUMN id bigserial PRIMARY KEY;",
            ],
        ),
        
        # Step 3: Change FK columns from bigint to uuid and recreate constraints
        migrations.RunSQL(
            sql=[
                # ProcessingResult
                "ALTER TABLE dki_core_processingresult ALTER COLUMN study_id TYPE uuid USING NULL;",
                "ALTER TABLE dki_core_processingresult ADD CONSTRAINT dki_core_processingresult_study_id_fkey FOREIGN KEY (study_id) REFERENCES dki_core_study(id) ON DELETE CASCADE;",
                "ALTER TABLE dki_core_processingresult ADD CONSTRAINT dki_core_processingresult_study_id_key UNIQUE (study_id);",
                # ProcessingLog
                "ALTER TABLE dki_core_processinglog ALTER COLUMN study_id TYPE uuid USING NULL;",
                "ALTER TABLE dki_core_processinglog ADD CONSTRAINT dki_core_processinglog_study_id_fkey FOREIGN KEY (study_id) REFERENCES dki_core_study(id) ON DELETE CASCADE;",
                "CREATE INDEX dki_core_processinglog_study_id_idx ON dki_core_processinglog(study_id);",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        
        # Step 4: Update Django's model state to match
        migrations.AlterField(
            model_name='study',
            name='id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
        ),
    ]
