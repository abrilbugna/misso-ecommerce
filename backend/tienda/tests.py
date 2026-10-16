from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Carrito, ItemCarrito, OpcionEnvio, Orden, Producto, EmailOrden
from .order_services import order_revision, update_order
from .views import _confirmar_pago_mercadopago


@override_settings(SUBSCRIPTIONS_PUBLIC_ENABLED=False, MERCADOPAGO_ACCESS_TOKEN='test-token',
                   SITE_URL='https://misso.ar', MISSO_ADMIN_EMAIL='admin@example.test')
class MercadoPagoFlowTests(TestCase):
    def setUp(self):
        self.envio = OpcionEnvio.objects.create(nombre='Correo Argentino', costo=Decimal('20.00'))
        self.producto = Producto.objects.create(nombre='Conjunto', precio=Decimal('100.00'))
        self.transport = self.enterContext(patch('tienda.order_emails.requests.post'))
        self.transport.return_value = Mock(status_code=200, json=lambda: {'id': 'email-test'})
        self.sdk = self.enterContext(patch('tienda.views.mercadopago.SDK'))

    def crear_orden(self, total=Decimal('132.00')):
        order = Orden.objects.create(nombre='Abril', email='abril@example.test', telefono='3511234567',
            direccion='Córdoba 123', subtotal=100, total=total, envio=self.envio, metodo_pago='mercadopago')
        session = self.client.session
        session['checkout_orders'] = [str(order.seguimiento_token)]
        session.save()
        return order

    def payment(self, order, **extra):
        self.sdk.return_value.payment.return_value.get.return_value = {
            'status': 200, 'response': {'id': 123, 'status': 'approved', 'currency_id': 'ARS',
                'external_reference': str(order.pk), 'transaction_amount': str(order.total), **extra}}

    def test_checkout_incluye_envio_y_recargo_sin_enviar_confirmacion(self):
        session = self.client.session
        session.save()
        cart = Carrito.objects.create(session_key=session.session_key)
        ItemCarrito.objects.create(carrito=cart, producto=self.producto, cantidad=1)
        response = self.client.post(reverse('checkout'), {'nombre': 'Abril', 'dni': '12345678', 'email': 'abril@example.test',
            'telefono': '3511234567', 'direccion': 'Córdoba 123', 'envio': self.envio.pk, 'metodo_pago': 'mercadopago'})
        order = Orden.objects.get()
        self.assertRedirects(response, reverse('pago_mp', args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual(order.total, Decimal('132.00'))
        self.assertFalse(order.pagado)
        self.assertEqual(order.estado, 'en_proceso')
        self.assertFalse(EmailOrden.objects.exists())
        self.transport.assert_not_called()

    def test_preferencia_cobra_productos_envio_y_recargo(self):
        order = self.crear_orden()
        preference = self.sdk.return_value.preference.return_value
        preference.create.return_value = {'status': 201, 'response': {'init_point': 'https://mp.test/pagar'}}
        response = self.client.get(reverse('pago_mp', args=[order.pk]))
        self.assertEqual(response.url, 'https://mp.test/pagar')
        data = preference.create.call_args.args[0]
        self.assertEqual(sum(Decimal(str(item['unit_price'])) for item in data['items']), order.total)
        self.assertEqual(data['items'][1]['unit_price'], 20.0)
        self.assertEqual(data['items'][2]['unit_price'], 12.0)
        self.assertEqual(data['notification_url'], 'https://misso.ar/tienda/pago/mp/webhook/')

    def test_pago_aprobado_confirma_y_notifica_una_sola_vez(self):
        order = self.crear_orden()
        self.payment(order)
        with self.captureOnCommitCallbacks(execute=True):
            _confirmar_pago_mercadopago('123')
            _confirmar_pago_mercadopago('123')
        order.refresh_from_db()
        self.assertTrue(order.pagado)
        self.assertEqual(order.estado, 'confirmado')
        self.assertEqual(order.pago_origen, 'mercadopago')
        self.assertEqual(order.mp_payment_id, '123')
        self.assertIsNotNone(order.pago_confirmado_at)
        self.assertEqual(self.transport.call_count, 2)  # One buyer + one store notification.
        self.assertEqual(order.emails.filter(tipo='inicial', enviado_at__isnull=False).count(), 1)

    def test_unverified_payment_never_confirms(self):
        order = self.crear_orden()
        for extra in ({'status': 'pending'}, {'status': 'rejected'}, {'transaction_amount': 120},
                      {'transaction_amount': '132.001'}, {'transaction_amount': 'NaN'},
                      {'external_reference': 'invalid'}, {'external_reference': '99999'},
                      {'currency_id': 'USD'}, {'id': 456}):
            with self.subTest(extra=extra):
                self.payment(order, **extra)
                self.assertIsNone(_confirmar_pago_mercadopago('123'))
        order.refresh_from_db()
        self.assertFalse(order.pagado)
        self.assertEqual(order.estado, 'en_proceso')
        self.assertFalse(EmailOrden.objects.exists())
        self.transport.assert_not_called()

    def test_repeated_webhooks_do_not_regress_dispatch_or_delivery(self):
        order = self.crear_orden()
        self.payment(order)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('mercadopago_webhook'), {'type': 'payment', 'data': {'id': '123'}}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            order = update_order(order.pk, {'revision': order_revision(order), 'estado': 'en_envio', 'pagado': True,
                 'transportista': 'correo_argentino', 'codigo_seguimiento': 'CP123456789AR', 'plazo_dias_habiles': 5})
        for state in ['en_envio', 'entregado']:
            if state == 'entregado':
                order = update_order(order.pk, {'revision': order_revision(order), 'estado': state, 'pagado': True})
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('mercadopago_webhook'), {'type': 'payment', 'data': {'id': '123'}}, content_type='application/json')
            order.refresh_from_db()
            self.assertEqual(order.estado, state)
        self.assertEqual(self.transport.call_count, 3)

    def test_approved_cancelled_order_is_not_reactivated(self):
        order = self.crear_orden()
        order.estado = 'cancelado'
        order.save()
        self.payment(order)
        _confirmar_pago_mercadopago('123')
        order.refresh_from_db()
        self.assertEqual(order.estado, 'cancelado')
        self.assertTrue(order.pagado)

    def test_return_url_status_is_not_trusted(self):
        order = self.crear_orden()
        self.payment(order, status='pending')
        response = self.client.get(reverse('mercadopago_retorno', args=[order.pk]), {'status': 'approved', 'payment_id': '123'})
        self.assertContains(response, 'Continuá en Mercado Pago')
        order.refresh_from_db()
        self.assertFalse(order.pagado)
        self.assertFalse(EmailOrden.objects.exists())

    def test_confirmacion_does_not_confirm_unpaid_mp(self):
        order = self.crear_orden()
        response = self.client.get(reverse('confirmacion', args=[order.pk]))
        self.assertContains(response, 'Continuá en Mercado Pago')
        self.assertNotContains(response, 'Pedido <em>confirmado.</em>', html=True)

    def test_webhook_retries_api_outage(self):
        self.sdk.return_value.payment.return_value.get.side_effect = RuntimeError('offline')
        response = self.client.post(reverse('mercadopago_webhook'), {'type': 'payment', 'data': {'id': '123'}}, content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.sdk.return_value.payment.return_value.get.side_effect = None
        for status in [429, 500, 503]:
            self.sdk.return_value.payment.return_value.get.return_value = {'status': status, 'response': {}}
            response = self.client.post(reverse('mercadopago_webhook'), {'type': 'payment', 'data': {'id': '123'}}, content_type='application/json')
            self.assertEqual(response.status_code, 503)
