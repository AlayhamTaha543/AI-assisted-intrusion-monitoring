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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in Alert._meta.fields]

    @admin.action(description='Re-run investigation for failed/queued/stale running')
    def rerun_investigation(self, request, queryset):
        from agent.tasks import run_investigation

        count = 0
        for alert in queryset:
            if alert.investigation_status not in ['failed', 'queued'] and not (alert.investigation_status == 'running' and alert.investigation_started_at and (timezone.now() - alert.investigation_started_at).total_seconds() > 360):
                continue
            try:
                with transaction.atomic():
                    alert.investigation_status = 'queued'
                    alert.investigation_error = ''
                    alert.ai_summary = ''
                    alert.ai_recommended_actions = []
                    alert.investigation_attempts = 0
                    alert.ai_used_tool = False
                    alert.save(update_fields=['investigation_status', 'investigation_error', 'ai_summary', 'ai_recommended_actions', 'investigation_attempts', 'ai_used_tool', 'updated_at'])
                transaction.on_commit(lambda a=alert: run_investigation.delay(a.id))
                count += 1
            except Exception:
                alert.investigation_status = 'failed'
                alert.investigation_error = 'queue_unavailable'
                alert.save(update_fields=['investigation_status', 'investigation_error', 'updated_at'])
        self.message_user(request, f'Requeued {count} alerts')
