from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .models import Alert
from .permissions import IsAnalyst
from .serializers import AlertListSerializer, AlertDetailSerializer


class AlertListView(APIView):
    permission_classes = [IsAnalyst]

    def get(self, request):
        queryset = Alert.objects.all().order_by('-created_at')

        severity = request.query_params.get('severity')
        if severity:
            if severity not in ['high', 'medium']:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(severity=severity)

        incident_status = request.query_params.get('incident_status')
        if incident_status:
            if incident_status not in ['open', 'acknowledged', 'resolved']:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(incident_status=incident_status)

        investigation_status = request.query_params.get('investigation_status')
        if investigation_status:
            if investigation_status not in ['queued', 'running', 'completed', 'failed']:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(investigation_status=investigation_status)

        rule_name = request.query_params.get('rule_name')
        if rule_name:
            if rule_name not in ['brute_force', 'port_scan']:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(rule_name=rule_name)

        source_ip = request.query_params.get('source_ip')
        if source_ip:
            queryset = queryset.filter(source_ip=source_ip)

        paginator = PageNumberPagination()
        paginator.page_size = min(int(request.query_params.get('page_size', 25)), 100)
        page = paginator.paginate_queryset(queryset, request)
        serializer = AlertListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AlertDetailView(APIView):
    permission_classes = [IsAnalyst]

    def get(self, request, pk):
        try:
            alert = Alert.objects.get(pk=pk)
        except Alert.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = AlertDetailSerializer(alert)
        return Response(serializer.data)

    def patch(self, request, pk):
        try:
            alert = Alert.objects.get(pk=pk)
        except Alert.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if set(request.data.keys()) != {'incident_status'}:
            return Response({'detail': 'Only incident_status allowed'}, status=status.HTTP_400_BAD_REQUEST)

        new_status = request.data.get('incident_status')
        allowed_transitions = {
            'open': ['acknowledged', 'resolved'],
            'acknowledged': ['resolved'],
            'resolved': [],
        }
        if new_status not in allowed_transitions.get(alert.incident_status, []):
            return Response({'detail': 'Invalid transition'}, status=status.HTTP_400_BAD_REQUEST)

        alert.incident_status = new_status
        alert.status_changed_by = request.user
        alert.status_changed_at = timezone.now()
        alert.save(update_fields=['incident_status', 'status_changed_by', 'status_changed_at', 'updated_at'])
        return Response(AlertDetailSerializer(alert).data)
