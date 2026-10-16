"""Order lifecycle integration tests: isolated SQL, mocked external transport."""
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch
import uuid

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Orden, Producto, OpcionEnvio, ItemOrden, ColorProducto, TalleProducto, Carrito, ItemCarrito, EmailOrden
from .order_emails import send_order_email, request_order_email, queue_initial
from .order_services import update_order, order_revision, confirm_verified_payment
from .email_utils import payload_despacho, payload_comprobante_cliente


@override_settings(SITE_URL='https://misso.ar', MISSO_ADMIN_EMAIL='shop@example.test', ALLOWED_HOSTS=['testserver'])
class OrderManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser('orders', 'staff@example.test', 'test-password')
        cls.product = Producto.objects.create(nombre='Conjunto', precio=100)
        cls.color = ColorProducto.objects.create(producto=cls.product, nombre='Rosa')
        cls.size = TalleProducto.objects.create(color=cls.color, talle='90', stock=5)
        cls.shipping = OpcionEnvio.objects.create(nombre='Correo Argentino', costo=20)

    def setUp(self):
        self.transport = self.enterContext(patch('tienda.order_emails.requests.post'))
        self.transport.return_value = Mock(status_code=200, json=lambda: {'id': 'resend-test-id'})

    def order(self, **extra):
        data = dict(nombre='Compradora', email='buyer@example.test', telefono='3519876543',
                    direccion='Domicilio privado 987', total=120, subtotal=100, envio=self.shipping, metodo_pago='efectivo')
        data.update(extra)
        order = Orden.objects.create(**data)
        ItemOrden.objects.create(orden=order, producto=self.product, color=self.color, talle=self.size, cantidad=1, precio=100)
        return order

    def change(self, order, state, **extra):
        order.refresh_from_db()
        return update_order(order.pk, {'revision': order_revision(order), 'estado': state, 'pagado': order.pagado, **extra})

    def dispatch(self, order):
        order = self.change(order, 'confirmado', pagado=order.metodo_pago != 'efectivo')
        return self.change(order, 'en_envio', transportista='correo_argentino', codigo_seguimiento='CP123456789AR', plazo_dias_habiles=7)

    def test_transfer_checkout_is_pending_and_initial_email_has_instructions(self):
        session = self.client.session
        session.save()
        cart = Carrito.objects.create(session_key=session.session_key)
        ItemCarrito.objects.create(carrito=cart, producto=self.product, color=self.color, talle=self.size, cantidad=1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('checkout'), {'nombre': 'Compradora', 'dni': '12345678', 'email': 'buyer@example.test',
                'telefono': '3519876543', 'direccion': 'Córdoba', 'envio': self.shipping.pk, 'metodo_pago': 'transferencia'})
        order = Orden.objects.get()
        self.assertRedirects(response, reverse('confirmacion_transferencia', args=[order.pk]))
        self.assertEqual(order.estado, 'en_proceso')
        self.assertFalse(order.pagado)
        from .order_identity import matches_dni
        self.assertTrue(matches_dni(order, '12345678'))
        self.assertNotIn('12345678', order.dni_hash)
        email = order.emails.get(tipo='inicial')
        self.assertNotIn('12345678', email.payload['html'])
        self.assertIsNotNone(email.enviado_at)
        self.assertEqual(email.payload['subject'], f'Recibimos tu pedido #{order.pk} ♡ — MISSO')
        for text in ['missocba', 'Conjunto', 'Rosa', '90', 'en proceso', 'no fue confirmado', str(order.seguimiento_token)]:
            self.assertIn(text, email.payload['html'])
        with self.assertRaises(ValidationError):
            self.change(order, 'confirmado')
        with self.captureOnCommitCallbacks(execute=True):
            order = self.change(order, 'confirmado', pagado=True)
        self.assertEqual(order.pago_origen, 'manual')
        self.assertEqual(self.transport.call_count, 2)

    def test_cash_checkout_sends_registered_order_without_claiming_payment(self):
        session = self.client.session
        session.save()
        cart = Carrito.objects.create(session_key=session.session_key)
        ItemCarrito.objects.create(carrito=cart, producto=self.product, cantidad=1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('checkout'), {'nombre': 'Compradora', 'dni': '12345678', 'email': 'buyer@example.test',
                'telefono': '3519876543', 'direccion': 'Córdoba', 'envio': self.shipping.pk, 'metodo_pago': 'efectivo'})
        order = Orden.objects.get()
        self.assertRedirects(response, reverse('confirmacion', args=[order.pk]))
        self.assertEqual(order.estado, 'en_proceso')
        self.assertFalse(order.pagado)
        self.assertIn('Recibimos tu pedido', order.emails.get(tipo='inicial').payload['subject'])
        self.assertContains(self.client.get(response.url), 'Pedido <em>recibido.</em>', html=True)

    def test_correcting_pending_dispatch_pauses_stale_email(self):
        self.transport.side_effect = requests.Timeout()
        with self.captureOnCommitCallbacks(execute=True):
            order = self.dispatch(self.order())
        with self.captureOnCommitCallbacks(execute=True):
            order = self.change(order, 'en_envio', codigo_seguimiento='CP987654321AR')
        email = order.emails.get()
        self.assertTrue(email.revision_manual)
        self.assertEqual(order.emails.count(), 1)
        self.transport.side_effect = None
        call_command('process_order_emails', stdout=StringIO())
        self.assertEqual(self.transport.call_count, 1)
        with self.captureOnCommitCallbacks(execute=True):
            request_order_email(order.pk, email.pk, order_revision(order), 'resend')
        order.refresh_from_db()
        self.assertEqual(self.transport.call_count, 2)
        self.assertIn('CP987654321AR', self.transport.call_args.kwargs['json']['html'])
        with self.assertRaises(ValidationError):
            request_order_email(order.pk, email.pk, order_revision(order), 'resend')

    def test_initial_buyer_and_store_deliveries_recover_independently(self):
        order = self.order()
        self.transport.side_effect = [requests.Timeout(), Mock(status_code=200, json=lambda: {'id': 'admin-sent'})]
        with self.captureOnCommitCallbacks(execute=True):
            queue_initial(order)
        self.assertIsNone(order.emails.get(tipo='inicial').enviado_at)
        self.assertIsNotNone(order.emails.get(tipo='admin').enviado_at)
        self.transport.side_effect = None
        with self.captureOnCommitCallbacks(execute=True):
            queue_initial(order)
        self.assertEqual(self.transport.call_count, 2)
        email = order.emails.get(tipo='inicial')
        email.proximo_intento_at = timezone.now() - timedelta(seconds=1)
        email.save()
        call_command('process_order_emails', stdout=StringIO())
        self.assertEqual(self.transport.call_count, 3)
        self.assertEqual(order.emails.filter(enviado_at__isnull=False).count(), 2)

    def test_cash_confirmation_does_not_collect_payment_or_send_email(self):
        order = self.order()
        with self.captureOnCommitCallbacks(execute=True):
            order = self.change(order, 'confirmado')
        self.assertFalse(order.pagado)
        self.assertEqual(order.estado, 'confirmado')
        self.transport.assert_not_called()

    def test_dispatch_notifies_once_and_correction_is_not_resent(self):
        order = self.order()
        with self.captureOnCommitCallbacks(execute=True):
            order = self.dispatch(order)
        date = order.despachado_at
        self.assertIsNotNone(date)
        email = order.emails.get(tipo='despacho')
        self.assertIsNotNone(email.enviado_at)
        for text in [f'Pedido #{order.pk}', 'CP123456789AR', '7 días hábiles', str(order.seguimiento_token), 'Correo Argentino']:
            self.assertIn(text, email.payload['html'])
        self.assertEqual(email.payload['subject'], f'Tu pedido #{order.pk} está en camino ♡ — MISSO')
        with self.captureOnCommitCallbacks(execute=True):
            self.change(order, 'en_envio')
            order = self.change(order, 'en_envio', codigo_seguimiento='CP987654321AR')
        self.assertEqual(order.despachado_at, date)
        self.assertEqual(order.emails.count(), 1)
        self.assertEqual(self.transport.call_count, 1)
        email.refresh_from_db()
        self.assertIn('CP123456789AR', email.payload['html'])
        with self.captureOnCommitCallbacks(execute=True):
            request_order_email(order.pk, email.pk, order_revision(order), 'resend')
        self.assertEqual(self.transport.call_count, 2)
        self.assertIn('CP987654321AR', order.emails.latest('pk').payload['html'])

    def test_dispatch_validation_and_transition_order(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            self.change(order, 'en_envio')
        order = self.change(order, 'confirmado')
        for extra in ({}, {'transportista': 'correo_argentino'},
                      {'transportista': 'correo_argentino', 'codigo_seguimiento': 'CP123456789AR'},
                      {'transportista': 'correo_argentino', 'codigo_seguimiento': '<bad>', 'plazo_dias_habiles': 5},
                      {'transportista': 'correo_argentino', 'codigo_seguimiento': 'CP123456789AR', 'plazo_dias_habiles': 0},
                      {'transportista': 'retiro', 'codigo_seguimiento': 'CP123456789AR'}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.change(order, 'en_envio', **extra)
        self.assertFalse(EmailOrden.objects.exists())
        order.refresh_from_db()
        self.assertIsNone(order.despachado_at)
        self.assertEqual(order.estado, 'confirmado')

    def test_retiro_and_other_delivery_need_no_postal_tracking(self):
        for carrier in ['retiro', 'otro']:
            order = self.change(self.order(), 'confirmado')
            with self.captureOnCommitCallbacks(execute=True):
                order = self.change(order, 'en_envio', transportista=carrier)
            html = order.emails.get().payload['html']
            self.assertNotIn('correoargentino.com.ar', html)
            self.assertNotIn('Código de seguimiento:', html)
            if carrier == 'retiro':
                self.assertIn('listo para retirar', html)
                self.assertNotIn('ya está en camino', html)

    def test_resend_failure_is_persisted_and_retry_uses_same_payload_and_key(self):
        self.transport.side_effect = requests.Timeout()
        with self.captureOnCommitCallbacks(execute=True):
            order = self.dispatch(self.order())
        order.refresh_from_db()
        email = order.emails.get()
        self.assertEqual(order.estado, 'en_envio')
        self.assertIsNone(email.enviado_at)
        self.assertEqual(email.intentos, 1)
        self.assertTrue(email.error)
        self.assertIsNotNone(email.proximo_intento_at)
        original = self.transport.call_args.kwargs
        self.transport.side_effect = None
        email.proximo_intento_at = timezone.now() - timedelta(seconds=1)
        email.save()
        call_command('process_order_emails', stdout=StringIO())
        email.refresh_from_db()
        self.assertIsNotNone(email.enviado_at)
        self.assertEqual(email.intentos, 2)
        self.assertEqual(self.transport.call_args.kwargs['json'], original['json'])
        self.assertEqual(self.transport.call_args.kwargs['headers']['Idempotency-Key'], original['headers']['Idempotency-Key'])
        call_command('process_order_emails', stdout=StringIO())
        self.assertEqual(self.transport.call_count, 2)

    def test_http_error_and_missing_provider_id_are_not_success(self):
        for response in [Mock(status_code=503), Mock(status_code=200, json=lambda: {})]:
            self.transport.return_value = response
            with self.captureOnCommitCallbacks(execute=True):
                order = self.dispatch(self.order())
            email = order.emails.get()
            self.assertIsNone(email.enviado_at)
            self.assertTrue(email.error)

    def test_ambiguous_old_delivery_requires_explicit_resend(self):
        order = self.dispatch(self.order())
        email = order.emails.get()
        email.primer_intento_at = timezone.now() - timedelta(hours=24)
        email.save()
        send_order_email(email.pk)
        email.refresh_from_db()
        self.assertTrue(email.revision_manual)
        self.transport.assert_not_called()
        with self.assertRaises(ValidationError):
            request_order_email(order.pk, email.pk, order_revision(order), 'retry')
        with self.captureOnCommitCallbacks(execute=True):
            new = request_order_email(order.pk, email.pk, order_revision(order), 'resend')
        self.assertNotEqual(new.clave, email.clave)
        email.refresh_from_db()
        self.assertIsNotNone(email.retirado_at)
        self.assertEqual(self.transport.call_count, 1)

    def test_rollback_never_sends_or_leaves_notification(self):
        order = self.change(self.order(), 'confirmado')
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.change(order, 'en_envio', transportista='retiro')
                    raise ValueError('abort')
            except ValueError:
                pass
        order.refresh_from_db()
        self.assertEqual(order.estado, 'confirmado')
        self.assertFalse(order.emails.exists())
        self.transport.assert_not_called()

    def test_delivered_stamps_date_without_email_or_payment_changes(self):
        with self.captureOnCommitCallbacks(execute=True):
            order = self.dispatch(self.order())
        total = order.total
        with self.captureOnCommitCallbacks(execute=True):
            order = self.change(order, 'entregado')
            date = order.entregado_at
            order = self.change(order, 'entregado')
        self.assertIsNotNone(date)
        self.assertEqual(order.entregado_at, date)
        self.assertFalse(order.pagado)
        self.assertEqual(order.total, total)
        self.assertEqual(self.transport.call_count, 1)
        with self.assertRaises(ValidationError):
            self.change(order, 'confirmado')
        with self.assertRaises(ValidationError):
            self.change(order, 'cancelado')

    def test_cancel_reactivate_and_duplicate_item_stock(self):
        order = self.order()
        ItemOrden.objects.create(orden=order, producto=self.product, color=self.color, talle=self.size, cantidad=2, precio=100)
        order = self.change(order, 'cancelado')
        order = self.change(order, 'cancelado')
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 8)
        order = self.change(order, 'en_proceso')
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 5)
        self.change(order, 'cancelado')
        self.size.stock = 0
        self.size.save()
        with self.assertRaises(ValidationError):
            self.change(order, 'en_proceso')
        order.refresh_from_db()
        self.assertEqual(order.estado, 'cancelado')

    def test_mp_payment_cannot_be_manually_overwritten(self):
        order = self.order(metodo_pago='mercadopago')
        with self.assertRaises(ValidationError):
            self.change(order, 'confirmado', pagado=True)
        order = confirm_verified_payment(order.pk, '987', order.total)
        with self.assertRaises(ValidationError):
            self.change(order, 'confirmado', pagado=False)
        self.client.force_login(self.staff)
        response = self.client.get(reverse('panel:pedido_editar', args=[order.pk]))
        self.assertContains(response, 'Verificado por Mercado Pago')
        self.assertTrue(response.context['form'].fields['pagado'].disabled)

    def test_concurrent_dispatch_data_and_email_action_are_rejected(self):
        order = self.dispatch(self.order())
        stale = order_revision(order)
        order = self.change(order, 'en_envio', codigo_seguimiento='CP222222222AR')
        with self.assertRaisesMessage(ValidationError, 'cambió mientras lo editabas'):
            update_order(order.pk, {'revision': stale, 'estado': 'entregado', 'pagado': False})
        with self.assertRaises(ValidationError):
            request_order_email(order.pk, order.emails.get().pk, stale, 'resend')
        self.assertIsNone(order.entregado_at)

    def test_email_dynamic_values_are_escaped(self):
        order = self.order(nombre='<script>buyer</script>', telefono='<b>phone</b>')
        self.product.nombre = '<img src=x onerror=alert(1)>'
        self.product.save()
        order = self.dispatch(order)
        for payload in [payload_despacho(order), payload_comprobante_cliente(order)]:
            self.assertNotIn('<script>', payload['html'])
            self.assertNotIn('<img src=x', payload['html'])
            self.assertIn('&lt;script&gt;', payload['html'])
            self.assertIn('&lt;img', payload['html'])

    def test_panel_email_permissions_and_explicit_confirmation(self):
        order = self.dispatch(self.order())
        email = order.emails.get()
        url = reverse('panel:pedido_email', args=[order.pk])
        data = {'revision': order_revision(order), 'email_id': email.pk, 'action': 'resend'}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        readonly = get_user_model().objects.create_user('readonly', is_staff=True)
        readonly.user_permissions.add(Permission.objects.get(codename='view_orden'))
        self.client.force_login(readonly)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, data)
        self.assertEqual(order.emails.count(), 1)
        other = self.dispatch(self.order())
        data.update(confirmar='on', email_id=other.emails.get().pk)
        self.client.post(url, data)
        self.assertEqual(order.emails.count(), 1)
        data['email_id'] = email.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, data)
        self.assertEqual(order.emails.count(), 2)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.staff)
        self.assertEqual(secure.post(url, data).status_code, 403)

    def test_django_admin_uses_shared_rules_and_concurrency(self):
        order = self.order()
        self.client.force_login(self.staff)
        url = reverse('admin:tienda_orden_change', args=[order.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['adminform'].form
        data = {'estado': 'confirmado', 'confirmar': 'on', 'revision': form['revision'].value(),
                'itemorden_set-TOTAL_FORMS': '1', 'itemorden_set-INITIAL_FORMS': '1',
                'itemorden_set-MIN_NUM_FORMS': '0', 'itemorden_set-MAX_NUM_FORMS': '0',
                'itemorden_set-0-id': order.itemorden_set.get().pk, 'itemorden_set-0-orden': order.pk}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.estado, 'confirmado')
        self.assertFalse(order.pagado)
        self.assertContains(self.client.post(url, data), 'cambió mientras lo editabas')
        data.update(estado='en_envio', revision=order_revision(order))
        self.assertContains(self.client.post(url, data), 'Seleccioná el transportista')
        data.update(transportista='correo_argentino', codigo_seguimiento='CP123456789AR', plazo_dias_habiles='7')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.emails.filter(tipo='despacho').count(), 1)
        self.assertEqual(self.transport.call_count, 1)

    def test_tracking_private_link_never_exposes_buyer_fields(self):
        order = self.dispatch(self.order())
        url = reverse('seguir_pedido')
        response = self.client.post(url, {'numero': order.pk, 'email': order.email})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]), follow=True)
        self.assertContains(response, order.codigo_seguimiento)
        self.assertContains(response, '7 días hábiles')
        for private in [order.direccion, order.telefono, order.email, str(order.seguimiento_token)]:
            self.assertNotContains(response, private)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.assertIn('noindex', response['X-Robots-Tag'])
        other = self.order()
        response = self.client.get(url, {'pedido': other.pk})
        self.assertEqual(response.context['order']['numero'], order.pk)

    def test_private_token_and_expired_session(self):
        order = self.order()
        bad = reverse('seguir_pedido_token', args=[uuid.uuid4()])
        self.assertEqual(self.client.get(bad).status_code, 400)
        response = self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]), follow=True)
        self.assertContains(response, f'Pedido #{order.pk}')
        self.assertContains(response, 'En proceso')
        self.assertEqual(response.redirect_chain[0][0], reverse('seguir_pedido'))
        session = self.client.session
        session['tracking_access']['expires'] = 0
        session.save()
        self.assertIsNone(self.client.get(reverse('seguir_pedido')).context['order'])
        self.assertIsNone(Client().get(reverse('seguir_pedido'), {'numero': order.pk}).context['order'])

    def test_tracking_updates_from_database_and_handles_cancelled_pickup(self):
        order = self.dispatch(self.order())
        self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]))
        self.change(order, 'entregado')
        response = self.client.get(reverse('seguir_pedido'))
        self.assertContains(response, 'ya fue entregado')
        order = self.change(self.order(), 'cancelado')
        self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]))
        self.assertContains(self.client.get(reverse('seguir_pedido')), 'está cancelado')
        order = self.change(self.order(), 'confirmado')
        order = self.change(order, 'en_envio', transportista='retiro')
        self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]))
        response = self.client.get(reverse('seguir_pedido'))
        self.assertContains(response, 'listo para retirar')
        self.assertNotContains(response, 'correoargentino.com.ar')

    def test_tracking_rate_limit_and_csrf(self):
        url = reverse('seguir_pedido')
        for index in range(30):
            self.client.post(url, {'numero': index + 1, 'email': f'visitor{index}@example.test'})
        self.assertEqual(self.client.post(url, {'numero': 1, 'email': 'x@example.test'}).status_code, 429)
        self.assertEqual(self.client.get(reverse('seguir_pedido_token', args=[uuid.uuid4()])).status_code, 429)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, {'numero': 1, 'email': 'x@example.test'}).status_code, 403)

    def test_old_numeric_urls_cannot_bypass_private_access(self):
        order = self.order(metodo_pago='mercadopago')
        for name in ['confirmacion', 'confirmacion_transferencia', 'pago_mp', 'mercadopago_retorno']:
            for pk in [order.pk, 98765]:
                response = self.client.get(reverse(name, args=[pk]))
                self.assertRedirects(response, reverse('seguir_pedido'))
                self.assertNotContains(self.client.get(response.url), order.direccion)


