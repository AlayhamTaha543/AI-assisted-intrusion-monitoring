from rest_framework import serializers
from .models import Alert


class AlertListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ['id', 'rule_name', 'source_ip', 'incident_status', 'investigation_status',
                  'severity', 'mitre_id', 'mitre_name', 'first_seen_at', 'last_seen_at',
                  'last_window_count', 'peak_window_count', 'created_at', 'updated_at']


class AlertDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = '__all__'
