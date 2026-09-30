# Tienda pública sin suscripciones

La experiencia pública se controla con `SUBSCRIPTIONS_PUBLIC_ENABLED`, que por
defecto es `False`. Es independiente de `MP_SUBSCRIPTION_ENABLED` y del Mercado
Pago de compras normales. No modifica contratos existentes en Mercado Pago.

## Auditoría y cambios

- Home: eliminado el enlace «¿Un conjunto cada mes? Conocé la suscripción» y su
  CSS. El wrapper de acciones permanece porque anima el CTA de productos. Se
  quitó su gap exclusivo entre los dos enlaces. El ancla del hero se llama ahora
  `coleccion`. No se modificó `inicio.js`, la intro, el scroll lock ni el cálculo
  responsive del hero.
- Videos: conservados los tres videos, stack, controles y animaciones. Nuevo
  texto: «Nueva línea en camino…», «Preparamos / algo nuevo.» y «Muy pronto llega
  una nueva colección de ropa deportiva a Misso.». CTA «Ver ropa deportiva».
  Solo se amplió el botón para alojar el nuevo texto con el estilo existente.
- Tienda: retirada la tarjeta de suscripción que aparecía tras el cuarto
  producto («La sorpresa mensual», preferencias, «$25.000 / mes» y enlace).
  Eliminados su CSS, selector y animación GSAP exclusiva. Los filtros, blob y
  ordenamiento de productos se mantienen.
- Footer compartido: eliminados términos y baja de suscripción; permanecen el
  contacto y «Seguir pedido», sin inventar términos generales.
- Información, formulario y resultado: sus textos, FAQs, términos, títulos y
  scripts permanecen en templates dormidos, pero no se sirven con la bandera
  pública desactivada. No se hallaron otras referencias en las páginas públicas
  de productos, carrito o checkout.

## Rutas, altas y correo

Con la bandera desactivada, información, comienzo, resultado y endpoint de
estado redirigen a `/tienda/` con HTTP 302 y `Cache-Control: no-store`. La
protección se ejecuta antes de consultar referencias, crear sesiones de alta,
validar formularios o iniciar pagos. Los POST con CSRF inválido siguen siendo
rechazados por Django antes de alcanzar las vistas.

También se bloquean `create_intention`, `start_checkout` y el POST remoto de
`SubscriptionAPI.create_pending`. Se pausan tanto el encolado como el envío de
bienvenidas, incluyendo las ya pendientes, sin borrar registros ni incrementar
intentos. Las plantillas históricas de emails y los correos de pedidos no cambian.

Se conservan modelos, migración 0016, integración recurrente, firma de webhooks,
worker, conciliación, tests y panel privado. Si la integración recurrente sigue
habilitada, los webhooks pueden actualizar el historial sin generar nuevas
altas ni enviar bienvenidas. No se cancelan ni pausan contratos remotos.

## Categoría deportiva y despliegue

`CATEGORIA_ROPA_DEPORTIVA = 'ropa-deportiva'` se añade a los choices de Producto.
La migración `0017_add_ropa_deportiva_category` contiene únicamente un
`AlterField`; no crea productos ni cambia su categoría. Conserva las cinco
categorías anteriores. El panel toma los choices del modelo automáticamente.

El CTA usa la URL nombrada `catalogo` y esa constante para generar
`/tienda/?categoria=ropa-deportiva`. El filtro muestra el empty state normal con
cero productos y mostrará automáticamente los productos activos que se asignen
a la nueva categoría.

Al desplegar, ejecutar las migraciones y la publicación habitual de estáticos.
Mantener `SUBSCRIPTIONS_PUBLIC_ENABLED=False`; no es necesario deshabilitar
Mercado Pago de productos ni cambiar sus credenciales. La migración 0017 se aplicó posteriormente en la base PostgreSQL configurada
en `.env`, tras comprobar que era la única pendiente y que su SQL era
`no-op`: no alteró productos ni tablas. Esto no despliega el código de la web.

Para recuperar las rutas de suscripción se puede activar la bandera pública,
manteniendo además la configuración propia de la integración recurrente. Eso
también reanuda los emails pendientes. Recuperar los enlaces y copy promocional
de Git es una decisión separada: la bandera no los vuelve a insertar.

## Verificación

Ejecutar la suite indicando la app, porque la estructura del repositorio no
descubre los tests con el comando sin etiqueta:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py test tienda --settings=misso.test_settings --noinput
.venv/bin/python manage.py makemigrations --check --dry-run --settings=misso.test_settings
```

Los tests usan una base aislada y transportes de pago/correo simulados. Cubren
la limpieza pública, hero/videos, CTA, filtro vacío y con productos, altas
bloqueadas incluso desde formularios anteriores, correos pausados, panel y
webhooks históricos, y el checkout/Mercado Pago de compras normales. Las
advertencias locales W102/W103 preexistentes corresponden a la configuración
recurrente, no a errores del cambio.

Resultado local: 86 tests aprobados. `check` aislado sin incidencias y sin
migraciones faltantes; `check` con configuración local termina correctamente
con las dos advertencias recurrentes ya indicadas. Sintaxis de JavaScript y
`git diff --check` correctos.

La revisión automatizada en Chromium cubre 1440×900, 1920×1080, 768×1024,
393×852, 393×700 y 320×568: hero completo en mobile, intro liberada, shimmer,
transforms finales, copy sin solaparse con videos, avance del carrusel, CTA,
empty state deportivo, blob, scroll horizontal del filtro y redirecciones.
Sin overflow horizontal ni warnings GSAP. No equivale a una prueba física en
Safari/iPhone. No se hizo deploy.

## Archivos modificados

- `.env.example`
- `backend/misso/settings.py`
- `backend/misso/test_settings.py`
- `backend/tienda/context_processors.py`
- `backend/tienda/models.py`
- `backend/tienda/views.py`
- `backend/tienda/subscription_access.py` (nuevo)
- `backend/tienda/subscription_api.py`
- `backend/tienda/subscription_emails.py`
- `backend/tienda/subscription_services.py`
- `backend/tienda/subscription_views.py`
- `backend/tienda/migrations/0017_add_ropa_deportiva_category.py` (nueva)
- `backend/tienda/test_public_storefront.py` (nuevo)
- `backend/tienda/test_subscriptions.py`
- `backend/tienda/tests.py`
- `frontend/static/css/inicio.css`
- `frontend/static/css/catalogo.css`
- `frontend/static/js/catalogo.js`
- `frontend/templates/tienda/inicio.html`
- `frontend/templates/tienda/catalogo.html`
- `frontend/templates/tienda/base.html`
- `docs/TIENDA_PUBLICA_PRODUCTOS.md` (nuevo)
