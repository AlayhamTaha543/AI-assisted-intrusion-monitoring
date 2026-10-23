from django.db import models
from django.contrib.auth.models import User


MITRE = {
    "brute_force": {"id": "T1110", "name": "Brute Force"},
    "port_scan": {"id": "T1046", "name": "Network Service Discovery"},
}


class Alert(models.Model):
    RULE_CHOICES = [('brute_force', 'Brute Force'), ('port_scan', 'Port Scan')]
    INCIDENT_STATUS_CHOICES = [('open', 'Open'), ('acknowledged', 'Acknowledged'), ('resolved', 'Resolved')]
    INVESTIGATION_STATUS_CHOICES = [('queued', 'Queued'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')]
    SEVERITY_CHOICES = [('high', 'High'), ('medium', 'Medium')]

    rule_name = models.CharField(max_length=20, choices=RULE_CHOICES)
    source_ip = models.GenericIPAddressField()
    incident_status = models.CharField(max_length=20, choices=INCIDENT_STATUS_CHOICES, default='open')
    investigation_status = models.CharField(max_length=20, choices=INVESTIGATION_STATUS_CHOICES, default='queued')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    mitre_id = models.CharField(max_length=10)
    mitre_name = models.CharField(max_length=100)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    last_window_count = models.IntegerField(default=0)
    peak_window_count = models.IntegerField(default=0)
    evidence = models.JSONField(default=dict)
    ai_summary = models.TextField(blank=True, default='')
    ai_recommended_actions = models.JSONField(default=list)
    ai_model = models.CharField(max_length=100, blank=True, default='')
    ai_used_tool = models.BooleanField(default=False)
    investigation_attempts = models.IntegerField(default=0)
    investigation_error = models.CharField(max_length=255, blank=True, default='')
    investigation_started_at = models.DateTimeField(null=True, blank=True)
    investigated_at = models.DateTimeField(null=True, blank=True)
    investigation_latency_ms = models.IntegerField(null=True, blank=True)
    status_changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='status_changes')
    status_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['rule_name', 'source_ip'],
                condition=models.Q(incident_status__in=['open', 'acknowledged']),
                name='unique_active_incident_per_rule_ip',
            )
        ]

    def __str__(self):
        return f"{self.rule_name} {self.source_ip} {self.incident_status}"