class OrderMigrationTests(TransactionTestCase):
    def test_historical_orders_get_unique_tokens_and_keep_payment_and_items(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('tienda', '0018_newslettercontacto')])
        old = executor.loader.project_state([('tienda', '0018_newslettercontacto')]).apps
        OldOrder = old.get_model('tienda', 'Orden')
        product = old.get_model('tienda', 'Producto').objects.create(nombre='Histórico', precio=100)
        ids = []
        for state, paid, method in [('finalizado', True, 'transferencia'), ('finalizado', False, 'efectivo'),
                                    ('en_proceso', False, 'mercadopago'), ('cancelado', False, 'efectivo')]:
            order = OldOrder.objects.create(nombre='Histórico', email='old@example.test', telefono='1', direccion='x',
                                            total=100, estado=state, pagado=paid, metodo_pago=method)
            old.get_model('tienda', 'ItemOrden').objects.create(orden=order, producto=product, cantidad=1, precio=100)
            ids.append(order.pk)
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([('tienda', '0021_order_tracking_access_email')])
            orders = list(Orden.objects.filter(pk__in=ids).order_by('pk'))
            self.assertEqual([o.estado for o in orders], ['entregado', 'entregado', 'en_proceso', 'cancelado'])
            self.assertEqual([o.pagado for o in orders], [True, False, False, False])
            self.assertEqual(len({o.seguimiento_token for o in orders}), 4)
            self.assertTrue(all(o.dni_hash == '' for o in orders))
            self.assertTrue(all(o.itemorden_set.count() == 1 for o in orders))
            self.assertTrue(all(o.despachado_at is None and o.entregado_at is None for o in orders))
            self.assertEqual(orders[0].pago_origen, 'historico')
            self.assertTrue(orders[0].finalizado_historico)
            self.assertFalse(orders[2].emails_iniciales_preexistentes)
            self.assertTrue(orders[1].emails_iniciales_preexistentes)
            self.assertFalse(EmailOrden.objects.exists())
            response = self.client.get(reverse('seguir_pedido_token', args=[orders[0].seguimiento_token]), follow=True)
            self.assertContains(response, f'Pedido #{orders[0].pk}')
        finally:
            MigrationExecutor(connection).migrate([('tienda', '0021_order_tracking_access_email')])
