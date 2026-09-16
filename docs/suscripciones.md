# Suscripciones recurrentes de Misso

## Flujo elegido y diferencia respecto de la propuesta inicial

Revisión de documentación oficial: 15/09/2026.

Se usa **Mercado Pago Suscripciones**, `POST /preapproval`, `status=pending`,
con recurrencia mensual y redirect al `init_point` devuelto por MP. **No se usa
Checkout Pro, preferencias de compra única, órdenes ni el carrito.**

La documentación actual impone `card_token_id` y `status=authorized` al crear una
suscripción **con plan asociado**. En cambio, documenta la creación pendiente y
el checkout alojado sin plan asociado. Para conservar la autorización dentro de
MP y la correlación segura por intención, se implementa esta segunda alternativa.
No se agrega un supuesto `preapproval_plan_id` a una creación pendiente ni se
pasan parámetros de correlación no documentados al enlace público de un plan.

Por tanto, **esta implementación no crea ni asocia un plan remoto**. Existe una
única definición comercial en settings/env, copiada como contrato histórico en
cada intención. `MP_SUBSCRIPTION_PLAN_ID` debe quedar vacío; si se configura, el
inicio falla de forma segura en lugar de fingir una asociación. Para pasar a un
plan asociado hace falta implementar la tokenización oficial de tarjeta y revisar
ese cambio de experiencia. El modelo conserva `mp_plan_id` para representar el
recurso, pero no inventa un ID de plan. No hay comando de creación de planes.

Fuentes principales:

- [Resumen](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/overview).
- [Con plan asociado y su requisito de token](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/integration-configuration/subscription-associated-plan).
- [Sin plan asociado, pago pendiente y link alojado](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/integration-configuration/subscription-no-associated-plan/pending-payments).
- [Crear preapproval](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/create-preapproval/post).
- [Consultar preapproval](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/get-preapproval/get).
- [Planes: API](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/create-preapproval-plan/post).
- [Webhooks y firma](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/additional-content/your-integrations/notifications/webhooks).
- [Facturas recurrentes](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/get-authorized-payment/get).
- [Buscar factura por pago](https://www.mercadopago.com.ar/developers/es/reference/online-payments/subscriptions/authorized-payment-search/get).

## Recorrido

1. El formulario conserva destino, talle, tipo de prenda, color preferido, color a
   evitar, estilo, carta y comentarios. Se agregan nombre completo, email,
   teléfono y aceptación explícita de los términos existentes. No había apellido
   separado ni dirección en el formulario original; no se inventaron preferencias
   ni preguntas de envío.
2. Validación Django + CSRF + token de envío firmado y vinculado a la sesión.
3. Se guarda `Suscripcion(estado=pendiente)` **antes** de contactar a MP, con
   `MISSO-SUB-<uuid>` único, aceptación fechada y snapshot de las respuestas.
4. Se reclama la creación mediante un UPDATE condicional atómico, se confirma
   esa transacción local y recién entonces se solicita `/preapproval`.
5. Se guarda ID/init_point y se redirige al checkout HTTPS de MP. La respuesta de
   creación no activa la suscripción ni envía bienvenida.
6. MP llama al webhook. El endpoint valida la firma y guarda el evento en una
   bandeja persistente antes de responder 200. Si no pudo guardar, no confirma
   la recepción; MP puede reintentar.
7. `process_subscriptions` consulta MP, aplica el estado y guarda dos emails en
   una cola local dentro de la misma transacción de activación.
8. El worker entrega la bienvenida al cliente y la notificación al administrador
   mediante Resend. El retorno muestra el estado local y consulta cada 5 segundos
   durante dos minutos; queda disponible la actualización manual.

## Configuración

Producción reutiliza `MP_ACCESS_TOKEN` → `MERCADOPAGO_ACCESS_TOKEN`. Pruebas usan
`MP_SUBSCRIPTION_MODE=test` y `MP_SUBSCRIPTION_TEST_ACCESS_TOKEN`, sin fallback al
token de compras. `PUBLIC_BASE_URL` define el origen de desarrollo; se reutilizan
`RESEND_API_KEY` y el transporte Resend del ecommerce. Ver PASOS PARA ABRIL al final.

| Variable | Uso |
| --- | --- |
| `MP_SUBSCRIPTION_ENABLED` | `False` por defecto. Habilitar solo en el entorno preparado. |
| `MP_ACCESS_TOKEN` | Token de la cuenta correspondiente al entorno; compartido con la integración existente. |
| `MP_SUBSCRIPTION_AMOUNT` | Importe mensual, default 25000. Decimal. |
| `MP_SUBSCRIPTION_CURRENCY` | `ARS`. |
| `MP_SUBSCRIPTION_REASON` | Nombre comercial que MP muestra al cliente. |
| `MP_SUBSCRIPTION_PLAN_ID` | **Vacío** para el flujo alojado implementado; no activa soporte de planes asociados. |
| `MP_WEBHOOK_SECRET` | Secreto de firma de la aplicación MP. |
| `SITE_URL` | Origen del sitio; fallback de checkout solo en modo production. |
| `PUBLIC_BASE_URL` | Origen HTTPS del túnel/staging; obligatorio para checkout en test. |
| `MP_SUBSCRIPTION_MODE` | `test` por defecto; `production` reutiliza el token de compras. |
| `MP_SUBSCRIPTION_TEST_ACCESS_TOKEN` | Token del vendedor de prueba, aislado del token existente. |
| `MISSO_ADMIN_EMAIL` | Destinatario administrativo; si falta reutiliza `EMAIL_HOST_USER`/`NOTIFICACION_EMAIL`. |
| `MISSO_EMAIL_FROM` | Remitente verificado en Resend; default `Misso <hola@misso.ar>`. |
| `RESEND_API_KEY` | Clave existente del proveedor de correo. |

La periodicidad se fija en un solo lugar: `MP_SUBSCRIPTION_FREQUENCY=1` y
`MP_SUBSCRIPTION_FREQUENCY_TYPE='months'` en settings. Cambiarla requiere revisar
los textos que indican mensual; no se ofrece una periodicidad arbitraria.

El precio de home, información, formulario y nuevas intenciones proviene del
mismo setting mediante `subscription_offer`. No se cambió su diseño ni la
redacción legal: se sustituyeron solamente los importes literales por el valor
configurado. Cambiar el setting no modifica retroactivamente los contratos
remotos existentes. Si el monto/moneda/periodicidad remoto no coincide con el
contrato guardado, la verificación queda en error para revisión; no se declara
una autorización con términos distintos.

## Puesta en marcha (no ejecutada contra producción)

1. Configurar variables en un entorno aislado de prueba.
2. Aplicar la migración **aditiva**:

   ```sh
   python manage.py migrate
   python manage.py check
   ```

3. Programar el worker cada minuto en el mismo entorno/base que Django:

   ```sh
   python manage.py process_subscriptions --limit 100
   ```

   En un scheduler/cron del servicio, ejecutar ese comando con el virtualenv y
   variables del proyecto. **El worker es obligatorio:** recibir 200 del webhook
   significa que el evento se guardó; la activación ocurre cuando lo procesa.
   Puede haber una demora de aproximadamente un ciclo del scheduler. Usar
   PostgreSQL en producción para los bloqueos por fila. SQLite se usa en pruebas
   aisladas y desarrollo; ejecutar un solo worker en SQLite.

4. Otorgar `tienda.view_suscripcion` a los usuarios activos/staff que deban ver la
   nueva sección. Los superusuarios ya tienen acceso. Staff sin permiso recibe
   403, igual que las demás áreas del panel.
5. Habilitar `MP_SUBSCRIPTION_ENABLED=True` **solo después** del setup del entorno.
6. Ejecutar las pruebas de integración de MP con usuarios y tarjetas de prueba.
   La implementación no ejecutó estos pasos ni usó dinero real.

### Mercado Pago Developers

- Usar la aplicación/cuenta del vendedor correspondiente al entorno.
- Configurar el secreto de firma en `MP_WEBHOOK_SECRET`.
- Endpoint público: `https://TU-DOMINIO/mercadopago/webhooks/subscriptions/`.
- Tópicos soportados: `subscription_preapproval`,
  `subscription_authorized_payment` y `payment`.
- El payload de creación incluye `notification_url` con
  `?source_news=webhooks`. La documentación actual de Webhooks tiene una salvedad
  para Suscripciones sobre la configuración desde Tus integraciones y remite a
  configurar durante la creación. Confirmar en el entorno de prueba que esa
  aplicación entrega los tópicos y la firma a esta URL. Si el panel permite
  configurar “Planes y suscripciones”, usar la misma URL y esos tópicos.
- **No reemplazar** el webhook de compras normales. Sigue en
  `/tienda/pago/mp/webhook/`, y su `notification_url` sigue intacta.
- `subscription_preapproval_plan` se ignora: este flujo no tiene plan remoto y
  un evento de plan nunca puede activar a un cliente.
- No aceptar notificaciones IPN sin firma como fallback. Si no llega una firma
  válida, revisar la configuración/delivery con MP antes de habilitar producción.

## Modelos y migración

Migración: `0016_suscripcion_eventomercadopago_pagosuscripcion_and_more`.
No altera Orden, Producto, carrito ni sus migraciones previas.

- `Suscripcion`: UUID público, clave única de envío, referencia externa única,
  contacto, preferencias consultables (destino/talle/tipo/estilo), snapshot JSON,
  importe/moneda/frecuencia históricos, términos fechados y URL, ID/plan/estado
  MP, autorización/cancelación/próximo cobro, control de creación, último evento,
  timestamps y confirmaciones de email por destinatario.
- `PagoSuscripcion`: factura y/o pago con identificadores externos UNIQUE,
  fecha, importe, moneda, estado del pago y estado de factura. Une las
  notificaciones de factura y pago; conserva pagos anteriores cuando MP genera
  un nuevo intento para la misma factura.
- `EventoMercadoPago`: inbox autenticada, identidad de evento UNIQUE,
  recurso/tópico/acción, recepción, intentos, error saneado y próximo reintento.
  No almacena indiscriminadamente el body ni datos de tarjetas.
- `EmailSuscripcion`: outbox con restricción UNIQUE `(suscripcion,tipo)`,
  payload HTML inmutable, intentos, entrega, ID Resend y revisión manual.

Snapshot versión 1: lista ordenada de `campo`, `pregunta`, `valor` original y
`respuesta` legible. Incluye todos los campos actuales, incluso opcionales vacíos,
los textos libres y los datos personales. En emails/panel se muestra el snapshot,
no etiquetas recalculadas con una versión futura del formulario. Django escapa
el texto libre en los templates.

Mapeo: `pending` → Pendiente; `authorized` → Activa; `paused` → Pausada;
`cancelled` → Cancelada. Un estado MP desconocido → Error. Una autorización de
recurrencia no se confunde con un cobro aprobado; los cobros tienen su propio
historial.

## Firma, correlación e idempotencia

Se usa `WebhookSignatureValidator` del SDK oficial instalado (`mercadopago 3.1.1`).
Aplica HMAC-SHA256 y comparación constante del manifiesto
`id:<data.id en minúsculas>;request-id:<x-request-id>;ts:<ts>;`, siguiendo las
reglas oficiales para componentes ausentes. Se exige el `data.id` firmado en
query y que coincida con el ID del body; nunca se usa el body para sustituir un
ID que no fue firmado. No se impone una ventana de antigüedad adicional al
validador: MP reintenta notificaciones, y la deduplicación + reconsulta actual
impiden que un replay vuelva a autorizar/emailar un estado antiguo.

La consulta autenticada por Access Token, ID de recurso, `external_reference`,
ID local/remoto y condiciones comerciales debe coincidir. Nunca se vincula por
email. Se bloquea la suscripción antes de la consulta definitiva y se descartan
snapshots con fecha remota anterior al último aplicado.

- Dos clics con el mismo formulario/sesión comparten la clave única y el mismo
  recurso remoto. Un token firmado de otra sesión no es válido.
- HTTP POST a MP ocurre fuera de la transacción de creación local. Un timeout,
  una respuesta exitosa incompleta o un crash dejan `uncertain/creating`.
- El siguiente intento y el worker buscan por `external_reference`. Si no hay
  resultados, **no vuelven a crear**: una búsqueda vacía puede deberse a demora
  de consistencia de MP. Así se evita generar contratos adicionales por un
  timeout. Si hay múltiples coincidencias, se registra un error para revisión.
- Un error inequívoco antes de crear permite reintentar manteniendo la intención
  y sus respuestas. Una intención ya enviada conserva su snapshot original.
- La bandeja deduplica eventos y la base impide duplicados en pagos/emails.
- Procesar un pago recurrente o reactivar una suscripción nunca crea una segunda
  bienvenida.

### Emails y límites de entrega distribuida

Los templates nuevos heredan el branding existente (logo Cloudinary, crema,
rosa y bordó), con HTML compatible e inline CSS. No ejecutan JS/GSAP.

El cliente recibe todas sus respuestas, importe, periodicidad, alta, términos
absolutos y enlace al sitio. El admin recibe además IDs y enlace absoluto al
panel. Los IDs MP no se muestran en el email del cliente.

Se reutiliza Resend con `Idempotency-Key` estable por suscripción/destinatario.
Cada email tiene su propio timestamp: si solo falla el del admin, no se reenvía
el del cliente. Un fallo de email no cambia el estado Activa.

[Resend conserva las claves 24 horas](https://resend.com/docs/dashboard/emails/idempotency-keys).
Para evitar duplicar una entrega de resultado incierto, a las 23 horas del primer
intento se detienen los reintentos automáticos y se marca revisión manual.
No existe garantía universal de “exactamente una vez” entre SQL y un proveedor
HTTP; el diseño combina outbox, bloqueo e idempotencia del proveedor y prioriza
no duplicar fuera de su ventana. Consultar el historial de Resend antes de
cualquier resolución manual. No resetear flags ni claves para “forzar” un envío.

## Rutas

- `/suscripcion/comenzar/`: formulario existente, ahora conectado a MP.
- `/suscripcion/resultado/<uuid>/`: retorno de estado local.
- `/suscripcion/resultado/<uuid>/estado/`: JSON mínimo para actualizar el retorno.
- `/mercadopago/webhooks/subscriptions/`: POST firmado.
- `/panel/suscripciones/`: búsqueda, estados y fechas.
- `/panel/suscripciones/<id>/`: contacto, contrato, preferencias, términos,
  emails, pagos e historial.
- `/admin/`: modelos registrados en modo lectura; no permite falsificar estados.

La URL pública usa un UUID aleatorio y solo muestra estado, sin preferencias ni
contacto. El retorno lleva `no-store`, `noindex` y `no-referrer`. GET y query
params nunca activan una suscripción ni disparan emails.

No se agregó cancelación remota ni local desde el panel. Cancelación, pausa y
reactivación se sincronizan desde MP.

## Diagnóstico y recuperación

- Eventos fallidos: revisar `EventoMercadoPago` en `/admin/`, su código y próximo
  intento. Los reintentos tienen backoff acotado a una hora.
- Intenciones inciertas: revisar por referencia/ID con MP, sin repetir el POST.
- Para reconsultar una suscripción conocida (GET remoto, sin cobros):

  ```sh
  python manage.py process_subscriptions --sync ID_LOCAL
  ```

- Una intención incierta sin coincidencias remotas requiere conciliación
  administrativa antes de permitir un nuevo contrato. No hay botón que asuma que
  el timeout significó fracaso.
- Emails pendientes/errores: visibles en el detalle y en `/admin/`.
- Los logs incluyen IDs locales, transición y códigos; no incluyen tokens,
  respuestas completas de MP ni texto libre del formulario.

## Tests y entorno sin dinero real

Pruebas automáticas con SQLite aislado y mocks:

```sh
python manage.py test tienda --settings=misso.test_settings --noinput
python manage.py check --settings=misso.test_settings
python manage.py makemigrations --check --dry-run --settings=misso.test_settings
```

`misso.test_settings` reemplaza base y credenciales; las pruebas nuevas bloquean
cualquier llamada HTTP que no esté mockeada. Cubren formulario, términos,
snapshot, duplicados, firma, consultas API, estados, pagos, emails/reintentos,
permisos, retornos, worker, y ejecutan también los tests existentes de compras y
panel. La migración se aplica a la base de test, **no a producción**.

Para la prueba manual posterior: usar un despliegue/base separados, cuenta
vendedora de prueba, comprador de prueba distinto y sus credenciales según el
producto Suscripciones. No cambiar las credenciales del ecommerce en producción
para probar. Abrir el checkout con el comprador de prueba y usar únicamente
[tarjetas/cuentas de prueba oficiales](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/integration-test/payment-approval).
Consultar también [cuentas de prueba](https://www.mercadopago.com.ar/developers/es/docs/your-integrations/test/accounts).
No inferir el entorno por el prefijo del token: las credenciales de una cuenta
vendedora de prueba pueden usar el prefijo de credenciales productivas de ESA
cuenta de prueba. Confirmar siempre la cuenta propietaria antes de probar.

Verificar entrega real del webhook firmado, correr el worker, comprobar una sola
bienvenida por destinatario y repetir la notificación. Esto sigue pendiente de
configuración del operador; los tests con mocks no prueban la aceptación real
de las credenciales, permisos, `notification_url` ni medios de pago de MP.

## Archivos

Backend: `subscription_models.py`, `subscription_forms.py`, `subscription_api.py`,
`subscription_services.py`, `subscription_emails.py`, `subscription_views.py`,
`subscription_panel.py`, comando `process_subscriptions`, migración 0016,
`test_subscriptions.py` y `misso/test_settings.py`.

Integración: `models.py`, `admin.py`, `views.py` (se elimina el flujo WhatsApp),
`context_processors.py`, `misso/settings.py`, `misso/urls.py`, `panel_urls.py`,
`.env.example`.

Frontend: formulario y CSS existente, nueva página/JS de resultado, templates
HTML de emails, navegación/listado/detalle del panel. En home e información se
sustituye solamente el importe literal por configuración compartida.

### Validación realizada en esta implementación

- 69 tests de `tienda`: pasan (suscripciones, compras normales y panel existente).
- `manage.py check`, comprobación de migraciones pendientes y sintaxis del JS: pasan.
- Medición en Chromium de formulario, resultado, listado y detalle en 1920,
  1440, 1280, 1024, 768, 430, 412, 390, 375, 360 y 320 px: sin overflow horizontal.
- Las cinco variantes de resultado responden correctamente; parámetros de éxito
  del navegador no alteran la suscripción.
- Capturas revisadas de escritorio y mobile con datos ficticios. Se corrigió una
  colisión de clase CSS en la aceptación de términos.
- Pruebas y preview usan SQLite temporal y llamadas externas mockeadas/bloqueadas.
  No se aplicaron migraciones a la base configurada ni se enviaron emails reales,
  crearon planes o autorizaron cargos en MP.

## Corrección del 503 y PASOS PARA ABRIL (15/09/2026)

### Causa comprobada

En el `.env` local faltaba `MP_SUBSCRIPTION_ENABLED`: se evaluaba `False`.
`start_checkout()` lanzaba `subscriptions_disabled` antes de llamar a MP;
la vista ocultaba ese motivo tras el formulario con HTTP 503. No era un fallo
causado por GSAP ni una respuesta 503 recibida de Mercado Pago.
Además, la validación exigía webhook secret y email administrativo para crear
el preapproval. Esa dependencia fue eliminada: solo afecta la confirmación y
las notificaciones posteriores.

Se habilitó el flag local y se separó el token de suscripciones de prueba del
token existente de compras. No se verificó remotamente ni se modificó ese token
existente. El modo `test` **no convierte una cuenta real en una cuenta de prueba**:
es obligatorio colocar credenciales pertenecientes al vendedor de prueba.
No hay fallback automático al token de compras. `production` es una elección
explícita que reutiliza `MP_ACCESS_TOKEN`; no se habilitó aquí.

### 1. Crear vendedor y comprador de prueba

En Mercado Pago Developers → Tus integraciones → tu aplicación → Cuentas de
prueba, creá dos cuentas de **Argentina**, una Vendedor y otra Comprador.
Guardá sus usuarios, contraseñas y código de verificación. En una sesión
separada iniciá sesión como **vendedor de prueba**, configurá su aplicación y
obtené su Access Token en las credenciales de esa aplicación. Aunque el panel
lo denomine credencial de producción, debe pertenecer al **usuario de prueba**,
nunca a tu vendedor real. El prefijo de un token no demuestra que sea seguro.

Fuente: [Cuentas de prueba oficiales](https://www.mercadopago.com.ar/developers/es/docs/your-integrations/test/accounts).

### 2. Abrir un túnel público

Con ngrok instalado y autenticado, ejecutá en otra terminal:

```sh
ngrok http 8000
```

Copiá el origen HTTPS que muestre ngrok (sin rutas). No hay dominio de túnel
hardcodeado. Esta integración requiere una base pública HTTPS para checkout;
no presupone que MP acepte localhost como retorno. La documentación del flujo
pending muestra HTTPS, pero no explicita todas las excepciones para localhost.
El webhook sí necesita acceso desde Internet. La base pública también evita que
el retorno de una prueba termine accidentalmente en `https://misso.ar`.

### 3. Completar `.env`

Ya quedaron escritos estos valores:

```dotenv
MP_SUBSCRIPTION_ENABLED=True
MP_SUBSCRIPTION_MODE=test
MP_SUBSCRIPTION_AMOUNT=25000
MP_SUBSCRIPTION_CURRENCY=ARS
```

Completá las líneas vacías **con valores reales obtenidos en los pasos anteriores**:

- `MP_SUBSCRIPTION_TEST_ACCESS_TOKEN`: Access Token del vendedor de prueba.
- `PUBLIC_BASE_URL`: origen HTTPS exacto del túnel o staging, sin slash final.
- Dejá `MP_SUBSCRIPTION_PLAN_ID` vacío: este checkout crea `/preapproval` pending
  sin plan asociado y sin pedir tarjeta en Misso.
- No cambies `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY` ni `DATABASE_URL` para esta corrección.

La configuración añade solo el host indicado a `ALLOWED_HOSTS` y su origen HTTPS
a `CSRF_TRUSTED_ORIGINS`; no usa comodines para todos los túneles.

### 4. Reiniciar y probar el redirect

Desde la raíz del proyecto:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Si ya corre Django, detenelo con Ctrl+C antes de reiniciar. Abrí la home, completá
el formulario usando el email del **comprador de prueba**, aceptá términos y
presioná Suscribirme. En Network debe aparecer POST `/suscripcion/comenzar/`
con **302** y Location apuntando al `init_point` oficial. Usá una sesión de
navegador separada para iniciar sesión en MP como comprador de prueba. Nunca
uses tu comprador personal ni una tarjeta real. Para autorizar en test, seguí
las [instrucciones oficiales](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/integration-test/payment-approval)
y sus tarjetas de prueba argentinas.

Si falta configuración, `check` y el arranque muestran W101/W102; en DEBUG el
formulario muestra la variable faltante. Los errores HTTP registran status,
error/message sanitizados y request ID. Un timeout/5xx o una creación sin ID o
init_point queda como incierta y no vuelve a hacer POST automáticamente.

### 5. Completar la confirmación por webhook y correos

La URL es `PUBLIC_BASE_URL` + `/mercadopago/webhooks/subscriptions/`.
El payload incluye esa URL en `notification_url`, con `?source_news=webhooks`.
En la aplicación del vendedor de prueba configurá los eventos de Planes y
suscripciones (`subscription_preapproval`, `subscription_authorized_payment`)
y Pagos (`payment`) cuando el panel lo permita; ver la salvedad de la sección
Mercado Pago Developers más arriba. Copiá su secreto de firma a
`MP_WEBHOOK_SECRET` y reiniciá Django. No modifiques el webhook de compras.

`RESEND_API_KEY` ya está presente; el destinatario administrativo efectivo se
obtiene del email existente. Podés definir `MISSO_ADMIN_EMAIL` explícitamente
si necesitás otro destinatario de prueba. No se enviaron emails durante esta
corrección. Revisá destinatarios antes de procesar una autorización de prueba.

Luego de recibir el evento ejecutá:

```sh
.venv/bin/python manage.py process_subscriptions --limit 100
```

Para confirmaciones continuas, programá ese comando cada minuto. El webhook
solo guarda el evento firmado; este worker consulta MP, actualiza el estado y
envía los emails idempotentes. Sin secreto el checkout puede abrir, pero el
webhook responde 503 y la suscripción no se confirma por esa vía.

### Validación realizada

- `manage.py check`: termina sin errores; advierte los tres datos pendientes
  (token de prueba, URL pública y secreto de webhook).
- `showmigrations tienda`: **[X] 0016**, consulta de solo lectura a la base configurada.
- 48 tests de suscripciones y 76 tests de la suite `tienda`: OK, con HTTP simulado.
- Incluye adapter → payload → respuesta id/init_point → persistencia → 302,
  API 400/401/500, token ausente, firma, doble envío y regresiones de compras.
- Sin cambios de modelos/migraciones, sin operaciones en MP ni cobros reales.
- El checkout remoto todavía requiere el token y URL que debe completar Abril;
  recibir un init_point desde la API real no se verificó durante esta tarea.
