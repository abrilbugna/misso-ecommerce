# Pedidos, despacho y seguimiento

## Operación del panel

El panel existente en `/panel/pedidos/` conserva sus permisos. El listado agrega productos, envío, código y fecha de despacho; el detalle separa pago, proceso, despacho y correos.

- **En proceso → Confirmado → En envío → Entregado.** Guardar el mismo estado no repite acciones.
- **Transferencia:** el checkout registra el pedido pendiente de pago. Después de comprobar la transferencia, marcar Pagado y Confirmado. No se envía otro correo al confirmar.
- **Efectivo:** se puede confirmar y despachar con el pago pendiente; Pagado indica que el dinero se recibió efectivamente.
- **Mercado Pago:** solo `_confirmar_pago_mercadopago`, consultando la API con un ID de pago, autoriza el pago. Verifica ID, aprobación, referencia de orden, ARS e importe exacto y finito. Guarda el ID y fecha de verificación. El panel y Django Admin no permiten cambiar manualmente ese pago. Un webhook repetido no retrocede estados ni crea notificaciones nuevas. Un pago tardío sobre un cancelado registra el cobro sin reactivar ni descontar stock: requiere atención de MISSO.
- **Cancelar:** permitido antes del despacho. Devuelve stock una sola vez. Reactivar a En proceso o Confirmado descuenta stock con bloqueo de variantes y verifica disponibilidad. Las transiciones que omiten pasos o retroceden se rechazan. Un pedido ya despachado no se cancela desde este flujo: una devolución física requiere conciliación de stock fuera de esta tarea.
- **Entregado:** se marca manualmente después de En envío; guarda fecha, no cobra ni notifica.

`order_services.py` concentra las reglas para panel y Django Admin. Usa transacciones, `select_for_update`, una revisión firmada de los campos relevantes y un contador de versión. El Admin técnico tampoco permite crear/eliminar órdenes o alterar sus ítems; su formulario usa el mismo servicio. Los datos personales, importes y método de compra permanecen de solo lectura.

## Despacho

En el detalle seleccionar el transportista real. Se sugiere Correo Argentino o Retiro cuando el nombre de la opción de envío lo identifica; se puede indicar Otro para entrega local sin seguimiento postal.

Para Correo Argentino se requieren código completo y plazo máximo entre 1 y 90 días hábiles. Se valida el formato (8–40 letras ASCII/números, sin espacios o guiones; se normaliza a mayúsculas), no la existencia de la pieza. Copiarlo de la etiqueta; el sistema nunca inventa códigos ni consulta la API postal.

Al pasar a En envío se fija `despachado_at` y se crea una notificación de despacho. Corregir el código o plazo cambia la página pública pero **no genera un correo nuevo**. El panel permite un reenvío explícito con los datos actuales. Si había un correo de despacho pendiente con datos anteriores, se pausa para revisión y reenvío explícito, evitando enviar un código que ya fue corregido. Para retiro se usa el mensaje “listo para retirar”, sin código ni enlace postal. Solo se registra un despacho en este flujo; no se reutiliza una orden entregada para un segundo envío.

## Correos y recuperación

Hay dos avisos principales al comprador: pedido registrado (transferencia/efectivo) o pago verificado (MP), y despacho. Se conserva el aviso inicial interno a MISSO, con una entrega independiente de la del comprador. Confirmado y Entregado no envían correos.

`EmailOrden` guarda tipo, secuencia, una clave UUID de idempotencia, destinatario/contenido congelado, intentos, primera tentativa, próximo intento, fecha aceptada, ID de Resend y error. Los registros se crean dentro de la misma transacción del pedido; el primer envío se intenta mediante `transaction.on_commit` después del commit. Un fallo de red/HTTP no revierte el pedido; la entrega permanece pendiente. Los logs no guardan el contenido ni la dirección del comprador.

