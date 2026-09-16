# Panel Misso

Backoffice propio en `/panel/`, implementado sobre los modelos existentes de `tienda`.
Django Admin continúa en `/admin/`. No hay cambios de modelos ni migraciones.

## Acceso

`/panel/login/` acepta el usuario de Django o un email que identifique una única cuenta.
Se requiere una cuenta activa con `is_staff=True`. El superusuario accede a todas las
secciones. Para otros usuarios staff se respetan los permisos Django `view`, `add`,
`change` y `delete` de cada modelo; asignarlos desde el admin técnico.

Editar un producto requiere `change_producto` (crear requiere `add_producto`). Cada
cambio en colores, talles, imágenes y videos comprueba además el permiso correspondiente.
La eliminación de un archivo asociado requiere `delete_imagenproducto` o
`delete_videoproducto`. No se ofrecen eliminaciones de productos, colores, talles,
promociones, envíos ni pedidos.

Todas las operaciones de escritura son POST con CSRF. Logout también es POST.
Las páginas protegidas no se almacenan en caché. No se han creado usuarios ni datos reales.

## Organización

- `panel_urls.py`: namespace `panel` y rutas.
- `panel_access.py`: protección reutilizable de staff y permisos.
- `panel_views.py`: dashboard, listados, filtros, paginación y formularios.
- `panel_forms.py`: ModelForms, formsets acotados y validaciones.
- `panel_services.py`: coordinación transaccional de producto y pedido.
- `frontend/templates/panel/`: layout propio y componentes.
- `frontend/static/css/panel.css`: estilos aislados, tokens y fuentes de `base.css`.
- `frontend/static/js/panel.js`: formsets dinámicos, previews y ayudas de validación.

## Edición de producto

Una sola petición coordina un ModelForm de Producto, un inline formset de ColorProducto,
un inline formset de TalleProducto por color y formsets de ImagenProducto/VideoProducto.
El servidor verifica que los IDs y `INITIAL_FORMS` coincidan con los registros del padre.
No se aceptan IDs ajenos ni omisiones de filas existentes.

Las imágenes usan referencias temporales al formulario del color. Esto permite crear
color, talles e imágenes asociadas en el mismo guardado, sin un selector de otro producto.
Todas las formas se validan antes de subir archivos y guardar dentro de `atomic()`.
Una revisión firmada detecta cambios concurrentes para evitar sobrescribir inventario
modificado desde que se abrió la ficha. Ante conflicto, recargar y volver a aplicar cambios.

Los colores/talles usados en pedidos tampoco pueden renombrarse desde el panel.
Los colores sin talles se muestran con advertencia. Stock bajo se define en
`LOW_STOCK_LIMIT = 2`: de 1 a 2; stock 0 se informa aparte.

Se pueden descartar filas recién agregadas. Las filas ya guardadas se conservan;
para dejar una variante sin disponibilidad, poner stock 0.

## Archivos

Se conserva Cloudinary y sus campos actuales. La carga se difiere hasta después de validar
los formularios; imágenes hasta 10 MB, videos hasta 50 MB. Los formatos permitidos figuran
en los formularios. Cloudinary también valida/procesa el contenido recibido.

Marcar un archivo para eliminar exige la casilla de confirmación al guardar. Se quita
la relación de la base; no se destruye el original remoto.

Cloudinary no participa en las transacciones SQL. Si se sube un archivo y después falla
otra subida o escritura, la base se revierte pero el archivo remoto podría quedar sin
asociar. No se elimina automáticamente para evitar borrar material compartido.
Ante un formulario inválido hay que seleccionar de nuevo los archivos; los campos de
texto y las filas se conservan. Los videos no se añadieron al frontend público.

## Pedidos y métricas

Ventas = suma de `Orden.total` con `pagado=True` y `estado != cancelado`.
Pendientes de pago = pedidos no pagados y no cancelados. Son métricas históricas,
no una proyección mensual. El dashboard omite datos para los que el staff no tenga permiso.

Los ítems se muestran como información histórica, sin edición. Estado y pagado se guardan
con confirmación explícita desde el detalle; nunca desde el listado. Cancelar devuelve
stock, reactivar lo descuenta con validación y bloqueo de talles. Se agrupan cantidades
por talle para evitar errores si aparece más de una línea de la misma variante. La
revisión firmada protege de cambios concurrentes del estado/pago.

Finalizar envía el comprobante, siguiendo el comportamiento del admin existente. Marcar
pagado manualmente no cobra ni consulta Mercado Pago. La lógica pública de checkout y
webhook permanece intacta. El stock público conserva las limitaciones diagnosticadas en
la auditoría; esta tarea no refactoriza ese flujo.

El costo del envío en el detalle se identifica como costo actual de la opción: no existe
un snapshot separado del costo histórico. Los totales guardados no se recalculan.

## Verificación

Pruebas aisladas (no conectan ni escriben a la base real):

```bash
DATABASE_URL=sqlite:///:memory: .venv/bin/python manage.py test tienda.test_panel tienda.tests --noinput
DATABASE_URL=sqlite:///:memory: .venv/bin/python manage.py check
node --check frontend/static/js/panel.js
```

Django crea y destruye su base temporal de pruebas. Las cargas Cloudinary y los emails
se simulan en los tests. No se crean migraciones del proyecto ni se ejecutan sobre la
base real. Las verificaciones de navegador también usan una base temporal aislada.
