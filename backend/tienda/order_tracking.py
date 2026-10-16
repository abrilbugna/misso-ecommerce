"""Limited DNI lookup; postal details require the private link sent by email."""
from datetime import timedelta
from time import time

from django import forms
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .models import Orden, IntentoSeguimiento
from .order_identity import normalize_dni, matches_dni
from .order_services import suggested_carrier

GENERIC_ERROR = 'No pudimos validar el acceso. Revisá los datos o usá el enlace privado del email de tu compra.'
# The shorter /seguimiento address currently returns 404; this official page works.
CORREO_TRACKING_URL = 'https://www.correoargentino.com.ar/seguimiento-de-envios'


class TrackingForm(forms.Form):
    dni = forms.CharField(label='Tu DNI', max_length=10,
                         widget=forms.PasswordInput(attrs={'placeholder': 'Tu DNI', 'inputmode': 'numeric', 'autocomplete': 'off'}))
    numero = forms.IntegerField(label='Número de pedido', min_value=1, max_value=9223372036854775807,
                                widget=forms.NumberInput(attrs={'placeholder': 'Número sin #', 'inputmode': 'numeric'}))

    def clean_dni(self):
        return normalize_dni(self.cleaned_data['dni'])


def allow_attempt(request, number=''):
    # REMOTE_ADDR must be set by the trusted deployment proxy. Never trust
    # arbitrary X-Forwarded-For headers supplied by visitors.
    keys = [('ip:' + request.META.get('REMOTE_ADDR', ''), 30)]
    # Normalize exactly as the lookup form (including +1, 01 and 1.0).
    # Otherwise equivalent representations could bypass the per-order limit.
    try:
        number = TrackingForm.base_fields['numero'].clean(number)
    except forms.ValidationError:
        number = None
    if number is not None:
        keys.append(('order:' + str(number), 10))
    allowed = True
    now = timezone.now()
    for value, limit in keys:
        key = salted_hmac('order-tracking-rate', value).hexdigest()
        with transaction.atomic():
            bucket, _ = IntentoSeguimiento.objects.select_for_update().get_or_create(clave=key, defaults={'inicio': now})
            if bucket.inicio <= now - timedelta(minutes=15):
                bucket.inicio, bucket.intentos = now, 0
            bucket.intentos += 1
            bucket.save(update_fields=['inicio', 'intentos'])
            allowed = allowed and bucket.intentos <= limit
    return allowed


def _private(response):
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


def _grant(request, order, private=True):
    request.session.cycle_key()
    key = 'tracking_access' if private else 'tracking_summary'
    # DNI access must never authorize checkout/payment or reveal the private token.
    request.session[key] = ({'token': str(order.seguimiento_token)} if private else {'number': order.pk}) | {'expires': time() + 3600}
    return _private(redirect('seguir_pedido'))


@never_cache
@sensitive_post_parameters('dni')
@require_http_methods(['GET', 'POST'])
def seguir_pedido(request, token=None):
    order = None
    error = ''
    status = 200
    private = False
    form = TrackingForm(request.POST if request.method == 'POST' else None)
    if token is not None or request.method == 'POST':
        request.session.pop('tracking_access', None)
        request.session.pop('tracking_summary', None)
        number = request.POST.get('numero', '')
        if not allow_attempt(request, number):
            error, status = 'Demasiados intentos. Volvé a probar en 15 minutos.', 429
        elif token is not None:
            order = Orden.objects.filter(seguimiento_token=token).first()
        elif form.is_valid():
            candidate = Orden.objects.filter(pk=form.cleaned_data['numero']).first()
            if candidate and matches_dni(candidate, form.cleaned_data['dni']):
                order = candidate
        if order:
            return _grant(request, order, private=token is not None)
        error = error or GENERIC_ERROR
        status = status if status == 429 else 400
    else:
        access = request.session.get('tracking_access', {})
        if access.get('expires', 0) > time() and access.get('token'):
            order = Orden.objects.filter(seguimiento_token=access['token']).first()
            private = order is not None
        summary = request.session.get('tracking_summary', {})
        if not order and summary.get('expires', 0) > time() and summary.get('number'):
            order = Orden.objects.filter(pk=summary['number']).first()
    public = None
    steps = []
    if order:
        # Only fulfilment status for DNI access. Never pass a model to the template.
        public = {'numero': order.pk, 'estado': order.estado, 'estado_label': order.get_estado_display(),
                  'retiro': (order.transportista or suggested_carrier(order)) == 'retiro'}
        if private:
            dispatched = order.estado in ('en_envio', 'entregado') and bool(order.despachado_at)
            postal = dispatched and order.transportista == 'correo_argentino'
            public.update({
                'creado': order.creado, 'pagado': order.pagado,
                'transportista_label': order.get_transportista_display() if dispatched else '',
                'codigo': order.codigo_seguimiento if postal else '',
                'plazo': order.plazo_dias_habiles if dispatched else None,
                'despachado_at': order.despachado_at if dispatched else None,
                'entregado_at': order.entregado_at if order.estado == 'entregado' else None,
            })
        states = [('en_proceso', 'En proceso'), ('confirmado', 'Confirmado'),
                  ('en_envio', 'Listo para retirar' if public['retiro'] else 'En envío'), ('entregado', 'Entregado')]
        current = next((i for i, (key, _) in enumerate(states) if key == order.estado), -1)
        steps = [{'label': label, 'done': i < current, 'current': i == current} for i, (_, label) in enumerate(states)]
    return _private(render(request, 'tienda/seguir_pedido.html', {
        'order': public, 'steps': steps, 'form': form, 'access_error': error,
        'private_access': private, 'correo_tracking_url': CORREO_TRACKING_URL,
    }, status=status))
