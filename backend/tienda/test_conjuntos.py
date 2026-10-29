"""Shared inventory and historical set purchases on an isolated test database."""
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError, close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from .email_utils import html_comprobante_cliente
from .inventory import adjust_locked
from .models import (Carrito, ColorProducto, ImagenProducto, ItemCarrito, ItemOrden,
                     OpcionEnvio, Orden, Producto, TalleProducto, CodigoPromocional)
from .order_services import order_revision, update_order
from .panel_forms import ProductoForm
from .panel_services import revision_for


@override_settings(ALLOWED_HOSTS=['testserver'])
class ConjuntosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.top = Producto.objects.create(nombre='Top deportivo', precio=20000)
        cls.short = Producto.objects.create(nombre='Short deportivo', precio=18000)
        cls.top_color = ColorProducto.objects.create(producto=cls.top, nombre='Rosa')
        cls.short_color = ColorProducto.objects.create(producto=cls.short, nombre='Rosa')
        cls.top_m = TalleProducto.objects.create(color=cls.top_color, talle='M', stock=10)
        cls.short_s = TalleProducto.objects.create(color=cls.short_color, talle='S', stock=5)
        cls.short_m = TalleProducto.objects.create(color=cls.short_color, talle='M', stock=8)
        cls.set = Producto.objects.create(nombre='Conjunto Deportivo Rosa', precio=34000,
                                          tipo='conjunto', parte_superior=cls.top, parte_inferior=cls.short)
        cls.shipping = OpcionEnvio.objects.create(nombre='Retiro', costo=0)

    def cart(self):
        session = self.client.session
        session.save()
        return Carrito.objects.create(session_key=session.session_key)

    def checkout(self):
        return self.client.post(reverse('checkout'), {
            'nombre': 'Compradora', 'dni': '12345678', 'email': 'buyer@example.test',
            'telefono': '3519876543', 'direccion': 'Córdoba', 'envio': self.shipping.pk,
            'metodo_pago': 'efectivo',
        })

    def test_set_has_own_price_images_and_valid_components(self):
        form = ProductoForm({'tipo': 'conjunto', 'nombre': 'Otro conjunto', 'precio': '34000',
                            'categoria': 'otros', 'parte_superior': self.top.pk,
                            'parte_inferior': self.short.pk, 'activo': 'on'})
        self.assertTrue(form.is_valid(), form.errors)
        image = ImagenProducto.objects.create(producto=self.set, imagen='misso/conjunto.png')
        self.assertEqual(self.set.imagen_principal(), image)
        self.assertEqual(self.set.precio, Decimal('34000'))
        invalid = ProductoForm({'tipo': 'conjunto', 'nombre': 'Circular', 'precio': '1',
                                'categoria': 'otros', 'parte_superior': self.set.pk,
                                'parte_inferior': self.short.pk})
        self.assertFalse(invalid.is_valid())

    @patch('tienda.panel_services.cloudinary.uploader.upload')
    def test_panel_creates_set_with_its_own_image(self, upload):
        upload.return_value = {'public_id': 'sets/rosa', 'format': 'png', 'version': 1}
        self.client.force_login(get_user_model().objects.create_superuser('set-admin', 'set@example.test', 'secret'))
        file = BytesIO()
        Image.new('RGB', (8, 8), 'pink').save(file, 'PNG')
        payload = {
            'producto-tipo': 'conjunto', 'producto-nombre': 'Conjunto nuevo',
            'producto-precio': '34000', 'producto-categoria': 'otros',
            'producto-parte_superior': self.top.pk, 'producto-parte_inferior': self.short.pk,
            'producto-activo': 'on', 'revision': revision_for(Producto()),
            'colors-TOTAL_FORMS': '0', 'colors-INITIAL_FORMS': '0',
            'images-TOTAL_FORMS': '1', 'images-INITIAL_FORMS': '0',
            'images-0-orden': '0',
            'images-0-imagen': SimpleUploadedFile('set.png', file.getvalue(), content_type='image/png'),
            'videos-TOTAL_FORMS': '0', 'videos-INITIAL_FORMS': '0',
        }
        response = self.client.post(reverse('panel:producto_nuevo'), payload)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        created = Producto.objects.get(nombre='Conjunto nuevo')
        self.assertEqual((created.parte_superior, created.parte_inferior, created.precio),
                         (self.top, self.short, Decimal('34000')))
        self.assertEqual(created.colores.count(), 0)
        self.assertEqual(created.imagenes.count(), 1)
        upload.assert_called_once()

    def test_individual_and_set_share_stock_and_keep_history(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.short, color=self.short_color,
                                   talle=self.short_s, cantidad=1)
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=2)
        response = self.checkout()
        order = Orden.objects.get()
        self.assertRedirects(response, reverse('confirmacion', args=[order.pk]))
        self.top_m.refresh_from_db(); self.short_s.refresh_from_db(); self.short_m.refresh_from_db()
        self.assertEqual((self.top_m.stock, self.short_s.stock, self.short_m.stock), (8, 2, 8))
        self.assertEqual(order.subtotal, Decimal('86000'))
        set_item = order.itemorden_set.get(producto=self.set)
        self.assertEqual((set_item.cantidad, set_item.precio, set_item.talle_inferior_id),
                         (2, Decimal('34000'), self.short_s.pk))
        self.set.nombre = 'Nombre nuevo'; self.set.save(update_fields=['nombre'])
        self.assertIn('Conjunto Deportivo Rosa', html_comprobante_cliente(order, [set_item]))
        self.assertIn('Top deportivo — Rosa — M', set_item.detalle_superior)
        self.assertIn('Short deportivo — Rosa — S', set_item.detalle_inferior)

    def test_cart_separates_sizes_and_rejects_shared_shortage(self):
        cart = self.cart()
        url = reverse('agregar_carrito', args=[self.set.pk])
        self.client.get(url, {'color': self.top_color.pk, 'talle': self.top_m.pk,
                              'talle_inferior': self.short_s.pk, 'cantidad': 2})
        self.client.get(url, {'color': self.top_color.pk, 'talle': self.top_m.pk,
                              'talle_inferior': self.short_m.pk, 'cantidad': 1})
        self.assertEqual(ItemCarrito.objects.filter(carrito=cart).count(), 2)
        self.assertContains(self.client.get(reverse('ver_carrito')), 'Short deportivo · talle S')
        self.client.get(reverse('agregar_carrito', args=[self.short.pk]),
                        {'color': self.short_color.pk, 'talle': self.short_s.pk, 'cantidad': 4})
        self.assertFalse(ItemCarrito.objects.filter(carrito=cart, producto=self.short).exists())
        self.assertContains(self.client.get(reverse('checkout')), 'Short deportivo · S')

    def test_buying_only_short_reduces_shared_inventory(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.short, color=self.short_color,
                                   talle=self.short_s, cantidad=1)
        self.checkout()
        self.short_s.refresh_from_db(); self.top_m.refresh_from_db()
        self.assertEqual((self.short_s.stock, self.top_m.stock), (4, 10))
        sizes = self.client.get(reverse('talles_conjunto', args=[self.set.pk, self.top_color.pk])).json()
        self.assertEqual(next(size['stock'] for size in sizes['inferior'] if size['talle'] == 'S'), 4)

    def test_checkout_rejects_aggregate_shortage_without_order(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.short, color=self.short_color,
                                   talle=self.short_s, cantidad=4)
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=2)
        self.assertContains(self.checkout(), 'No hay stock suficiente')
        self.assertFalse(Orden.objects.exists())
        self.short_s.refresh_from_db()
        self.assertEqual(self.short_s.stock, 5)

    def test_checkout_rejects_exhausted_top_as_well(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=1)
        self.top_m.stock = 0
        self.top_m.save(update_fields=['stock'])
        self.assertContains(self.checkout(), 'No hay stock suficiente')
        self.assertFalse(Orden.objects.exists())

    def test_cancel_and_reactivate_each_component_once(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=2)
        self.checkout()
        order = Orden.objects.get()
        update_order(order.pk, {'revision': order_revision(order), 'estado': 'cancelado'})
        self.top_m.refresh_from_db(); self.short_s.refresh_from_db()
        self.assertEqual((self.top_m.stock, self.short_s.stock), (10, 5))
        order.refresh_from_db()
        adjust_locked({self.short_s.pk: 5}, -1)
        with self.assertRaises(ValidationError):
            update_order(order.pk, {'revision': order_revision(order), 'estado': 'en_proceso'})
        order.refresh_from_db()
        self.assertEqual(order.estado, 'cancelado')
        adjust_locked({self.short_s.pk: 5}, 1)
        update_order(order.pk, {'revision': order_revision(order), 'estado': 'en_proceso'})
        self.top_m.refresh_from_db(); self.short_s.refresh_from_db()
        self.assertEqual((self.top_m.stock, self.short_s.stock), (8, 3))

    def test_invalid_cross_product_variant_rejected(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.short_s, talle_inferior=self.top_m, cantidad=1)
        self.assertContains(self.checkout(), 'combinación de prendas')
        self.assertFalse(ItemOrden.objects.exists())

    def test_set_uses_own_price_for_coupon_shipping_and_mp_surcharge(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=1)
        self.shipping.costo = Decimal('1000')
        self.shipping.save(update_fields=['costo'])
        code = CodigoPromocional.objects.create(codigo='SET10', descuento_porcentaje=10)
        session = self.client.session
        session['codigo_promo'] = code.codigo
        session.save()
        response = self.client.post(reverse('checkout'), {
            'nombre': 'Compradora', 'dni': '12345678', 'email': 'buyer@example.test',
            'telefono': '3519876543', 'direccion': 'Córdoba', 'envio': self.shipping.pk,
            'metodo_pago': 'mercadopago',
        })
        order = Orden.objects.get()
        self.assertRedirects(response, reverse('pago_mp', args=[order.pk]), fetch_redirect_response=False)
        self.assertEqual((order.subtotal, order.descuento, order.total),
                         (Decimal('34000'), Decimal('3400'), Decimal('34760')))
        self.assertEqual(order.itemorden_set.get().precio, Decimal('34000'))

    def test_panel_and_private_tracking_show_set_components(self):
        cart = self.cart()
        ItemCarrito.objects.create(carrito=cart, producto=self.set, color=self.top_color,
                                   talle=self.top_m, talle_inferior=self.short_s, cantidad=1)
        self.checkout()
        order = Orden.objects.get()
        self.client.force_login(get_user_model().objects.create_superuser('order-admin', 'order@example.test', 'secret'))
        self.assertContains(self.client.get(reverse('panel:pedido_editar', args=[order.pk])),
                            'Short deportivo — Rosa — S')
        self.client.logout()
        self.client.get(reverse('seguir_pedido_token', args=[order.seguimiento_token]))
        self.assertContains(self.client.get(reverse('seguir_pedido')), 'Top deportivo — Rosa — M')


