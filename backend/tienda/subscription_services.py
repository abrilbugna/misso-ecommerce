import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Suscripcion, PagoSuscripcion, EventoMercadoPago
from .subscription_api import SubscriptionAPI, MPSubscriptionError, checkout_url, resource_id, terms_url

logger = logging.getLogger(__name__)
STATES = {'pending': 'pendiente', 'authorized': 'activa', 'paused': 'pausada', 'cancelled': 'cancelada'}


def mp_date(value):
    try:
        result = parse_datetime(value) if isinstance(value, str) else None
        return timezone.make_aware(result) if result and timezone.is_naive(result) else result
    except (ValueError, TypeError):
        return None


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount >= Decimal('10000000000'):
            raise ValueError
        return amount.quantize(Decimal('.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise MPSubscriptionError('invalid_amount') from None


def create_intention(form, key):
    data = form.cleaned_data
    with transaction.atomic():
        sub, created = Suscripcion.objects.get_or_create(submission_key=key, defaults={
            **{k: data[k] for k in ('nombre', 'email', 'telefono', 'destino', 'talle', 'tipo_prenda', 'estilo')},
            'respuestas_snapshot': form.snapshot(), 'terminos_aceptados': True,
            'terminos_aceptados_at': timezone.now(), 'terminos_url': terms_url(),
            'importe': settings.MP_SUBSCRIPTION_AMOUNT, 'moneda': settings.MP_SUBSCRIPTION_CURRENCY,
            'frecuencia': settings.MP_SUBSCRIPTION_FREQUENCY, 'frecuencia_tipo': settings.MP_SUBSCRIPTION_FREQUENCY_TYPE,
        })
        # Only before any remote attempt may the user correct saved responses.
        if not created and sub.checkout_estado in ('new', 'error') and not sub.mp_preapproval_id:
            sub = Suscripcion.objects.select_for_update().get(pk=sub.pk)
            if sub.checkout_estado in ('new', 'error') and not sub.mp_preapproval_id:
                for key in ('nombre', 'email', 'telefono', 'destino', 'talle', 'tipo_prenda', 'estilo'):
                    setattr(sub, key, data[key])
                sub.respuestas_snapshot = form.snapshot()
                sub.terminos_aceptados_at = timezone.now()
                sub.save()
    if created:
        logger.info('subscription intention created local_id=%s', sub.pk)
    return sub


def bind_checkout(sub_id, data):
    with transaction.atomic():
        sub = Suscripcion.objects.select_for_update().get(pk=sub_id)
        identifier = resource_id(data.get('id'))
        if data.get('external_reference') != sub.external_reference or (sub.mp_preapproval_id and sub.mp_preapproval_id != identifier):
            raise MPSubscriptionError('checkout_reference_mismatch', uncertain=True)
        sub.mp_preapproval_id = identifier
        sub.init_point = checkout_url(data.get('init_point'))
        sub.checkout_estado = 'ready'
        sub.ultimo_error = ''
        # Creation/redirect never activates or sends emails, even if the response says authorized.
        sub.save(update_fields=['mp_preapproval_id', 'init_point', 'checkout_estado', 'ultimo_error', 'actualizado'])
        logger.info('[SUBSCRIPTION] preapproval created local_id=%s mp_id=%s init_point=yes', sub.pk, identifier)
        return sub


def recover_checkout(sub):
    data = SubscriptionAPI().search_subscription(sub.external_reference)
    matches = [r for r in data.get('results', []) if r.get('external_reference') == sub.external_reference]
    if len(matches) == 1:
        return bind_checkout(sub.pk, matches[0])
    if len(matches) > 1:
        raise MPSubscriptionError('multiple_remote_subscriptions')
    # An empty search is not proof a timed-out POST did not succeed (eventual consistency).
    return sub


def start_checkout(sub):
    if not settings.MP_SUBSCRIPTION_ENABLED:
        raise MPSubscriptionError('subscriptions_disabled')
    if not settings.MP_SUBSCRIPTION_AMOUNT.is_finite() or settings.MP_SUBSCRIPTION_AMOUNT <= 0 or settings.MP_SUBSCRIPTION_CURRENCY != 'ARS':
        raise MPSubscriptionError('subscriptions_not_configured')
    sub.refresh_from_db()
    if sub.mp_preapproval_id or sub.estado != Suscripcion.Estado.PENDIENTE:
        return sub
    if sub.checkout_estado in ('uncertain', 'creating'):
        return recover_checkout(sub)
    # Claim and COMMIT before the HTTP request. A crash leaves a durable creating record.
    claimed = Suscripcion.objects.filter(pk=sub.pk, checkout_estado__in=['new', 'error'], mp_preapproval_id__isnull=True).update(
        checkout_estado='creating', checkout_intentado_at=timezone.now(), actualizado=timezone.now())
    if not claimed:
        sub.refresh_from_db()
        return sub
    sub.refresh_from_db()
    remote_created = False
    try:
        logger.info('[SUBSCRIPTION] local_id=%s external_reference=%s creating Mercado Pago preapproval', sub.pk, sub.external_reference)
        data = SubscriptionAPI().create_pending(sub)
        logger.info('[SUBSCRIPTION] creation response local_id=%s id_present=%s init_point=%s', sub.pk, bool(data.get('id')), bool(data.get('init_point')))
        remote_created = True
        return bind_checkout(sub.pk, data)
    except MPSubscriptionError as exc:
        Suscripcion.objects.filter(pk=sub.pk, checkout_estado='creating').update(
            checkout_estado='uncertain' if remote_created or exc.uncertain else 'error', ultimo_error=exc.code, actualizado=timezone.now())
        logger.warning('subscription checkout failed local_id=%s code=%s', sub.pk, exc.code)
        raise


def validate_subscription(sub, data):
    recurring = data.get('auto_recurring') or {}
    if data.get('external_reference') != sub.external_reference:
        raise MPSubscriptionError('subscription_reference_mismatch')
    if sub.mp_preapproval_id and str(data.get('id')) != sub.mp_preapproval_id:
        raise MPSubscriptionError('subscription_id_mismatch')
    if (data.get('preapproval_plan_id') or '') != sub.mp_plan_id:
        raise MPSubscriptionError('subscription_plan_mismatch')
    if (money(recurring.get('transaction_amount')) != sub.importe or recurring.get('currency_id') != sub.moneda
            or recurring.get('frequency') != sub.frecuencia or recurring.get('frequency_type') != sub.frecuencia_tipo):
        raise MPSubscriptionError('subscription_terms_mismatch')


def sync_subscription(identifier, event=None):
    api = SubscriptionAPI()
    # Resolve by API reference if a webhook overtakes the POST response. Never by email.
    hint = api.get_subscription(identifier)
    if str(hint.get('id')) != str(identifier):
        raise MPSubscriptionError('subscription_id_mismatch')
    sub = Suscripcion.objects.filter(external_reference=hint.get('external_reference')).first()
    if not sub:
        return None  # Another product/app using this seller, not a Misso intention.
    with transaction.atomic():
        sub = Suscripcion.objects.select_for_update().get(pk=sub.pk)
        # Fetch under the subscription lock so concurrent topics cannot apply stale snapshots.
        data = api.get_subscription(identifier)
        if str(data.get('id')) != str(identifier):
            raise MPSubscriptionError('subscription_id_mismatch')
        validate_subscription(sub, data)
        modified = mp_date(data.get('last_modified'))
        if sub.mp_actualizado_at and modified and modified < sub.mp_actualizado_at:
            return sub
        old = sub.estado
        sub.mp_preapproval_id = resource_id(data.get('id'))
        sub.mp_estado = str(data.get('status', ''))[:40]
        sub.estado = STATES.get(sub.mp_estado, Suscripcion.Estado.ERROR)
        sub.mp_actualizado_at = modified
        sub.proximo_cobro_at = mp_date(data.get('next_payment_date'))
        sub.checkout_estado = 'ready'
        if data.get('init_point'):
            sub.init_point = checkout_url(data['init_point'])
        sub.ultimo_error = '' if sub.estado != 'error' else 'unknown_mp_status'
        if sub.estado == 'activa' and not sub.autorizado_at:
            sub.autorizado_at = modified or timezone.now()
        if sub.estado == 'cancelada' and not sub.cancelado_at:
            sub.cancelado_at = modified or timezone.now()
        if event:
            sub.ultimo_evento = f'{event.topico}:{event.recurso_id}'[:120]
            sub.ultimo_evento_at = event.recibido_at
        sub.save()
        if sub.estado == 'activa':
            from .subscription_emails import queue_welcome
            queue_welcome(sub)
        if old != sub.estado:
            logger.info('subscription state local_id=%s from=%s to=%s', sub.pk, old, sub.estado)
        return sub


def store_invoice(invoice, event=None, payment_override=None):
    identifier = resource_id(invoice.get('preapproval_id'))
    sub = sync_subscription(identifier, event)
    if not sub:
        return None
    invoice_id = resource_id(invoice.get('id'))
    payment = payment_override or invoice.get('payment') or {}
    payment_id = resource_id(payment['id']) if payment.get('id') else None
    # Prefer the Payments resource for actual payment state (refunds/chargebacks included).
    if payment_id and not payment_override:
        payment = SubscriptionAPI().get_payment(payment_id)
    if payment_id and str(payment.get('id')) != payment_id:
        raise MPSubscriptionError('payment_id_mismatch')
    if invoice.get('currency_id') != sub.moneda:
        raise MPSubscriptionError('invoice_currency_mismatch')
    if payment.get('currency_id') and payment['currency_id'] != sub.moneda:
        raise MPSubscriptionError('payment_currency_mismatch')
    with transaction.atomic():
        Suscripcion.objects.select_for_update().get(pk=sub.pk)
        # Keep earlier payment attempts if the recurring invoice acquires a new payment ID.
        existing = PagoSuscripcion.objects.filter(mp_authorized_payment_id=invoice_id).first()
        if existing and existing.suscripcion_id != sub.pk:
            raise MPSubscriptionError('invoice_subscription_mismatch')
        if existing and existing.mp_payment_id and payment_id and existing.mp_payment_id != payment_id:
            if payment_override and str((invoice.get('payment') or {}).get('id')) != payment_id:
                invoice_id = None  # Historical payment event; don't replace the current invoice.
                existing = None
            else:
                existing.mp_authorized_payment_id = None
                existing.save(update_fields=['mp_authorized_payment_id'])
                existing = None
        row = PagoSuscripcion.objects.filter(mp_payment_id=payment_id).first() if payment_id else existing
        row = row or existing or PagoSuscripcion(suscripcion=sub)
        if row.suscripcion_id != sub.pk:
            raise MPSubscriptionError('payment_subscription_mismatch')
        modified = mp_date(payment.get('date_last_updated')) or mp_date(invoice.get('last_modified'))
        if row.mp_actualizado_at and modified and modified < row.mp_actualizado_at:
            return sub
        row.mp_authorized_payment_id = invoice_id
        row.mp_payment_id = payment_id
        row.importe = money(payment.get('transaction_amount', invoice.get('transaction_amount')))
        row.moneda = sub.moneda
        row.estado = str(payment.get('status') or invoice.get('status') or 'unknown')[:40]
        row.estado_factura = str(invoice.get('status') or '')[:40]
        row.fecha = mp_date(payment.get('date_approved')) or mp_date(invoice.get('debit_date')) or mp_date(invoice.get('date_created'))
        row.mp_actualizado_at = modified
        row.save()
        logger.info('subscription payment synchronized local_id=%s payment_local_id=%s', sub.pk, row.pk)
    return sub


def process_event(event_id):
    with transaction.atomic():
        event = EventoMercadoPago.objects.select_for_update().get(pk=event_id)
        if event.procesado_at:
            return
        event.intentos += 1
        try:
            # A savepoint prevents half-updated local state on a validation/API failure.
            with transaction.atomic():
                sub = None
                api = SubscriptionAPI()
                if event.topico == 'subscription_preapproval':
                    sub = sync_subscription(event.recurso_id, event)
                elif event.topico == 'subscription_authorized_payment':
                    invoice = api.get_invoice(event.recurso_id)
                    if str(invoice.get('id')) != event.recurso_id:
                        raise MPSubscriptionError('invoice_id_mismatch')
                    sub = store_invoice(invoice, event)
                elif event.topico == 'payment':
                    payment = api.get_payment(event.recurso_id)
                    if str(payment.get('id')) != event.recurso_id:
                        raise MPSubscriptionError('payment_id_mismatch')
                    results = api.invoices_for_payment(event.recurso_id).get('results', [])
                    for invoice in results:
                        sub = store_invoice(invoice, event, payment)
                    if not results and str(payment.get('external_reference', '')).startswith('MISSO-SUB-'):
                        raise MPSubscriptionError('invoice_not_yet_available')
                event.suscripcion = sub
                event.procesado_at = timezone.now()
                event.error = ''
        except (MPSubscriptionError, ValueError, TypeError, KeyError, AttributeError) as exc:
            event.error = exc.code if isinstance(exc, MPSubscriptionError) else 'invalid_resource_shape'
            event.proximo_intento_at = timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(event.intentos, 7)))
            logger.warning('subscription event failed event_id=%s code=%s', event.pk, event.error)
        event.save()


def due_events():
    return EventoMercadoPago.objects.filter(procesado_at__isnull=True).filter(Q(proximo_intento_at__isnull=True) | Q(proximo_intento_at__lte=timezone.now()))