Los reintentos usan **el mismo contenido y la misma clave**, con espera creciente hasta una hora. Resend conserva sus [claves de idempotencia durante 24 horas](https://resend.com/docs/dashboard/emails/idempotency-keys); después de 23 horas desde el primer intento se detiene el envío automático y se pide revisión manual para evitar duplicados ante respuestas ambiguas. “Enviado” significa aceptado por Resend, no confirmación de llegada a la bandeja del cliente.

En el panel:

1. **Reintentar el correo pendiente:** usa la misma clave y contenido dentro de la ventana segura.
2. **Reenviar con datos actuales:** exige confirmación, crea una nueva secuencia y clave, y detiene la versión anterior si estaba pendiente. Revisar primero Resend, especialmente si la respuesta original fue incierta. Un correo ya enviado no puede retirarse de la bandeja del comprador.

## Seguimiento público

`/seguir-pedido/` está conectado al footer sin cambios de diseño. Acepta número de pedido + DNI para ver únicamente la etapa de preparación/entrega. Para ver el código postal y los datos del despacho requiere el enlace privado `/seguir-pedido/<UUID>/` del correo. El token aleatorio tiene 122 bits de entropía; no deriva del ID ni del DNI.

El DNI nunca concede acceso a checkout, comprobantes o pago. Los pedidos históricos sin DNI siguen usando el enlace privado de sus correos; si no lo tienen pueden contactar a MISSO.

Un enlace válido concede acceso durante una hora en la sesión y redirige a la URL sin token. Respuestas privadas sin caché, sin indexación y con `Referrer-Policy: no-referrer`. No se incluyen dirección, teléfono, email, identificadores de pago o productos en la proyección pública. El formulario usa CSRF, errores genéricos y límites persistentes compartidos entre procesos: 30 intentos por IP y 10 por número de pedido cada 15 minutos. Los valores se guardan como HMAC, no en claro. Configurar el proxy para entregar la IP real como `REMOTE_ADDR`; no se confía en cabeceras `X-Forwarded-For` arbitrarias.

Las antiguas rutas de confirmación y pago por ID también requieren la sesión de compra o un acceso privado validado. Los clientes que reabran esas rutas en otro navegador usarán el email/enlace de seguimiento. El webhook no depende de cookies.

El progreso refleja exclusivamente la base de MISSO. El código puede copiarse para consultar el [seguimiento oficial de Correo Argentino](https://www.correoargentino.com.ar/seguimiento-de-envios); no se simulan movimientos de transporte.

## Modelos y migración

`0019_order_fulfilment` amplía `Orden` con trazabilidad de pago, transportista, código, plazo, fechas, token y versión; crea `EmailOrden` y `IntentoSeguimiento`.

Equivalencia explícita: `finalizado` era el cierre terminal del flujo anterior y pasa a `entregado` **independientemente de pagado**, conservando el marcador `finalizado_historico`. No existían datos que acrediten la fecha real de despacho o entrega: ambas quedan nulas y el panel lo aclara. Los otros estados anteriores y el valor de pago se preservan. Los pagos históricos se etiquetan “origen no registrado”; no se inventa una verificación de MP.

Cada orden existente recibe un UUID distinto antes de exigir el campo no nulo. Se conservan IDs, ítems, importes y stock. No se emiten correos durante la migración. Las órdenes anteriores donde el código viejo ya intentaba notificar (transferencia/efectivo y MP pagado) se marcan como avisos preexistentes para evitar envíos retrospectivos; no se afirma que hayan sido entregados. MP todavía impago podrá recibir su aviso al aprobarse.

La SQLite local estaba vacía de órdenes al revisar la implementación. La equivalencia y la preservación se prueban con registros históricos sintéticos, incluyendo finalizados impagos. No se consultó ni modificó la base de producción.

## Puesta en producción

El código está preparado; no se aplicó la migración a producción ni se configuraron tareas remotas.

1. Respaldar la base y desplegar en una ventana sin escrituras de checkout/panel, para completar la migración de tokens e históricos antes de atender con el modelo nuevo.
2. Revisar y aplicar `python manage.py migrate --plan` y `python manage.py migrate` en el entorno de despliegue.
3. Configurar `SITE_URL=https://misso.ar`, `RESEND_API_KEY`, `MISSO_EMAIL_FROM` y `MISSO_ADMIN_EMAIL` (o el fallback existente `EMAIL_HOST_USER`).
4. Programar cada minuto, con el mismo entorno y base de la aplicación: `python manage.py process_order_emails --limit 100`. No ejecuta ni reactiva suscripciones mensuales. Ejemplo de cron (ajustar rutas y carga de variables):

   ```cron
   * * * * * cd /ruta/misso && /ruta/misso/.venv/bin/python manage.py process_order_emails --limit 100
   ```

El primer intento ocurre al guardar; **los reintentos automáticos requieren esta tarea programada**. Sin ella, los pendientes siguen guardados y pueden reintentarse desde el panel. La misma tarea limpia contadores de acceso de más de un día.

## Verificación local

Usar siempre `--settings=misso.test_settings`: DB SQLite en memoria, credenciales falsas y transportes simulados. La suite cubre pagos, checkout, stock, permisos, CSRF, concurrencia optimista, correos, reintentos, histórico, acceso privado y regresiones del storefront/suscripciones. Los bloqueos SQL están preparados para PostgreSQL; las pruebas SQLite de revisión concurrente verifican formularios obsoletos, no una carga concurrente real de PostgreSQL.

```sh
.venv/bin/python manage.py test tienda --settings=misso.test_settings --noinput
.venv/bin/python manage.py makemigrations --check --dry-run --settings=misso.test_settings
.venv/bin/python manage.py check --settings=misso.test_settings
```

Resultado de esta implementación: **122 pruebas aprobadas**, `check` sin incidencias, migraciones sin diferencias pendientes y `git diff --check` limpio. Se revisaron en Chromium vistas con datos ficticios: seguimiento a 1440, 393 y 320 px, listado/detalle del panel a 1440 px y email a 393 px. Sin desbordamientos horizontales. La revisión del email fue una vista HTML en navegador, no un envío a Gmail.


## DNI del checkout (migración 0020)

`0020_order_dni_digest` agrega `Orden.dni_hash`, vacío para pedidos históricos. El checkout valida 7 u 8 dígitos ASCII, admite puntos en formato argentino y guarda HMAC-SHA256 con el UUID de cada pedido como contexto. No guarda el DNI ni lo agrega a correos, URLs, sesiones o registros del limitador; los formularios tampoco devuelven su valor en HTML. Las vistas marcan el campo como sensible para los reportes de errores de Django.

La clave es `ORDER_DNI_KEY` del entorno, con `SECRET_KEY` como respaldo. Debe mantenerse estable: cambiarla invalida las comparaciones existentes. Si se define después del primer pedido, conservar el valor usado originalmente. Los enlaces privados seguirán funcionando aunque no se pueda validar un DNI.

La consulta por DNI abre una sesión limitada durante una hora. El enlace privado abre una sesión separada de una hora y quita el token de la barra de direcciones. Un intento nuevo borra el acceso anterior; una consulta fallida no muestra datos del pedido consultado previamente. Solo se muestra tracking postal con enlace privado, estado En envío/Entregado, fecha de despacho y transportista Correo Argentino. Para retiro se utilizan mensajes específicos.

Correo Argentino: se comprobó su FAQ oficial que recomienda `/seguimiento`, pero esa URL devolvió 404 al revisarla. Se conserva `/seguimiento-de-envios`, que respondió correctamente. No se encontró una URL pública documentada y verificable que precargue cualquier código: se ofrece copiar el código y abrir la web oficial, sin scraping ni parámetros supuestos.

Para verificar esta ampliación sin tocar la base configurada en `.env`:

```sh
DJANGO_SETTINGS_MODULE=misso.test_settings .venv/bin/python manage.py test tienda
DJANGO_SETTINGS_MODULE=misso.test_settings .venv/bin/python manage.py makemigrations --check --dry-run
```

Aplicar `0020` en el entorno de despliegue antes de habilitar el nuevo checkout. Las pruebas no aplican migraciones a PostgreSQL de producción.

### Enlaces privados existentes (migración 0021)

La consulta pública utiliza únicamente DNI y número de pedido. Se retiró la solicitud de enlaces por email. Los enlaces privados de compra y despacho siguen vigentes; se conserva la compatibilidad con notificaciones de acceso ya registradas.

### Archivos de esta ampliación

- Acceso y DNI: `backend/tienda/order_identity.py`, `order_tracking.py`, `models.py`, `forms.py`, `views.py` y `backend/misso/settings.py`.
- Migraciones: `0020_order_dni_digest.py` y `0021_order_tracking_access_email.py`.
- Compatibilidad de correos de acceso existentes: `backend/tienda/order_emails.py`, `email_utils.py` y `frontend/templates/tienda/emails/acceso_pedido.html`. Los envíos inicial y de despacho conservan sus disparadores y enlaces privados.
- Interfaz: `frontend/templates/tienda/seguir_pedido.html`, `checkout.html`, `includes/bubble_nav.html`, `frontend/static/css/seguimiento.css`, `pill-buttons.css`, `frontend/static/js/seguimiento.js` y `pill-buttons.js`.
- Pruebas: `backend/tienda/test_order_tracking.py`, `test_order_management.py`, `test_public_storefront.py` y `tests.py`.
- Se reutilizan las rutas existentes de seguimiento y el enlace del footer; no fue necesario volver a modificarlos.

Validación: suite de 132 tests en SQLite aislado, sin servicios externos reales; comprobación de migraciones y sintaxis JS. Capturas en Chromium de formulario, estado limitado y acceso privado a 1440×900, 393×852 y 320×568 sin desbordamiento horizontal ni solapamiento de navegación. Se probó en el navegador la copia correcta y el fallback de selección cuando Clipboard API falla; se revisaron además la recuperación y los botones postales en 320 px. Las capturas usan datos sintéticos renderizados por Django, no la base de producción.
