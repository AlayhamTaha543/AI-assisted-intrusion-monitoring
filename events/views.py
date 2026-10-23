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
        for idx, item in enumerate(data):
            s = LogEventSerializer(data=item)
            if not s.is_valid():
                return Response({'errors': [{'index': idx, 'errors': s.errors}]}, status=status.HTTP_400_BAD_REQUEST)
            serializers_list.append((idx, s))

        event_ids = []
        for _, s in serializers_list:
            event_ids.append(s.validated_data['event_id'])

        # deduplicate within batch
        seen_batch = set()
        unique_list = []
        for orig_idx, s in serializers_list:
            eid = s.validated_data['event_id']
            if eid in seen_batch:
                continue
            seen_batch.add(eid)
            unique_list.append(s)

        existing = set(LogEvent.objects.filter(event_id__in=list(seen_batch)).values_list('event_id', flat=True))
        to_create_data = []
        for s in unique_list:
            vd = dict(s.validated_data)
            eid = vd['event_id']
            if eid in existing:
                continue
            to_create_data.append(vd)

        created_events = []
        with transaction.atomic():
            objs = []
            for vd in to_create_data:
                objs.append(LogEvent(
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
                ))
            if objs:
                LogEvent.objects.bulk_create(objs, ignore_conflicts=True)
            created_events = list(LogEvent.objects.filter(event_id__in=[o.event_id for o in objs]))
            submitted_ids = [s.validated_data['event_id'] for s in unique_list]
            all_submitted = list(LogEvent.objects.filter(event_id__in=submitted_ids))
            if all_submitted:
                process_events_for_detection(all_submitted)

        return Response({'received': len(data), 'inserted': len(created_events), 'duplicates': len(data) - len(created_events)}, status=status.HTTP_201_CREATED)
