from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from tienda.models import IntentoSeguimiento
from tienda.order_emails import due_order_emails, send_order_email


class Command(BaseCommand):
    help = 'Procesa notificaciones de pedidos pendientes (ejecutar cada minuto). No procesa suscripciones.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        count = 0
        for pk in list(due_order_emails().values_list('pk', flat=True)[:max(1, options['limit'])]):
            send_order_email(pk)
            count += 1
        IntentoSeguimiento.objects.filter(inicio__lt=timezone.now() - timedelta(days=1)).delete()
        self.stdout.write(f'Notificaciones procesadas: {count}')
