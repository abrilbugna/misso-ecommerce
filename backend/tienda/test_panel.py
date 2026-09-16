"""Integration checks run against Django's isolated test database, never live data."""
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse, resolve

from .models import (Producto, ColorProducto, TalleProducto, ImagenProducto, VideoProducto,
                     Orden, ItemOrden, OpcionEnvio, CodigoPromocional)
from .panel_services import revision_for, order_revision


def management(prefix, total=0, initial=0):
    return {f'{prefix}-TOTAL_FORMS': str(total), f'{prefix}-INITIAL_FORMS': str(initial),
            f'{prefix}-MIN_NUM_FORMS': '0', f'{prefix}-MAX_NUM_FORMS': '50'}


def image_file():
    file = BytesIO()
    Image.new('RGB', (8, 8), 'pink').save(file, 'PNG')
    return SimpleUploadedFile('photo.png', file.getvalue(), content_type='image/png')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser('staff', 'staff@example.test', 'panel-test-password')
        cls.regular = get_user_model().objects.create_user('regular', password='panel-test-password')
        cls.product = Producto.objects.create(nombre='Producto de prueba', precio='100', activo=True)
        cls.color = ColorProducto.objects.create(producto=cls.product, nombre='Negro')
        cls.size = TalleProducto.objects.create(color=cls.color, talle='85', stock=2)
        cls.shipping = OpcionEnvio.objects.create(nombre='Retiro', costo=0)
        cls.order = Orden.objects.create(nombre='Cliente de prueba', email='customer@example.test', telefono='123', direccion='Prueba', subtotal=100, total=100, envio=cls.shipping)
        cls.item = ItemOrden.objects.create(orden=cls.order, producto=cls.product, color=cls.color, talle=cls.size, cantidad=1, precio=100)

    def setUp(self):
        self.client.force_login(self.staff)

    def payload(self, product=None):
        product = product or Producto()
        data = {'producto-nombre': 'Producto actualizado', 'producto-precio': '150', 'producto-categoria': 'otros', 'producto-activo': 'on', 'revision': revision_for(product)}
        for name in ['colors', 'images', 'videos']:
            data.update(management(name))
        if product.pk:
            colors = list(product.colores.order_by('pk'))
            data.update(management('colors', len(colors), len(colors)))
            for index, color in enumerate(colors):
                prefix = f'colors-{index}'
                data.update({f'{prefix}-id': str(color.pk), f'{prefix}-nombre': color.nombre})
                sizes = list(color.talles.order_by('pk'))
                data.update(management(f'{prefix}-sizes', len(sizes), len(sizes)))
                for j, size in enumerate(sizes):
                    data.update({f'{prefix}-sizes-{j}-id': str(size.pk), f'{prefix}-sizes-{j}-talle': size.talle, f'{prefix}-sizes-{j}-stock': str(size.stock)})
        return data

    def test_access_login_logout_and_admin(self):
        urls = ['/panel/', '/panel/productos/', '/panel/productos/nuevo/', '/panel/productos/1/', '/panel/pedidos/', '/panel/pedidos/1/', '/panel/promociones/', '/panel/promociones/nuevo/', '/panel/promociones/1/', '/panel/envios/', '/panel/envios/nuevo/', '/panel/envios/1/']
        anon = Client()
        for url in urls:
            self.assertEqual(anon.get(url).status_code, 302, url)
            self.assertTrue(anon.get(url).url.startswith('/panel/login/?next='))
        anon.force_login(self.regular)
        for url in urls:
            self.assertEqual(anon.get(url).status_code, 403, url)
        self.assertEqual(anon.get('/panel/login/').status_code, 403)
        self.assertEqual(resolve('/admin/').namespace, 'admin')
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(self.client.get('/panel/logout/').status_code, 405)
        self.assertRedirects(self.client.post('/panel/logout/'), '/panel/login/')
        response = self.client.post('/panel/login/', {'username': 'staff@example.test', 'password': 'panel-test-password', 'next': 'https://evil.example'})
        self.assertEqual(response.url, '/panel/')

    def test_csrf_and_model_permissions(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.staff)
        self.assertEqual(secure.post('/panel/logout/').status_code, 403)
        self.assertEqual(secure.post('/panel/productos/nuevo/', self.payload()).status_code, 403)
        restricted = get_user_model().objects.create_user('restricted', is_staff=True)
        restricted.user_permissions.add(Permission.objects.get(codename='view_producto'))
        self.client.force_login(restricted)
        self.assertEqual(self.client.get('/panel/').status_code, 200)
        self.assertEqual(self.client.get('/panel/productos/').status_code, 200)
        self.assertEqual(self.client.post('/panel/productos/nuevo/', self.payload()).status_code, 403)
        self.assertEqual(self.client.get('/panel/pedidos/').status_code, 403)

    def test_all_pages_render(self):
        promo = CodigoPromocional.objects.create(codigo='TEST', descuento_fijo=10)
        urls = ['/panel/', '/panel/productos/', '/panel/productos/nuevo/', f'/panel/productos/{self.product.pk}/', '/panel/pedidos/', f'/panel/pedidos/{self.order.pk}/', '/panel/promociones/', '/panel/promociones/nuevo/', f'/panel/promociones/{promo.pk}/', '/panel/envios/', '/panel/envios/nuevo/', f'/panel/envios/{self.shipping.pk}/']
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertNotContains(response, 'form.as_p')
        self.assertEqual(Client().get('/panel/login/').status_code, 200)

    def test_real_metrics_exclude_cancelled_sales(self):
        Orden.objects.filter(pk=self.order.pk).update(pagado=True)
        Orden.objects.create(nombre='Cancelado', email='cancel@example.test', telefono='1', direccion='x', total=999, estado='cancelado', pagado=True)
        response = self.client.get('/panel/')
        self.assertEqual(response.context['sales'], Decimal('100'))
        self.assertEqual(response.context['stock']['low'], 1)
        self.assertEqual(response.context['products']['total'], 1)

    def test_create_nested_product(self):
        data = self.payload()
        data.update(management('colors', 1))
        data['colors-0-nombre'] = 'Rosa'
        data.update(management('colors-0-sizes', 2))
        data.update({'colors-0-sizes-0-talle': '85', 'colors-0-sizes-0-stock': '5', 'colors-0-sizes-1-talle': '90', 'colors-0-sizes-1-stock': '0'})
        response = self.client.post('/panel/productos/nuevo/', data)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        created = Producto.objects.get(nombre='Producto actualizado')
        self.assertEqual(list(created.colores.get().talles.order_by('talle').values_list('stock', flat=True)), [5, 0])

    def test_edit_add_color_and_talle_together(self):
        data = self.payload(self.product)
        data['colors-0-sizes-0-stock'] = '7'
        data.update(management('colors', 2, 1))
        data['colors-1-nombre'] = 'Rosa'
        data.update(management('colors-1-sizes', 1))
        data.update({'colors-1-sizes-0-talle': '95', 'colors-1-sizes-0-stock': '4'})
        response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
        self.assertEqual(response.status_code, 302)
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 7)
        self.assertEqual(self.product.colores.get(nombre='Rosa').talles.get().stock, 4)

    def test_negative_and_duplicate_sizes_do_not_partially_save(self):
        for duplicate in [False, True]:
            data = self.payload(self.product)
            if duplicate:
                data.update(management('colors-0-sizes', 2, 1))
                data.update({'colors-0-sizes-1-talle': '85', 'colors-0-sizes-1-stock': '1'})
            else:
                data['colors-0-sizes-0-stock'] = '-1'
            response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'No guardamos')
            self.product.refresh_from_db()
            self.assertEqual(self.product.precio, Decimal('100'))

    def test_foreign_ids_and_management_tampering_rejected(self):
        other = Producto.objects.create(nombre='Otro', precio=100)
        color = ColorProducto.objects.create(producto=other, nombre='Ajeno')
        for changes in [{'colors-0-id': str(color.pk)}, {'colors-INITIAL_FORMS': '0'}, {'colors-TOTAL_FORMS': '0', 'colors-INITIAL_FORMS': '0'}, {'colors-0-sizes-TOTAL_FORMS': '0', 'colors-0-sizes-INITIAL_FORMS': '0'}]:
            data = self.payload(self.product)
            data.update(changes)
            response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
            self.assertEqual(response.status_code, 200)
            self.product.refresh_from_db()
            self.assertEqual(self.product.precio, Decimal('100'))

    def test_stale_inventory_rejected(self):
        data = self.payload(self.product)
        TalleProducto.objects.filter(pk=self.size.pk).update(stock=1)
        response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
        self.assertContains(response, 'cambió mientras editabas')
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 1)

    def test_historical_names_and_deletion_protected(self):
        data = self.payload(self.product)
        data['colors-0-nombre'] = 'Cambio peligroso'
        self.assertContains(self.client.post(f'/panel/productos/{self.product.pk}/', data), 'Conservá su nombre histórico')
        response = self.client.get(f'/panel/productos/{self.product.pk}/')
        self.assertNotContains(response, 'name="colors-0-DELETE"')
        self.assertNotContains(response, 'Eliminar producto')
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/eliminar/').status_code, 404)

    @patch('tienda.panel_services.cloudinary.uploader.upload')
    def test_upload_image_and_video_with_new_color(self, upload):
        upload.return_value = {'public_id': 'panel/test', 'format': 'png', 'version': 1}
        data = self.payload()
        data.update(management('colors', 1))
        data['colors-0-nombre'] = 'Rosa'
        data.update(management('colors-0-sizes', 1))
        data.update({'colors-0-sizes-0-talle': '85', 'colors-0-sizes-0-stock': '2'})
        data.update(management('images', 1))
        data.update({'images-0-imagen': image_file(), 'images-0-color_ref': 'colors-0', 'images-0-orden': '0'})
        data.update(management('videos', 1))
        data.update({'videos-0-video': SimpleUploadedFile('video.mp4', b'test-video', content_type='video/mp4'), 'videos-0-orden': '1'})
        response = self.client.post('/panel/productos/nuevo/', data)
        self.assertEqual(response.status_code, 302)
        product = Producto.objects.get(nombre='Producto actualizado')
        self.assertEqual(product.imagenes.get().color_id, product.colores.get().pk)
        self.assertEqual(product.videos.count(), 1)
        self.assertEqual(upload.call_count, 2)

    @patch('tienda.panel_services.cloudinary.uploader.upload')
    def test_invalid_media_color_never_uploads(self, upload):
        data = self.payload(self.product)
        data.update(management('images', 1))
        data.update({'images-0-imagen': image_file(), 'images-0-color_ref': 'colors-99', 'images-0-orden': '0'})
        response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
        self.assertEqual(response.status_code, 200)
        upload.assert_not_called()
        self.assertFalse(ImagenProducto.objects.exists())

    @patch('tienda.panel_services.cloudinary.uploader.upload', side_effect=RuntimeError('Cloudinary unavailable'))
    def test_cloudinary_failure_rolls_back_database(self, upload):
        data = self.payload(self.product)
        data.update(management('images', 1))
        data.update({'images-0-imagen': image_file(), 'images-0-color_ref': 'colors-0', 'images-0-orden': '0'})
        with self.assertLogs('tienda.panel_views', level='ERROR'):
            response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
        self.assertContains(response, 'No pudimos guardar')
        self.product.refresh_from_db()
        self.assertEqual(self.product.precio, Decimal('100'))

    def test_image_update_preserves_file_and_delete_requires_confirmation(self):
        image = ImagenProducto.objects.create(producto=self.product, color=self.color, imagen='image/upload/v1/test.png')
        image.refresh_from_db()
        original = str(image.imagen)
        data = self.payload(self.product)
        data.update(management('images', 1, 1))
        data.update({'images-0-id': str(image.pk), 'images-0-color_ref': 'colors-0', 'images-0-orden': '3'})
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/', data).status_code, 302)
        image.refresh_from_db()
        self.assertEqual(str(image.imagen), original)
        self.assertEqual(image.orden, 3)
        data['revision'] = revision_for(self.product)
        data['images-0-DELETE'] = 'on'
        response = self.client.post(f'/panel/productos/{self.product.pk}/', data)
        self.assertContains(response, 'Confirmá la eliminación')
        self.assertTrue(ImagenProducto.objects.filter(pk=image.pk).exists())
        data['confirm_delete'] = 'on'
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/', data).status_code, 302)
        self.assertFalse(ImagenProducto.objects.filter(pk=image.pk).exists())

    @patch('tienda.panel_views.enviar_comprobante_cliente')
    def test_order_state_stock_and_manual_payment(self, email):
        def post(state, paid=False):
            self.order.refresh_from_db()
            data = {'estado': state, 'confirmar': 'on', 'revision': order_revision(self.order)}
            if paid:
                data['pagado'] = 'on'
            return self.client.post(f'/panel/pedidos/{self.order.pk}/', data)
        self.assertEqual(post('cancelado').status_code, 302)
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 3)
        self.assertEqual(post('cancelado').status_code, 302)
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 3)
        self.assertEqual(post('finalizado', True).status_code, 302)
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 2)
        email.assert_called_once()
        self.order.refresh_from_db()
        self.assertTrue(self.order.pagado)

    def test_reactivate_insufficient_stock_and_stale_order(self):
        self.order.estado = 'cancelado'
        self.order.save()
        self.size.stock = 0
        self.size.save()
        data = {'estado': 'en_proceso', 'confirmar': 'on', 'revision': order_revision(self.order)}
        self.assertContains(self.client.post(f'/panel/pedidos/{self.order.pk}/', data), 'No hay stock suficiente')
        Orden.objects.filter(pk=self.order.pk).update(pagado=True)
        self.assertContains(self.client.post(f'/panel/pedidos/{self.order.pk}/', data), 'cambió mientras lo editabas')

    def test_promotions_and_shipping_validation(self):
        for fields in [{'descuento_porcentaje': '-1'}, {'descuento_porcentaje': '101'}, {'descuento_fijo': '-1'}, {'descuento_fijo': '1', 'descuento_porcentaje': '10'}, {}]:
            response = self.client.post('/panel/promociones/nuevo/', {'codigo': 'TEST', **fields})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(CodigoPromocional.objects.exists())
        self.assertEqual(self.client.post('/panel/promociones/nuevo/', {'codigo': 'test', 'descuento_porcentaje': '10', 'activo': 'on'}).status_code, 302)
        self.assertEqual(CodigoPromocional.objects.get().codigo, 'TEST')
        self.assertEqual(self.client.post('/panel/envios/nuevo/', {'nombre': 'Envío', 'costo': '-1'}).status_code, 200)
        self.assertEqual(self.client.post('/panel/envios/nuevo/', {'nombre': 'Envío', 'costo': '50', 'activo': 'on'}).status_code, 302)

    def test_filters_and_public_pages(self):
        for url in ['/panel/productos/?stock=low', '/panel/productos/?stock=unconfigured', '/panel/productos/?activo=0', '/panel/pedidos/?desde=no-es-fecha', '/panel/pedidos/?q=%231', '/panel/pedidos/?pagado=0&estado=en_proceso']:
            self.assertEqual(self.client.get(url).status_code, 200)
        for url in ['/', '/tienda/', f'/tienda/{self.product.pk}/', '/tienda/carrito/', f'/tienda/talles/{self.color.pk}/']:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get('/tienda/checkout/').status_code, 302)

    def test_nested_changes_require_child_model_permission(self):
        staff = get_user_model().objects.create_user('catalog-editor', is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='change_producto'))
        self.client.force_login(staff)
        data = self.payload(self.product)
        data['colors-0-sizes-0-stock'] = '10'
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/', data).status_code, 403)
        self.size.refresh_from_db()
        self.assertEqual(self.size.stock, 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.precio, Decimal('100'))

    def test_order_requires_explicit_confirmation(self):
        response = self.client.post(f'/panel/pedidos/{self.order.pk}/', {
            'estado': 'cancelado', 'pagado': 'on', 'revision': order_revision(self.order),
        })
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.estado, 'en_proceso')
        self.assertFalse(self.order.pagado)

    def test_media_record_from_another_product_is_rejected(self):
        other = Producto.objects.create(nombre='Otro producto', precio=10)
        image = ImagenProducto.objects.create(producto=other, imagen='image/upload/v1/other.png')
        data = self.payload(self.product)
        data.update(management('images', 1, 1))
        data.update({'images-0-id': str(image.pk), 'images-0-color_ref': '', 'images-0-orden': '0', 'images-0-DELETE': 'on', 'confirm_delete': 'on'})
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/', data).status_code, 200)
        self.assertTrue(ImagenProducto.objects.filter(pk=image.pk, producto=other).exists())

    def test_product_can_be_deactivated_and_unconfigured_color_is_visible(self):
        ColorProducto.objects.create(producto=self.product, nombre='Rosa')
        response = self.client.get(f'/panel/productos/{self.product.pk}/')
        self.assertContains(response, 'Este color no tiene talles configurados.')
        data = self.payload(self.product)
        data.pop('producto-activo')
        self.assertEqual(self.client.post(f'/panel/productos/{self.product.pk}/', data).status_code, 302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.activo)
        self.assertNotContains(self.client.get('/tienda/'), self.product.nombre)
