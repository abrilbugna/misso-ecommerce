"""Tracking security and DNI capture; all tests use the isolated test database."""
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from .forms import CheckoutForm
from .models import Orden, IntentoSeguimiento, OpcionEnvio
from .order_identity import normalize_dni, dni_digest, matches_dni
from .order_tracking import CORREO_TRACKING_URL, GENERIC_ERROR
from .email_utils import payload_despacho


@override_settings(ALLOWED_HOSTS=['testserver'], SITE_URL='https://misso.ar', ORDER_DNI_KEY='test-only-dni-key')
class OrderTrackingTests(TestCase):
    def setUp(self):
        self.url = reverse('seguir_pedido')
        self.order = Orden.objects.create(nombre='Nombre privado', email='private@example.test',
            telefono='3517777777', direccion='Calle privada 987', total=100,
            estado='en_envio', transportista='correo_argentino', codigo_seguimiento='CP123456789AR',
            plazo_dias_habiles=7, despachado_at=timezone.now())
        self.order.dni_hash = dni_digest('12.345.678', self.order.seguimiento_token)
        self.order.save(update_fields=['dni_hash'])

    def lookup(self, client=None, **data):
        return (client or self.client).post(self.url, {'numero': self.order.pk, 'dni': '12345678', **data}, follow=True)

    def private(self, client=None):
        return (client or self.client).get(reverse('seguir_pedido_token', args=[self.order.seguimiento_token]), follow=True)

    def test_normalization_keyed_per_order_digest(self):
        self.assertEqual(normalize_dni(' 12.345.678 '), '12345678')
        self.assertTrue(matches_dni(self.order, '12345678'))
        self.assertFalse(matches_dni(self.order, '87654321'))
        self.assertNotIn('12345678', self.order.dni_hash)
        self.assertNotEqual(self.order.dni_hash, dni_digest('12345678', uuid.uuid4()))
        with override_settings(ORDER_DNI_KEY='different-key'):
            self.assertFalse(matches_dni(self.order, '12345678'))
        for value in ['123', '123456789', '12-345-678', '１２３４５６７８', '00000000', 'abc12345', '1.2.345678']:
            with self.assertRaises(ValidationError):
                normalize_dni(value)

    def test_dni_grants_only_status_never_postal_or_checkout_access(self):
        response = self.lookup(dni='12.345.678')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Pedido #{self.order.pk}')
        self.assertContains(response, 'está en camino')
        self.assertFalse(response.context['private_access'])
        self.assertNotIn('tracking_access', self.client.session)
        self.assertNotIn('dni', self.client.session['tracking_summary'])
        for secret in [self.order.email, self.order.telefono, self.order.direccion, self.order.nombre,
                       self.order.codigo_seguimiento, str(self.order.seguimiento_token), '12345678', '12.345.678']:
            self.assertNotContains(response, secret)
        for name in ['pago_mp', 'confirmacion', 'confirmacion_transferencia']:
            self.assertRedirects(self.client.get(reverse(name, args=[self.order.pk])), self.url)

    def test_same_error_for_wrong_missing_and_historical_dni(self):
        old = Orden.objects.create(nombre='Viejo', total=10, email='old@example.test')
        for number, dni in [(self.order.pk, '87654321'), (98765, '12345678'), (old.pk, '12345678'), (self.order.pk, 'invalid')]:
            response = self.lookup(numero=number, dni=dni)
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, GENERIC_ERROR, status_code=400)
            self.assertIsNone(response.context['order'])
        self.assertEqual(self.client.post(self.url, {'numero': self.order.pk, 'email': self.order.email}).status_code, 400)
        response = Client().get(reverse('seguir_pedido_token', args=[old.seguimiento_token]), follow=True)
        self.assertContains(response, f'Pedido #{old.pk}')

    def test_private_link_shows_dispatch_and_email_still_targets_it(self):
        response = self.private()
        self.assertContains(response, self.order.codigo_seguimiento)
        self.assertContains(response, '7 días hábiles')
        self.assertContains(response, CORREO_TRACKING_URL)
        self.assertContains(response, 'data-copy-tracking')
        self.assertContains(response, 'data-copy-status')
        self.assertContains(response, 'js/seguimiento.js')
        self.assertEqual(response.redirect_chain[0][0], self.url)
        self.assertNotContains(response, str(self.order.seguimiento_token))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        payload = payload_despacho(self.order)
        self.assertIn(reverse('seguir_pedido_token', args=[self.order.seguimiento_token]), payload['html'])
        self.assertNotIn('12345678', payload['html'].replace(self.order.codigo_seguimiento, ''))

    def test_states_and_no_postal_details_for_cancelled_undispatched_or_pickup(self):
        self.private()
        for state, text in [('en_proceso', 'revisando los detalles'), ('confirmado', 'está confirmado'),
                            ('en_envio', 'está en camino'), ('entregado', 'ya fue entregado'), ('cancelado', 'está cancelado')]:
            Orden.objects.filter(pk=self.order.pk).update(estado=state)
            response = self.client.get(self.url)
            self.assertContains(response, text)
            if state in ('en_envio', 'entregado'):
                self.assertContains(response, self.order.codigo_seguimiento)
            else:
                self.assertNotContains(response, self.order.codigo_seguimiento)
            if state == 'cancelado':
                self.assertNotContains(response, 'aria-label="Progreso del pedido"')
        for carrier, dispatched in [('retiro', timezone.now()), ('otro', timezone.now()), ('correo_argentino', None)]:
            Orden.objects.filter(pk=self.order.pk).update(estado='en_envio', transportista=carrier, despachado_at=dispatched)
            response = self.client.get(self.url)
            self.assertNotContains(response, self.order.codigo_seguimiento)
            self.assertNotContains(response, CORREO_TRACKING_URL)
            if carrier == 'retiro':
                self.assertContains(response, 'listo para retirar')

    def test_number_limit_shared_between_ips_and_ip_limit_ignores_forwarded_header(self):
        for index in range(10):
            self.client.post(self.url, {'numero': self.order.pk, 'dni': '87654321'}, REMOTE_ADDR=f'10.0.0.{index}')
        self.assertEqual(self.client.post(self.url, {'numero': '000'+str(self.order.pk), 'dni': '12345678'}, REMOTE_ADDR='10.0.0.99').status_code, 429)
        for alternate in ['+' + str(self.order.pk), str(self.order.pk) + '.0']:
            self.assertEqual(self.client.post(self.url, {'numero': alternate, 'dni': '12345678'}, REMOTE_ADDR='10.0.0.98').status_code, 429)
        IntentoSeguimiento.objects.all().delete()
        for index in range(30):
            self.client.post(self.url, {'numero': index+100, 'dni': '12345678'}, HTTP_X_FORWARDED_FOR=f'10.0.0.{index}')
        self.assertEqual(self.lookup().status_code, 429)
        self.assertNotIn('12345678', ''.join(IntentoSeguimiento.objects.values_list('clave', flat=True)))
        IntentoSeguimiento.objects.update(inicio=timezone.now()-timedelta(minutes=16))
        self.assertEqual(self.lookup().status_code, 200)

    def test_csrf_invalid_token_expiration_and_failed_lookup_clear_access(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, {'dni': '12345678', 'numero': self.order.pk}).status_code, 403)
        self.assertEqual(self.client.get(reverse('seguir_pedido_token', args=[uuid.uuid4()])).status_code, 400)
        self.private()
        self.lookup(dni='87654321')
        self.assertIsNone(self.client.get(self.url).context['order'])
        self.lookup()
        session = self.client.session
        session['tracking_summary']['expires'] = 0
        session.save()
        self.assertIsNone(self.client.get(self.url).context['order'])
        self.assertIsNone(Client().get(self.url, {'numero': self.order.pk, 'dni': '12345678'}).context['order'])

    def test_checkout_requires_dni_and_footer_navigation_use_existing_routes(self):
        shipping = OpcionEnvio.objects.create(nombre='Retiro', costo=0)
        data = dict(nombre='Buyer', email='buyer@example.test', telefono='123', direccion='Dirección', envio=shipping.pk, metodo_pago='efectivo')
        self.assertFalse(CheckoutForm(data).is_valid())
        self.assertFalse(CheckoutForm({**data, 'dni':'abc12345'}).is_valid())
        form = CheckoutForm({**data, 'dni':'12.345.678'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['dni'], '12345678')
        response = self.client.get(self.url)
        self.assertContains(response, f'class="site-footer-tracking" href="{self.url}"')
        self.assertContains(response, 'hero-shop misso-pill-button misso-pill-right')
        self.assertContains(response, 'misso-pill-button')
        self.assertContains(response, 'Tu DNI')

    def test_removed_recovery_cannot_send_email_or_grant_access(self):
        from .models import EmailOrden
        response = self.client.get(self.url)
        for removed in ('tracking-recovery', 'Solicitar mi enlace', 'sin DNI', 'recovery-email'):
            self.assertNotContains(response, removed)
        response = self.client.post(self.url, {
            'action': 'access_link', 'recovery-numero': self.order.pk,
            'recovery-email': self.order.email,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(response.context['order'])
        self.assertNotIn('tracking_access', self.client.session)
        self.assertFalse(EmailOrden.objects.exists())
        self.assertContains(self.private(), self.order.codigo_seguimiento)
