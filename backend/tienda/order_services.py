"""Order transitions shared by the custom panel, Django Admin and payment API."""
import re
from collections import Counter

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Orden, TalleProducto

EDITABLE_FIELDS = ('estado', 'pagado', 'transportista', 'codigo_seguimiento', 'plazo_dias_habiles')
REVISION_FIELDS = ('estado', 'pagado', 'version', 'pago_origen', 'mp_payment_id',
                   'transportista', 'codigo_seguimiento', 'plazo_dias_habiles')
TRANSITIONS = {
    'en_proceso': {'confirmado', 'cancelado'},
    'confirmado': {'en_envio', 'cancelado'},
    'en_envio': {'entregado'},
    'entregado': set(),
    'cancelado': {'en_proceso', 'confirmado'},
}


def order_revision(order):
    return signing.dumps({'pk': order.pk, **{key: getattr(order, key) for key in REVISION_FIELDS}}, salt='panel.order')


def check_revision(order, revision):
    try:
        previous = signing.loads(revision, salt='panel.order')
    except (signing.BadSignature, TypeError):
        raise ValidationError('La ficha venció. Recargá el pedido.')
    current = {'pk': order.pk, **{key: getattr(order, key) for key in REVISION_FIELDS}}
    if previous != current:
        raise ValidationError('El pedido cambió mientras lo editabas. Recargá antes de guardar.')


def suggested_carrier(order):
    name = (order.envio.nombre if order.envio else '').casefold()
    if 'correo argentino' in name:
        return 'correo_argentino'
    if 'retiro' in name or 'retirar' in name:
        return 'retiro'
    return ''


def validate_order_update(order, cleaned):
    check_revision(order, cleaned.get('revision'))
    new = {key: cleaned.get(key, getattr(order, key)) for key in EDITABLE_FIELDS}
    new['codigo_seguimiento'] = new['codigo_seguimiento'].strip().upper()
    state = new['estado']
    if state not in TRANSITIONS or (state != order.estado and state not in TRANSITIONS.get(order.estado, set())):
        raise ValidationError('Transición inválida. Seguí En proceso → Confirmado → En envío → Entregado. Los pedidos despachados no se cancelan desde este flujo.')
    if order.metodo_pago == 'mercadopago' and new['pagado'] != order.pagado:
        raise ValidationError('El pago de Mercado Pago solo puede actualizarse mediante su verificación automática.')
    if state in ('confirmado', 'en_envio', 'entregado') and state != order.estado:
        if order.metodo_pago != 'efectivo' and not new['pagado']:
            raise ValidationError('Verificá el pago antes de confirmar o despachar este pedido.')
    if order.estado in ('confirmado', 'en_envio', 'entregado') and order.metodo_pago != 'efectivo' and order.pagado and not new['pagado']:
        raise ValidationError('No se puede quitar el pago de un pedido ya confirmado.')
    if new['transportista'] not in ('', 'correo_argentino', 'retiro', 'otro'):
        raise ValidationError('Seleccioná un transportista válido.')
    days = new['plazo_dias_habiles']
    if days is not None and (not isinstance(days, int) or not 1 <= days <= 90):
        raise ValidationError('El plazo debe ser entre 1 y 90 días hábiles.')
    code = new['codigo_seguimiento']
    if code and not re.fullmatch(r'[A-Z0-9]{8,40}', code):
        raise ValidationError('Copiá el código completo de la etiqueta: entre 8 y 40 letras o números, sin espacios ni guiones.')
    if new['transportista'] != 'correo_argentino' and code:
        raise ValidationError('El código postal se utiliza únicamente con Correo Argentino.')
    # Legacy completed orders have no dispatch data; editing them must not invent it.
    dispatch = state == 'en_envio' or (state == 'entregado' and not order.finalizado_historico)
    if dispatch:
        if not new['transportista']:
            raise ValidationError('Seleccioná el transportista o Retiro antes de registrar el despacho.')
        if new['transportista'] == 'correo_argentino' and (not code or days is None):
            raise ValidationError('Para Correo Argentino ingresá el código de seguimiento y el plazo máximo en días hábiles.')
    return new


def _adjust_stock(order, new_state):
    delta = (1 if new_state == 'cancelado' else -1) if (order.estado == 'cancelado') != (new_state == 'cancelado') else 0
    if not delta:
        return
    quantities = Counter()
    for item in order.itemorden_set.all():
        if item.talle_id:
            if item.cantidad <= 0:
                raise ValidationError('El pedido tiene cantidades inválidas. Revisá sus ítems.')
            quantities[item.talle_id] += item.cantidad
    for size in TalleProducto.objects.select_for_update().filter(pk__in=quantities).order_by('pk'):
        stock = size.stock + delta * quantities[size.pk]
        if stock < 0:
            raise ValidationError(f'No hay stock suficiente para reactivar {size.color.nombre}, talle {size.talle}.')
        size.stock = stock
        size.save(update_fields=['stock'])


@transaction.atomic
def update_order(pk, cleaned):
    from .order_emails import queue_dispatch
    order = Orden.objects.select_for_update().get(pk=pk)
    new = validate_order_update(order, cleaned)
    previous_state = order.estado
    dispatch_changed = order.despachado_at and any(
        new[key] != getattr(order, key) for key in ('transportista', 'codigo_seguimiento', 'plazo_dias_habiles'))
    _adjust_stock(order, new['estado'])
    if new['pagado'] != order.pagado:
        order.pago_origen = 'manual' if new['pagado'] else ''
        order.pago_confirmado_at = timezone.now() if new['pagado'] else None
    for key, value in new.items():
        setattr(order, key, value)
    dispatch = previous_state != 'en_envio' and order.estado == 'en_envio'
    if dispatch:
        order.despachado_at = timezone.now()
    if previous_state != 'entregado' and order.estado == 'entregado':
        order.entregado_at = timezone.now()
    order.version += 1
    order.save()
    if dispatch_changed:
        # A queued snapshot may contain a mistyped code. Its idempotency key
        # cannot safely be reused with new contents: require an explicit resend.
        order.emails.filter(tipo='despacho', enviado_at__isnull=True, retirado_at__isnull=True).update(
            revision_manual=True, error='Los datos del despacho cambiaron. Revisá Resend y reenviá con los datos actuales.')
    if dispatch:
        queue_dispatch(order)
    return order


@transaction.atomic
def confirm_verified_payment(pk, payment_id, amount):
    """Called only after fetching an approved ARS payment from Mercado Pago's API."""
    from .order_emails import queue_initial
    try:
        order = Orden.objects.select_for_update().get(pk=pk, metodo_pago='mercadopago')
    except Orden.DoesNotExist:
        return None
    if order.total != amount:
        return None
    if order.mp_payment_id and order.mp_payment_id != payment_id:
        return order  # An additional payment must not replay fulfilment or emails.
    if not order.mp_payment_id:
        order.mp_payment_id = payment_id
        order.pagado = True
        order.pago_origen = 'mercadopago'
        order.pago_confirmado_at = timezone.now()
        if order.estado == 'en_proceso':
            order.estado = 'confirmado'
        order.version += 1
        order.save()
    queue_initial(order)
    return order
