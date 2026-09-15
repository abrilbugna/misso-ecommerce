from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Carrito, ItemCarrito, OpcionEnvio, Orden, Producto
from .views import _confirmar_pago_mercadopago


@override_settings(
    MERCADOPAGO_ACCESS_TOKEN='test-token',
    SITE_URL='https://misso.ar',
)
class MercadoPagoFlowTests(TestCase):
    def setUp(self):
        self.envio = OpcionEnvio.objects.create(nombre='Correo Argentino', costo=Decimal('20.00'))
        self.producto = Producto.objects.create(nombre='Conjunto', precio=Decimal('100.00'))

    def crear_orden(self, total=Decimal('132.00')):
        return Orden.objects.create(
            nombre='Abril',
            email='abril@example.com',
            telefono='3511234567',
            direccion='Córdoba 123',
            subtotal=Decimal('100.00'),
            descuento=Decimal('0.00'),
            total=total,
            envio=self.envio,
            metodo_pago='mercadopago',
            estado='en_proceso',
        )

    @patch('tienda.views.enviar_comprobante_cliente')
    @patch('tienda.views.enviar_notificacion_tienda')
    def test_checkout_incluye_envio_y_recargo_sin_enviar_confirmacion(self, notificar, comprobante):
        session = self.client.session
        session.save()
        carrito = Carrito.objects.create(session_key=session.session_key)
        ItemCarrito.objects.create(carrito=carrito, producto=self.producto, cantidad=1)

        response = self.client.post(reverse('checkout'), {
            'nombre': 'Abril',
            'email': 'abril@example.com',
            'telefono': '3511234567',
            'direccion': 'Córdoba 123',
            'envio': self.envio.pk,
            'metodo_pago': 'mercadopago',
        })

        orden = Orden.objects.get()
        self.assertRedirects(response, reverse('pago_mp', args=[orden.pk]), fetch_redirect_response=False)
        self.assertEqual(orden.total, Decimal('132.00'))
        self.assertFalse(orden.pagado)
        notificar.assert_not_called()
        comprobante.assert_not_called()

    @patch('tienda.views.mercadopago.SDK')
    def test_preferencia_cobra_productos_envio_y_recargo(self, sdk_class):
        orden = self.crear_orden()
        preference = Mock()
        preference.create.return_value = {'status': 201, 'response': {'init_point': 'https://mp.test/pagar'}}
        sdk_class.return_value.preference.return_value = preference

        response = self.client.get(reverse('pago_mp', args=[orden.pk]))

        self.assertEqual(response.url, 'https://mp.test/pagar')
        data = preference.create.call_args.args[0]
        self.assertEqual(sum(Decimal(str(item['unit_price'])) for item in data['items']), orden.total)
        self.assertEqual(data['items'][1]['unit_price'], 20.0)
        self.assertEqual(data['items'][2]['unit_price'], 12.0)
        self.assertEqual(data['notification_url'], 'https://misso.ar/tienda/pago/mp/webhook/')

    @patch('tienda.views.enviar_comprobante_cliente')
    @patch('tienda.views.enviar_notificacion_tienda')
    @patch('tienda.views.mercadopago.SDK')
    def test_pago_aprobado_confirma_y_notifica_una_sola_vez(self, sdk_class, notificar, comprobante):
        orden = self.crear_orden()
        payment = Mock()
        payment.get.return_value = {
            'status': 200,
            'response': {
                'status': 'approved',
                'currency_id': 'ARS',
                'external_reference': str(orden.pk),
                'transaction_amount': 132,
            },
        }
        sdk_class.return_value.payment.return_value = payment

        _confirmar_pago_mercadopago('123')
        _confirmar_pago_mercadopago('123')

        orden.refresh_from_db()
        self.assertTrue(orden.pagado)
        self.assertEqual(orden.estado, 'en_proceso')
        notificar.assert_called_once()
        comprobante.assert_called_once()

    @patch('tienda.views.enviar_comprobante_cliente')
    @patch('tienda.views.enviar_notificacion_tienda')
    @patch('tienda.views.mercadopago.SDK')
    def test_pago_pendiente_o_monto_incorrecto_no_confirma(self, sdk_class, notificar, comprobante):
        orden = self.crear_orden()
        payment = Mock()
        sdk_class.return_value.payment.return_value = payment

        for status, amount in [('pending', 132), ('approved', 120)]:
            payment.get.return_value = {
                'status': 200,
                'response': {
                    'status': status,
                    'currency_id': 'ARS',
                    'external_reference': str(orden.pk),
                    'transaction_amount': amount,
                },
            }
            self.assertIsNone(_confirmar_pago_mercadopago('123'))

        orden.refresh_from_db()
        self.assertFalse(orden.pagado)
        self.assertEqual(orden.estado, 'en_proceso')
        notificar.assert_not_called()
        comprobante.assert_not_called()

    @patch('tienda.views._confirmar_pago_mercadopago')
    def test_webhook_procesa_el_id_de_pago(self, confirmar):
        response = self.client.post(
            reverse('mercadopago_webhook'),
            data={'type': 'payment', 'data': {'id': '987654'}},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        confirmar.assert_called_once_with('987654')

    def test_confirmacion_publica_no_confirma_orden_mp_impaga(self):
        orden = self.crear_orden()

        response = self.client.get(reverse('confirmacion', args=[orden.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Continuá en Mercado Pago')
        self.assertNotContains(response, 'Pedido <em>confirmado.</em>', html=True)
