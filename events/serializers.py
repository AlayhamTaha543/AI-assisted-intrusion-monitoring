import ipaddress
import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers


class LogEventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField(required=True)
    timestamp = serializers.DateTimeField()
    source_ip = serializers.CharField()
    dest_ip = serializers.CharField(required=False, allow_null=True)
    dest_port = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    protocol = serializers.ChoiceField(choices=['tcp', 'udp', 'icmp', 'http', 'ssh', 'other'])
    event_type = serializers.ChoiceField(choices=['login_failed', 'login_success', 'connection'])
    username = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=100)
    bytes_sent = serializers.IntegerField(required=False, min_value=0, max_value=2147483647)
    raw = serializers.JSONField(required=False, allow_null=True)

    def validate_source_ip(self, value):
        try:
            ipaddress.ip_address(value)
        except Exception:
            raise serializers.ValidationError('Invalid IP address')
        return value

    def validate_dest_ip(self, value):
        if value is None or value == '':
            return None
        try:
            ipaddress.ip_address(value)
        except Exception:
            raise serializers.ValidationError('Invalid IP address')
        return value

    def validate_username(self, value):
        if value is None or value == '':
            return None
        return value

    def validate_timestamp(self, value):
        now = timezone.now()
        if value > now + timedelta(seconds=settings.MAX_FUTURE_SKEW_SECONDS):
            raise serializers.ValidationError('Timestamp too far in the future')
        if value < now - timedelta(hours=settings.MAX_EVENT_AGE_HOURS):
            raise serializers.ValidationError('Timestamp too old')
        return value

    def validate_raw(self, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise serializers.ValidationError('raw must be object')
        try:
            s = json.dumps(value)
        except Exception:
            raise serializers.ValidationError('Invalid raw')
        if len(s.encode('utf-8')) > settings.MAX_RAW_BYTES:
            raise serializers.ValidationError('raw too large')
        if '\\u0000' in s:
            raise serializers.ValidationError('raw contains null')
        return value
