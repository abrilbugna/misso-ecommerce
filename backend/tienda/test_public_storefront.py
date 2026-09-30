"""Public product-only storefront; all fixtures live in Django's test database."""
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (CATEGORIAS, CATEGORIA_ROPA_DEPORTIVA, Carrito, ItemCarrito,
                     Producto, Orden, Suscripcion, EmailSuscripcion)
from .subscription_api import MPSubscriptionError, SubscriptionAPI
from .subscription_services import create_intention, start_checkout
from .subscription_emails import queue_welcome, send_welcome, due_emails


@override_settings(SUBSCRIPTIONS_PUBLIC_ENABLED=False, MP_SUBSCRIPTION_ENABLED=True,
                   ALLOWED_HOSTS=['testserver'])
class PublicStorefrontTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # More than four items also exercises the former catalog promo slot.
        cls.products = [Producto.objects.create(nombre=f'Producto {i}', precio=100,
                        categoria='bralettes') for i in range(5)]
        cls.order = Orden.objects.create(nombre='Cliente', email='cliente@example.test',
                                        telefono='123', direccion='Prueba', total=100)
        cls.sub = Suscripcion.objects.create(submission_key=uuid.uuid4(), nombre='Histórica',
                    email='cliente@example.test', telefono='123', destino='mismo', talle='90',
                    importe=Decimal('25000'), moneda='ARS')

    def assert_product_only(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertNotRegex(response.content.decode().lower(),
                            r'suscrip|suscrib|preapproval|preferencias|25\.000|25k')

    def test_home_preserves_hero_and_videos_with_sports_cta(self):
        response = self.client.get(reverse('inicio'))
        self.assert_product_only(response)
        for content in ('NUEVA', 'COLECCIÓN', 'VER PRODUCTOS', 'Deslizá para más',
                        'img/letram.svg', 'collection-product', 'intro-carousel',
                        'Nueva línea en camino...', 'Preparamos<br><em>algo nuevo.</em>',
                        'Muy pronto llega una nueva colección de ropa deportiva a Misso.',
                        'Ver ropa deportiva'):
            self.assertContains(response, content)
        self.assertContains(response, '<video ', count=3)
        self.assertContains(response, f'href="{reverse("catalogo")}?categoria={CATEGORIA_ROPA_DEPORTIVA}"')

    def test_public_pages_and_shared_footer_have_no_subscription_references(self):
        session = self.client.session
        session.save()
        cart = Carrito.objects.create(session_key=session.session_key)
        ItemCarrito.objects.create(carrito=cart, producto=self.products[0], cantidad=1)
        urls = [reverse('catalogo'), reverse('detalle', args=[self.products[0].pk]),
                reverse('ver_carrito'), reverse('checkout'),
                reverse('confirmacion', args=[self.order.pk]),
                reverse('confirmacion_transferencia', args=[self.order.pk])]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_product_only(response)
                self.assertContains(response, 'mailto:missocba@gmail.com')
                self.assertContains(response, 'Seguir pedido')

    def test_all_public_subscription_routes_redirect_without_disclosing_history(self):
        for reference in (self.sub.referencia_publica, uuid.uuid4()):
            urls = [reverse('informacion_suscripcion'), reverse('comenzar_suscripcion'),
                    reverse('suscripcion_resultado', args=[reference]),
                    reverse('suscripcion_estado', args=[reference])]
            for url in urls:
                for method in ('get', 'post'):
                    with self.subTest(url=url, method=method):
                        response = getattr(self.client, method)(url)
                        self.assertRedirects(response, reverse('catalogo'))
                        self.assertIn('no-store', response['Cache-Control'])

    def test_saved_valid_form_cannot_start_checkout_after_pause(self):
        with override_settings(SUBSCRIPTIONS_PUBLIC_ENABLED=True):
            page = self.client.get(reverse('comenzar_suscripcion'))
            token = page.context['form']['submission_token'].value()
        with patch('tienda.subscription_views.create_intention') as create, \
             patch('tienda.subscription_views.start_checkout') as start:
            response = self.client.post(reverse('comenzar_suscripcion'), {
                'nombre': 'Cliente', 'email': 'cliente@example.test', 'telefono': '123',
                'destino': 'mismo', 'talle': '90', 'tipo_prenda': 'conjuntos',
                'estilo': 'detalles', 'terminos_aceptados': 'on', 'submission_token': token})
        self.assertRedirects(response, reverse('catalogo'))
        create.assert_not_called()
        start.assert_not_called()
        self.assertEqual(Suscripcion.objects.count(), 1)
        self.assertFalse(EmailSuscripcion.objects.exists())

    def test_creation_services_and_remote_preapproval_are_blocked(self):
        with patch('tienda.subscription_api.requests.request') as transport:
            for operation in (lambda: create_intention(None, uuid.uuid4()),
                              lambda: start_checkout(self.sub),
                              lambda: SubscriptionAPI().create_pending(self.sub)):
                with self.assertRaises(MPSubscriptionError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, 'subscriptions_public_disabled')
        transport.assert_not_called()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.checkout_estado, 'new')

    def test_welcome_queue_and_pending_delivery_pause_without_deleting_history(self):
        email = EmailSuscripcion.objects.create(suscripcion=self.sub, tipo='cliente',
                                               payload={'to': ['cliente@example.test']})
        with patch('tienda.subscription_emails.requests.post') as send:
            queue_welcome(self.sub)
            send_welcome(email.pk)
        send.assert_not_called()
        self.assertFalse(due_emails().exists())
        email.refresh_from_db()
        self.assertEqual(EmailSuscripcion.objects.count(), 1)
        self.assertIsNone(email.primer_intento_at)
        self.assertIsNone(email.enviado_at)
        self.assertEqual(email.intentos, 0)

    def test_sports_filter_empty_then_populated_without_changing_existing_categories(self):
        self.assertEqual(CATEGORIAS[:-1], [('conjuntos armados', 'Conjuntos armados'),
            ('bralettes', 'Bralettes'), ('bombachas', 'Bombachas'), ('babydoll', 'Babydolls'), ('otros', 'Otros')])
        url = reverse('catalogo') + '?categoria=' + CATEGORIA_ROPA_DEPORTIVA
        response = self.client.get(url)
        self.assert_product_only(response)
        self.assertContains(response, 'Ropa deportiva')
        self.assertContains(response, 'No hay productos en esta categoría todavía.')
        self.assertQuerySetEqual(response.context['productos'], [])
        product = Producto.objects.create(nombre='Deportiva de prueba', precio=100,
                                           categoria=CATEGORIA_ROPA_DEPORTIVA)
        product.full_clean()
        Producto.objects.create(nombre='Oculta', precio=100, activo=False,
                                categoria=CATEGORIA_ROPA_DEPORTIVA)
        response = self.client.get(url)
        self.assertQuerySetEqual(response.context['productos'], [product])
        self.assertEqual(response.context['categoria_activa'], CATEGORIA_ROPA_DEPORTIVA)
        self.assertEqual(Producto.objects.filter(categoria='bralettes').count(), 5)

    def test_private_panel_still_serves_subscription_history(self):
        urls = [reverse('panel:suscripciones'),
                reverse('panel:suscripcion_detalle', args=[self.sub.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        staff = get_user_model().objects.create_superuser('staff', 'staff@example.test', 'test')
        self.client.force_login(staff)
        for url in urls:
            self.assertContains(self.client.get(url), 'Histórica')

    @override_settings(SUBSCRIPTIONS_PUBLIC_ENABLED=True)
    def test_flag_can_restore_retained_public_templates(self):
        for name, args in [('informacion_suscripcion', []), ('comenzar_suscripcion', []),
                           ('suscripcion_resultado', [self.sub.referencia_publica]),
                           ('suscripcion_estado', [self.sub.referencia_publica])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