@override_settings(ALLOWED_HOSTS=['testserver'])
class ConcurrentSetCheckoutTests(TransactionTestCase):
    @patch('tienda.views.queue_initial')
    def test_same_last_variant_cannot_be_sold_twice(self, queue_initial):
        top = Producto.objects.create(nombre='Top', precio=100)
        bottom = Producto.objects.create(nombre='Short', precio=100)
        top_color = ColorProducto.objects.create(producto=top, nombre='Rosa')
        bottom_color = ColorProducto.objects.create(producto=bottom, nombre='Rosa')
        top_size = TalleProducto.objects.create(color=top_color, talle='M', stock=1)
        bottom_size = TalleProducto.objects.create(color=bottom_color, talle='S', stock=1)
        conjunto = Producto.objects.create(nombre='Conjunto', precio=180, tipo='conjunto',
                                           parte_superior=top, parte_inferior=bottom)
        shipping = OpcionEnvio.objects.create(nombre='Retiro', costo=0)
        clients = [Client(), Client()]
        for client in clients:
            session = client.session
            session.save()
            cart = Carrito.objects.create(session_key=session.session_key)
            ItemCarrito.objects.create(carrito=cart, producto=conjunto, color=top_color,
                                       talle=top_size, talle_inferior=bottom_size, cantidad=1)
        barrier = Barrier(2)

        def buy(client):
            close_old_connections()
            barrier.wait()
            try:
                return client.post(reverse('checkout'), {
                    'nombre': 'Compradora', 'dni': '12345678', 'email': 'buyer@example.test',
                    'telefono': '3519876543', 'direccion': 'Córdoba', 'envio': shipping.pk,
                    'metodo_pago': 'efectivo',
                }).status_code
            except OperationalError:
                # SQLite has database-level write locks; PostgreSQL blocks the row.
                return 409
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(buy, clients))
        top_size.refresh_from_db(); bottom_size.refresh_from_db()
        self.assertEqual(top_size.stock, bottom_size.stock)
        self.assertEqual(top_size.stock + Orden.objects.count(), 1)
        self.assertLessEqual(Orden.objects.count(), 1)
        self.assertTrue(all(status in (200, 302, 409) for status in statuses))
        if connection.vendor == 'postgresql':
            self.assertEqual(sorted(statuses), [200, 302])
            self.assertEqual(Orden.objects.count(), 1)
            self.assertEqual(top_size.stock, 0)
