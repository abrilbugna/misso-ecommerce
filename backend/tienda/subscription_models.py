"""Recurring billing records, deliberately independent of orders and stock."""
import uuid
from django.db import models


def subscription_reference():
    return f'MISSO-SUB-{uuid.uuid4()}'


class Suscripcion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        ACTIVA = 'activa', 'Activa'
        PAUSADA = 'pausada', 'Pausada'
        CANCELADA = 'cancelada', 'Cancelada'
        ERROR = 'error', 'Error'

    referencia_publica = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    submission_key = models.UUIDField(unique=True, editable=False)
    external_reference = models.CharField(max_length=64, unique=True, default=subscription_reference, editable=False)
    nombre = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=30)
    destino = models.CharField(max_length=20)
    talle = models.CharField(max_length=20)
    tipo_prenda = models.CharField(max_length=20, blank=True)
    estilo = models.CharField(max_length=20, blank=True)
    respuestas_snapshot = models.JSONField(default=dict)
    terminos_aceptados = models.BooleanField(default=False)
    terminos_aceptados_at = models.DateTimeField(null=True, blank=True)
    terminos_url = models.URLField(max_length=500)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3)
    frecuencia = models.PositiveIntegerField(default=1)
    frecuencia_tipo = models.CharField(max_length=10, default='months')
    mp_preapproval_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    mp_plan_id = models.CharField(max_length=100, blank=True)
    mp_estado = models.CharField(max_length=40, blank=True)
    mp_actualizado_at = models.DateTimeField(null=True, blank=True)
    proximo_cobro_at = models.DateTimeField(null=True, blank=True)
    autorizado_at = models.DateTimeField(null=True, blank=True)
    cancelado_at = models.DateTimeField(null=True, blank=True)
    init_point = models.URLField(max_length=1000, blank=True)
    # new -> creating -> ready; uncertain is reconciled, never blindly POSTed again.
    checkout_estado = models.CharField(max_length=20, default='new')
    checkout_intentado_at = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=200, blank=True)
    ultimo_evento = models.CharField(max_length=120, blank=True)
    ultimo_evento_at = models.DateTimeField(null=True, blank=True)
    confirmation_email_sent_at = models.DateTimeField(null=True, blank=True)
    admin_email_sent_at = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = 'Suscripción'
        verbose_name_plural = 'Suscripciones'

    def __str__(self):
        return f'Suscripción #{self.pk} — {self.get_estado_display()}'

    @property
    def respuestas(self):
        return self.respuestas_snapshot.get('campos', [])


class PagoSuscripcion(models.Model):
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.PROTECT, related_name='pagos')
    mp_authorized_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    mp_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3)
    estado = models.CharField(max_length=40)
    estado_factura = models.CharField(max_length=40, blank=True)
    fecha = models.DateTimeField(null=True, blank=True)
    mp_actualizado_at = models.DateTimeField(null=True, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(mp_authorized_payment_id__isnull=False) | models.Q(mp_payment_id__isnull=False), name='subscription_payment_has_external_id')]


class EventoMercadoPago(models.Model):
    """Durable authenticated inbox. A worker retries failures without losing events."""
    clave = models.CharField(max_length=64, unique=True)
    topico = models.CharField(max_length=60)
    recurso_id = models.CharField(max_length=100)
    accion = models.CharField(max_length=100, blank=True)
    recibido_at = models.DateTimeField(auto_now_add=True)
    procesado_at = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveIntegerField(default=0)
    proximo_intento_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.PROTECT, null=True, blank=True, related_name='eventos')

    class Meta:
        ordering = ['recibido_at']


class EmailSuscripcion(models.Model):
    """Immutable email payload + one delivery record per subscription/recipient."""
    suscripcion = models.ForeignKey(Suscripcion, on_delete=models.PROTECT, related_name='emails')
    tipo = models.CharField(max_length=10, choices=[('cliente', 'Cliente'), ('admin', 'Administrador')])
    payload = models.JSONField(default=dict)
    creado = models.DateTimeField(auto_now_add=True)
    primer_intento_at = models.DateTimeField(null=True, blank=True)
    enviado_at = models.DateTimeField(null=True, blank=True)
    proximo_intento_at = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveIntegerField(default=0)
    proveedor_id = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=200, blank=True)
    revision_manual = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['suscripcion', 'tipo'], name='unique_subscription_welcome_recipient')]
