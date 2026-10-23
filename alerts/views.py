import ipaddress
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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
            try:
                ipaddress.ip_address(source_ip)
            except Exception:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(source_ip=str(ipaddress.ip_address(source_ip)))

        first_seen_after = request.query_params.get('first_seen_after')
        if first_seen_after:
            dt = parse_datetime(first_seen_after)
            if dt is None:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            if dt.tzinfo is None:
                from django.utils.timezone import make_aware
                dt = make_aware(dt)
            queryset = queryset.filter(first_seen_at__gte=dt)

        first_seen_before = request.query_params.get('first_seen_before')
        if first_seen_before:
            dt = parse_datetime(first_seen_before)
            if dt is None:
                return Response({'detail': 'Invalid filter'}, status=status.HTTP_400_BAD_REQUEST)
            if dt.tzinfo is None:
                from django.utils.timezone import make_aware
                dt = make_aware(dt)
            queryset = queryset.filter(first_seen_at__lte=dt)

        page_size = request.query_params.get('page_size', 25)
        try:
            ps = int(page_size)
        except Exception:
            return Response({'detail': 'Invalid page_size'}, status=status.HTTP_400_BAD_REQUEST)
        if ps < 1:
            return Response({'detail': 'Invalid page_size'}, status=status.HTTP_400_BAD_REQUEST)
        if ps > 100:
            ps = 100

        paginator = PageNumberPagination()
        paginator.page_size = ps
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

        if not isinstance(request.data, dict) or set(request.data.keys()) != {'incident_status'}:
            return Response({'detail': 'Only incident_status allowed'}, status=status.HTTP_400_BAD_REQUEST)

        new_status = request.data.get('incident_status')
        if not isinstance(new_status, str):
            return Response({'detail': 'Invalid transition'}, status=status.HTTP_400_BAD_REQUEST)
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
