import hashlib
import secrets
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import CodigoPromocional, NewsletterContacto


class NewsletterForm(forms.Form):
    email = forms.EmailField(max_length=254)
    # The "Suscribirme" submit button supplies this explicit opt-in value.
    consentimiento = forms.BooleanField(required=True)
    website = forms.CharField(required=False)

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


def _reply(request, message, *, status=200, ok=False):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': ok, 'message': message}, status=status)
    if ok:
        messages.success(request, message, extra_tags='newsletter')
    else:
        messages.error(request, message, extra_tags='newsletter')
    next_url = request.POST.get('next', '/')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('inicio')
    return redirect(next_url)


@never_cache
@require_POST
def registrar_newsletter(request):
    # Limit repeated submissions per visitor; the hidden field catches simple bots.
    ip = request.META.get('REMOTE_ADDR', '')
    key = 'newsletter:' + hashlib.sha256(ip.encode()).hexdigest()
    if cache.add(key, 1, timeout=3600):
        attempts = 1
    else:
        attempts = cache.incr(key)
    if attempts > 6:
        return _reply(request, 'Demasiados intentos. Probá de nuevo más tarde.', status=429)

    form = NewsletterForm(request.POST)
    if form.is_valid() and form.cleaned_data['website']:
        return _reply(request, 'No pudimos procesar tu solicitud.', status=400)
    if not form.is_valid():
        return _reply(request, 'Ingresá un correo válido para suscribirte a las novedades.', status=400)

    with transaction.atomic():
        contacto, created = NewsletterContacto.objects.get_or_create(
            email=form.cleaned_data['email'],
            defaults={
                'consentimiento_comercial': True,
                'consentimiento_fecha': timezone.now(),
            },
        )
        if not created:
            contacto = NewsletterContacto.objects.select_for_update().get(pk=contacto.pk)
            if not contacto.activo:
                contacto.activo = True
                contacto.consentimiento_comercial = True
                contacto.consentimiento_fecha = timezone.now()
                contacto.save(update_fields=['activo', 'consentimiento_comercial', 'consentimiento_fecha'])
        if not contacto.codigo_promocional_id:
            codigo = CodigoPromocional.objects.create(
                codigo=f'MISSO10-{secrets.token_hex(8).upper()}',
                descuento_porcentaje=Decimal('10.00'),
                usos_maximos=1,
                activo=True,
            )
            contacto.codigo_promocional = codigo
            contacto.save(update_fields=['codigo_promocional'])
        else:
            codigo = contacto.codigo_promocional

    if codigo.es_valido():
        return _reply(request, f'Tu código de 10% OFF es {codigo.codigo}. Usalo en el carrito.', ok=True)
    return _reply(request, 'Tu correo está registrado. El beneficio de 10% ya fue utilizado.', ok=True)
