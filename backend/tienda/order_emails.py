"""Transactional order outbox with bounded retries and Resend idempotency."""
import logging
from datetime import timedelta
from functools import partial

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

from .email_utils import payload_comprobante_cliente, payload_notificacion_tienda, payload_despacho, payload_acceso_pedido
from .models import EmailOrden, Orden

logger = logging.getLogger(__name__)
PAYLOADS = {'inicial': payload_comprobante_cliente, 'admin': payload_notificacion_tienda, 'despacho': payload_despacho, 'acceso': payload_acceso_pedido}


def _schedule(email):
    transaction.on_commit(partial(send_order_email, email.pk), robust=True)


def _queue(order, kind):
    # The caller owns the order row lock (or has just inserted the order).
    email = EmailOrden.objects.filter(orden=order, tipo=kind, secuencia=1).first()
    if email is None:
        email = EmailOrden.objects.create(orden=order, tipo=kind, payload=PAYLOADS[kind](order))
        _schedule(email)
    return email


def queue_initial(order):
    if order.emails_iniciales_preexistentes:
        return
    _queue(order, 'inicial')
    _queue(order, 'admin')


def queue_dispatch(order):
    return _queue(order, 'despacho')


def send_order_email(email_id):
    now = timezone.now()
    # Commit the first attempt before the external effect, even if the process
    # dies after Resend accepts it and before the SQL result is committed.
    EmailOrden.objects.filter(pk=email_id, primer_intento_at__isnull=True,
                              enviado_at__isnull=True, retirado_at__isnull=True).update(primer_intento_at=now)
    with transaction.atomic():
        email = EmailOrden.objects.select_for_update().get(pk=email_id)
        if email.enviado_at or email.retirado_at or email.revision_manual:
            return
        if email.proximo_intento_at and email.proximo_intento_at > now:
            return
        # Resend remembers keys for 24h. Ambiguous deliveries must not be
        # automatically replayed beyond that window with a fresh key.
        if now - email.primer_intento_at >= timedelta(hours=23):
            email.revision_manual = True
            email.error = 'Verificá la entrega en Resend antes de autorizar un reenvío.'
            email.save(update_fields=['revision_manual', 'error'])
            return
        email.intentos += 1
        error = ''
        try:
            if not settings.RESEND_API_KEY or not email.payload.get('to') or not all(email.payload['to']):
                raise ValueError
            response = requests.post('https://api.resend.com/emails',
                headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}', 'Content-Type': 'application/json',
                         'Idempotency-Key': f'misso-order-{email.clave}'},
                json=email.payload, timeout=(3, 8), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                error = f'resend_http_{response.status_code}'
            else:
                provider_id = response.json().get('id')
                if not isinstance(provider_id, str) or not provider_id:
                    raise ValueError
                email.proveedor_id = provider_id[:100]
                email.enviado_at = timezone.now()
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            error = 'resend_delivery_unconfirmed'
        email.error = error
        email.proximo_intento_at = (timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(email.intentos, 7)))) if error else None
        email.save()
        logger.log(logging.WARNING if error else logging.INFO, 'order_email id=%s outcome=%s', email.pk, error or 'sent')


def due_order_emails():
    return EmailOrden.objects.filter(enviado_at__isnull=True, retirado_at__isnull=True, revision_manual=False).filter(
        Q(proximo_intento_at__isnull=True) | Q(proximo_intento_at__lte=timezone.now()))


@transaction.atomic
def request_order_email(order_id, email_id, revision, action):
    from .order_services import check_revision
    order = Orden.objects.select_for_update().get(pk=order_id)
    check_revision(order, revision)
    try:
        email = EmailOrden.objects.select_for_update().get(pk=email_id, orden=order)
    except EmailOrden.DoesNotExist:
        raise ValidationError('La notificación no pertenece a este pedido.')
    if email.retirado_at:
        raise ValidationError('Esta notificación fue reemplazada. Usá la más reciente.')
    if order.emails.filter(tipo=email.tipo, secuencia__gt=email.secuencia).exists():
        raise ValidationError('Usá la notificación más reciente de este tipo para evitar reenvíos duplicados.')
    if action == 'retry':
        if email.enviado_at or email.revision_manual:
            raise ValidationError('Este correo requiere un reenvío explícito, previa revisión en Resend.')
        email.proximo_intento_at = None
        email.save(update_fields=['proximo_intento_at'])
    elif action == 'resend':
        if email.tipo == 'despacho' and (not order.despachado_at or order.estado not in ('en_envio', 'entregado')):
            raise ValidationError('El pedido todavía no está despachado.')
        # Retire an unsent snapshot; never silently mutate a payload already
        # submitted with an idempotency key (e.g. a corrected tracking code).
        if not email.enviado_at:
            email.retirado_at = timezone.now()
            email.save(update_fields=['retirado_at'])
        seq = order.emails.filter(tipo=email.tipo).aggregate(value=Max('secuencia'))['value'] + 1
        email = EmailOrden.objects.create(orden=order, tipo=email.tipo, secuencia=seq, payload=PAYLOADS[email.tipo](order))
    else:
        raise ValidationError('Acción de correo inválida.')
    order.version += 1
    order.save(update_fields=['version'])
    _schedule(email)
    return email

