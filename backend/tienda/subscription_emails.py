"""Persistent welcome outbox using Misso's existing Resend transport and branding."""
import logging
from datetime import timedelta
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone
from .email_utils import LOGO_URL
from .models import EmailSuscripcion, Suscripcion
from .subscription_api import public_url

logger = logging.getLogger(__name__)


def queue_welcome(sub):
    context = {'sub': sub, 'logo_url': LOGO_URL, 'home_url': public_url('inicio'),
               'panel_url': public_url('panel:suscripcion_detalle', pk=sub.pk)}
    for kind, recipient, subject in [('cliente', sub.email, '¡Ya sos parte de Misso! ♡'),
                                      ('admin', settings.MISSO_ADMIN_EMAIL, 'Nueva suscripción en Misso ♡')]:
        if not EmailSuscripcion.objects.filter(suscripcion=sub, tipo=kind).exists():
            EmailSuscripcion.objects.create(suscripcion=sub, tipo=kind, payload={
                'from': settings.MISSO_EMAIL_FROM, 'to': [recipient or ''], 'subject': subject,
                'html': render_to_string(f'tienda/emails/suscripcion_{kind}.html', context),
            })


def send_welcome(email_id):
    now = timezone.now()
    # Persist before the remote side effect; SQL rollback cannot unsend an email.
    EmailSuscripcion.objects.filter(pk=email_id, primer_intento_at__isnull=True).update(primer_intento_at=now)
    with transaction.atomic():
        email = EmailSuscripcion.objects.select_for_update().get(pk=email_id)
        if email.enviado_at or email.revision_manual:
            return
        # Resend retains idempotency keys 24h. Do NOT resend ambiguous deliveries beyond it.
        if now - email.primer_intento_at >= timedelta(hours=23):
            email.revision_manual = True
            email.error = 'Revisar entrega en Resend: venció la ventana de reintento seguro.'
            email.save()
            return
        email.intentos += 1
        error = ''
        try:
            if not settings.RESEND_API_KEY or not all(email.payload.get('to', [])):
                raise ValueError
            response = requests.post('https://api.resend.com/emails',
                headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}', 'Content-Type': 'application/json',
                         'Idempotency-Key': f'misso-sub-{email.suscripcion_id}-{email.tipo}'},
                json=email.payload, timeout=(3, 8), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                error = f'resend_http_{response.status_code}'
            else:
                provider_id = response.json().get('id')
                if not provider_id:
                    raise ValueError
                email.proveedor_id = str(provider_id)[:100]
                email.enviado_at = timezone.now()
                field = 'confirmation_email_sent_at' if email.tipo == 'cliente' else 'admin_email_sent_at'
                Suscripcion.objects.filter(pk=email.suscripcion_id).update(**{field: email.enviado_at})
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            error = 'resend_delivery_unconfirmed'
        email.error = error
        email.proximo_intento_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(email.intentos, 7))) if error else None
        email.save()
        logger.log(logging.WARNING if error else logging.INFO, 'subscription email local_id=%s type=%s outcome=%s', email.suscripcion_id, email.tipo, error or 'sent')


def due_emails():
    return EmailSuscripcion.objects.filter(enviado_at__isnull=True, revision_manual=False).filter(Q(proximo_intento_at__isnull=True) | Q(proximo_intento_at__lte=timezone.now()))
