from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from tienda.models import Suscripcion
from tienda.subscription_services import due_events, process_event, recover_checkout, sync_subscription
from tienda.subscription_emails import due_emails, send_welcome
from tienda.subscription_api import MPSubscriptionError


class Command(BaseCommand):
    help = 'Procesa eventos y emails pendientes. Programar cada minuto. No crea planes ni cobra.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--sync', type=int, help='Reconsultar una suscripción local por ID (solo lectura en MP).')

    def handle(self, *args, **options):
        if not settings.MP_SUBSCRIPTION_ENABLED:
            raise CommandError('Suscripciones deshabilitadas. Configurá el entorno antes de ejecutar el worker.')
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('--limit debe estar entre 1 y 1000.')
        if options['sync']:
            sub = Suscripcion.objects.get(pk=options['sync'])
            if not sub.mp_preapproval_id:
                sub = recover_checkout(sub)
            if sub.mp_preapproval_id:
                sync_subscription(sub.mp_preapproval_id)
        for pk in list(due_events().values_list('pk', flat=True)[:options['limit']]):
            process_event(pk)
        # Recover POSTs that might have succeeded remotely before a timeout/process crash.
        for sub in Suscripcion.objects.filter(checkout_estado__in=['creating', 'uncertain'], checkout_intentado_at__lt=timezone.now()-timedelta(minutes=2))[:options['limit']]:
            try:
                recover_checkout(sub)
            except MPSubscriptionError as exc:
                self.stderr.write(f'Intención {sub.pk}: {exc.code}')
        for pk in list(due_emails().values_list('pk', flat=True)[:options['limit']]):
            send_welcome(pk)
        self.stdout.write('Colas de suscripciones procesadas.')
