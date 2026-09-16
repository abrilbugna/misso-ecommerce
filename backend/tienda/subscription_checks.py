"""Local diagnostics only: never contact Mercado Pago from Django checks."""
from django.conf import settings
from django.core.checks import Warning, register
from .subscription_api import MPSubscriptionError, access_token, public_base


@register()
def subscription_configuration(app_configs, **kwargs):
    if not settings.MP_SUBSCRIPTION_ENABLED:
        return []
    warnings = []
    for validate, identifier in ((access_token, 'tienda.W101'), (public_base, 'tienda.W102')):
        try:
            validate()
        except MPSubscriptionError as exc:
            warnings.append(Warning(f'Suscripciones: {exc.code}.',
                hint='Configurar .env según docs/suscripciones.md (PASOS PARA ABRIL).', id=identifier))
    if not settings.MP_WEBHOOK_SECRET:
        warnings.append(Warning('Falta MP_WEBHOOK_SECRET: el checkout puede iniciar, pero no se confirmarán webhooks.', id='tienda.W103'))
    if not settings.MISSO_ADMIN_EMAIL or not settings.RESEND_API_KEY:
        warnings.append(Warning('Correo de suscripciones incompleto: revisar MISSO_ADMIN_EMAIL y RESEND_API_KEY.', id='tienda.W104'))
    return warnings
