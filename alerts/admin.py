from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['id', 'rule_name', 'source_ip', 'incident_status', 'investigation_status', 'severity', 'created_at']
    list_filter = ['rule_name', 'incident_status', 'investigation_status', 'severity']
    readonly_fields = [field.name for field in Alert._meta.fields]
    actions = ['rerun_investigation']
    fieldsets = (
        ('Computed by the backend', {
            'fields': ('rule_name', 'source_ip', 'severity', 'mitre_id', 'mitre_name', 'first_seen_at', 'last_seen_at', 'last_window_count', 'peak_window_count', 'evidence', 'incident_status', 'status_changed_by', 'status_changed_at', 'created_at', 'updated_at')
        }),
        ('AI-generated, not authoritative', {
            'fields': ('ai_summary', 'ai_recommended_actions', 'ai_model', 'ai_used_tool', 'investigation_status', 'investigation_attempts', 'investigation_error', 'investigation_started_at', 'investigated_at', 'investigation_latency_ms')
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in Alert._meta.fields]

    @admin.action(description='Re-run investigation for failed/queued/stale running', permissions=['view'])
    def rerun_investigation(self, request, queryset):
        from agent.tasks import run_investigation

        count = 0
        skipped = 0
        for alert in queryset:
            if alert.investigation_status == 'completed':
                skipped += 1
                continue
            if alert.investigation_status == 'running' and alert.investigation_started_at and (timezone.now() - alert.investigation_started_at).total_seconds() <= 360:
                skipped += 1
                continue
            try:
                with transaction.atomic():
                    alert.investigation_status = 'queued'
                    alert.investigation_error = ''
                    alert.ai_summary = ''
                    alert.ai_recommended_actions = []
                    alert.investigation_attempts = 0
                    alert.ai_used_tool = False
                    alert.investigation_started_at = None
                    alert.investigated_at = None
                    alert.investigation_latency_ms = None
                    alert.ai_model = ''
                    alert.save(update_fields=['investigation_status', 'investigation_error', 'ai_summary', 'ai_recommended_actions', 'investigation_attempts', 'ai_used_tool', 'investigation_started_at', 'investigated_at', 'investigation_latency_ms', 'ai_model', 'updated_at'])
                transaction.on_commit(lambda a=alert: run_investigation.delay(a.id))
                count += 1
            except Exception:
                alert.investigation_status = 'failed'
                alert.investigation_error = 'queue_unavailable'
                alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
        self.message_user(request, f'Re-queued {count}, skipped {skipped}')
