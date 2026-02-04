from rest_framework import serializers
from .models import Study, ProcessingResult, ProcessingLog

class ProcessingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingLog
        fields = '__all__'

class ProcessingResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingResult
        fields = '__all__'

class StudySerializer(serializers.ModelSerializer):
    logs = ProcessingLogSerializer(many=True, read_only=True)
    results = ProcessingResultSerializer(read_only=True)

    class Meta:
        model = Study
        fields = '__all__'
        read_only_fields = ['status', 'error_message', 'dicom_directory', 'created_at']
