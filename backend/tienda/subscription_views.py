import hashlib
import json
import logging
import uuid
from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from mercadopago.webhook import WebhookSignatureValidator, InvalidWebhookSignatureError
from .models import Suscripcion, EventoMercadoPago
from .subscription_forms import SuscripcionForm
from .subscription_services import create_intention, start_checkout
from .subscription_api import MPSubscriptionError, resource_id

logger = logging.getLogger(__name__)
TOPICS = {'subscription_preapproval', 'subscription_authorized_payment', 'payment'}


def submission_key(request):
    current = request.session.get('subscription_submission_key')
    # A deliberate new visit after a completed contract may start another one
    # (for example a gift). Pending forms/tabs continue to share the same key.
    if current and request.method == 'GET' and Suscripcion.objects.filter(
            submission_key=current, estado__in=['activa', 'cancelada']).exists():
        del request.session['subscription_submission_key']
    if 'subscription_submission_key' not in request.session:
        request.session['subscription_submission_key'] = str(uuid.uuid4())
    return request.session['subscription_submission_key']


@never_cache
@require_http_methods(['GET', 'POST'])
def comenzar(request):
    key = submission_key(request)
    initial = {'submission_token': signing.dumps(key, salt='misso-submission')}
    form = SuscripcionForm(request.POST if request.method == 'POST' else None, initial=initial)
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            token = signing.loads(form.cleaned_data['submission_token'], salt='misso-submission', max_age=86400)
            if not constant_time_compare(str(token), key):
                raise signing.BadSignature
        except signing.BadSignature:
            form.add_error(None, 'Este formulario venció. Recargá la página para continuar.')
            status = 400
        else:
            sub = create_intention(form, uuid.UUID(key))
            try:
                sub = start_checkout(sub)
                if sub.estado == 'pendiente' and sub.init_point:
                    return redirect(sub.init_point)
                return redirect('suscripcion_resultado', referencia=sub.referencia_publica)
            except MPSubscriptionError as exc:
                logger.warning('[SUBSCRIPTION] local_id=%s code=%s %s', sub.pk, exc.code,
                    'Mercado Pago subscriptions are disabled by configuration.' if exc.code == 'subscriptions_disabled' else '')
                if settings.DEBUG:
                    form.add_error(None, {
                        'subscriptions_disabled': 'Mercado Pago subscriptions are disabled by configuration.',
                        'missing_test_access_token': 'Falta configurar MP_SUBSCRIPTION_TEST_ACCESS_TOKEN del vendedor de prueba.',
                        'mp_not_configured': 'Falta configurar MP_ACCESS_TOKEN.',
                        'invalid_public_base_url': 'Configurá PUBLIC_BASE_URL con la URL HTTPS pública de desarrollo.',
                    }.get(exc.code, 'Código de diagnóstico: ' + exc.code))
                form.add_error(None, 'No pudimos iniciar el pago. Probá nuevamente. Tus respuestas quedaron guardadas.')
                status = 503
    elif request.method == 'POST':
        status = 400
    return render(request, 'tienda/formulario_suscripcion.html', {'form': form,
        'subscription_amount': settings.MP_SUBSCRIPTION_AMOUNT, 'subscription_currency': settings.MP_SUBSCRIPTION_CURRENCY}, status=status)


@never_cache
@require_GET
def resultado(request, referencia):
    sub = get_object_or_404(Suscripcion, referencia_publica=referencia)
    response = render(request, 'tienda/suscripcion_resultado.html', {'sub': sub})
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@never_cache
@require_GET
def estado(request, referencia):
    sub = get_object_or_404(Suscripcion, referencia_publica=referencia)
    # No personal details, remote writes or GET-controlled states.
    return JsonResponse({'estado': sub.estado})


@csrf_exempt
@require_POST
def webhook(request):
    if not settings.MP_SUBSCRIPTION_ENABLED or not settings.MP_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    if len(request.body) > 16384:
        return HttpResponse(status=413)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not isinstance(data.get('data'), dict):
            raise ValueError
        identifier = resource_id(request.GET.get('data.id')).lower()
        if str(data['data'].get('id', '')).lower() != identifier:
            raise ValueError
        WebhookSignatureValidator.validate(request.headers.get('x-signature'), request.headers.get('x-request-id'),
                                           identifier, settings.MP_WEBHOOK_SECRET)
        topic = data.get('type')
        if not isinstance(topic, str):
            raise ValueError
    except InvalidWebhookSignatureError:
        logger.warning('subscription webhook signature rejected')
        return HttpResponse(status=401)
    except (ValueError, TypeError, KeyError, MPSubscriptionError):
        return HttpResponse(status=400)
    if topic not in TOPICS:
        return HttpResponse(status=200)
    identity = [topic, identifier, str(data.get('id') or request.headers.get('x-signature'))]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    linked = Suscripcion.objects.filter(mp_preapproval_id=identifier).first() if topic == 'subscription_preapproval' else None
    event, created = EventoMercadoPago.objects.get_or_create(clave=key, defaults={
        'topico': topic, 'recurso_id': identifier, 'accion': str(data.get('action', ''))[:100], 'suscripcion': linked})
    logger.info('subscription webhook received event_id=%s duplicate=%s', event.pk, not created)
    # Acknowledge only after the durable inbox insert; the worker verifies MP and retries.
    return HttpResponse(status=200)
