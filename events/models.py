import uuid
from django.db import models


class LogEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('login_failed', 'Login Failed'),
        ('login_success', 'Login Success'),
        ('connection', 'Connection'),
    ]
    PROTOCOL_CHOICES = [
        ('tcp', 'TCP'),
        ('udp', 'UDP'),
        ('icmp', 'ICMP'),
        ('http', 'HTTP'),
        ('ssh', 'SSH'),
        ('other', 'Other'),
    ]

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    timestamp = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    source_ip = models.GenericIPAddressField()
    dest_ip = models.GenericIPAddressField(null=True, blank=True)
    dest_port = models.IntegerField(null=True, blank=True)
    protocol = models.CharField(max_length=10, choices=PROTOCOL_CHOICES)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    username = models.CharField(max_length=100, null=True, blank=True)
    bytes_sent = models.PositiveIntegerField(default=0)
    raw = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['source_ip', 'timestamp']),
            models.Index(fields=['source_ip', 'event_type', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.source_ip} {self.event_type} {self.timestamp}"
