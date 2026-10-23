import uuid

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LogEvent
from .permissions import IsIngestor
from .serializers import LogEventSerializer
from detection.service import process_events_for_detection


class EventIngestView(APIView):
    permission_classes = [IsIngestor]

    def post(self, request):
        data = request.data
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return Response({'detail': 'Invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        if len(data) == 0:
            return Response({'detail': 'Empty batch'}, status=status.HTTP_400_BAD_REQUEST)
        if len(data) > settings.MAX_BATCH_SIZE:
            return Response({'detail': 'Batch too large'}, status=status.HTTP_400_BAD_REQUEST)

        serializers_list = []
        for item in data:
            s = LogEventSerializer(data=item)
            if not s.is_valid():
                return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
            serializers_list.append(s)

        # Check for duplicate event_ids within batch
        event_ids = []
        for s in serializers_list:
            eid = s.validated_data.get('event_id')
            if eid is None:
                eid = uuid.uuid4()
                # attach back
                s.validated_data['event_id'] = eid
            event_ids.append(eid)
        # deduplicate within batch by keeping first occurrence
        seen_batch = set()
        unique_indices = []
        for i, eid in enumerate(event_ids):
            if eid in seen_batch:
                continue
            seen_batch.add(eid)
            unique_indices.append(i)

        # check existing
        existing = set(LogEvent.objects.filter(event_id__in=list(seen_batch)).values_list('event_id', flat=True))
        to_create_data = []
        for idx in unique_indices:
            s = serializers_list[idx]
            vd = s.validated_data
            eid = vd['event_id']
            if eid in existing:
                continue
            to_create_data.append(vd)

        created = []
        with transaction.atomic():
            for vd in to_create_data:
                event = LogEvent.objects.create(
                    event_id=vd['event_id'],
                    timestamp=vd['timestamp'],
                    source_ip=vd['source_ip'],
                    dest_ip=vd.get('dest_ip'),
                    dest_port=vd.get('dest_port'),
                    protocol=vd['protocol'],
                    event_type=vd['event_type'],
                    username=vd.get('username'),
                    bytes_sent=vd.get('bytes_sent') or 0,
                    raw=vd.get('raw'),
                )
                created.append(event)
            if created:
                process_events_for_detection(created)

        return Response({'created': len(created)}, status=status.HTTP_201_CREATED)
