# Cómo trabajar con el código

## Recorrido de una página

1. El navegador pide una URL.
2. `backend/misso/urls.py` dirige la solicitud a la tienda.
3. `backend/tienda/urls.py` elige una función de `views.py`.
4. Esa función usa los modelos y formularios para obtener o guardar información.
5. Django completa una plantilla de `frontend/templates/tienda/` con esos datos.
6. El navegador recibe el HTML y carga CSS, JavaScript, imágenes y fuentes de `frontend/static/`.

## Qué archivo editar

| Quiero cambiar… | Dónde hacerlo |
| --- | --- |
| Menú, pie de página o estructura común | `frontend/templates/tienda/base.html` |
| Colores, fuentes y estilos generales | `frontend/static/css/base.css` |
| Diseño del catálogo | `frontend/templates/tienda/catalogo.html` y `frontend/static/css/catalogo.css` |
| Selección de color, talle o cantidad | `frontend/static/js/detalle.js` |
| Aplicación del cupón en el navegador | `frontend/static/js/carrito.js` |
| Interacciones del checkout | `frontend/static/js/checkout.js` |
| Validación del formulario | `backend/tienda/forms.py` |
| Cálculos, stock, pedidos o pagos | `backend/tienda/views.py` y `models.py` |
| Campos de un producto o pedido | `backend/tienda/models.py`, luego generar una migración |
| Pantallas del administrador | `backend/tienda/admin.py` |
| Correos de compra | `backend/tienda/email_utils.py` |
| Claves y configuración de servicios | `.env` local o variables del proveedor |

## Convenciones

- Usar el mismo nombre para una página y sus recursos: `checkout.html`, `checkout.css`, `checkout.js`.
- Las plantillas extienden `tienda/base.html`. Los estilos van en `extra_css` y los scripts nuevos en `extra_js`.
- Cargar recursos con `{% load static %}` y `{% static 'images/archivo.png' %}`. En CSS, usar rutas relativas como `../fonts/ADELIA.otf`.
- El JavaScript estático no interpreta `{{ variables }}` de Django. Los scripts actuales reciben los valores necesarios mediante atributos `data-*` del elemento `<script>` y los leen con `document.currentScript.dataset` al cargar. Para estructuras complejas, usar `json_script` de Django.
- Los atributos `style` y los eventos HTML existentes se conservaron para mantener el diseño y las interacciones. Los bloques completos de CSS y JavaScript están separados.
- Validar precios, descuentos, stock y permisos en el backend; el navegador solo presenta la información e interacciones.
- Mantener las migraciones dentro de `backend/tienda/migrations/`. Los nombres de las aplicaciones Django se conservaron, por lo que este movimiento no necesita migraciones nuevas.
- `staticfiles/` es la salida generada por `collectstatic`; editar los originales en `frontend/static/`.
- Las fotos de productos se administran mediante los modelos y Cloudinary; `images/` contiene los recursos fijos del diseño.
