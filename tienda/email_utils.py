import requests
from django.conf import settings

LOGO_URL = "https://res.cloudinary.com/ddsobe4fw/image/upload/w_280,f_auto,q_auto/v1782404900/phonto_cscttz.jpg"

def _logo():
    return f'<img src="{LOGO_URL}" alt="Misso" style="max-width:140px;width:auto;height:auto;display:block;margin:0 auto 24px auto;">'

def _bloque_pago_envio(orden):
    metodo_pago = orden.metodo_pago
    envio_nombre = str(orden.envio) if orden.envio else "A confirmar"

    if metodo_pago == "transferencia":
        bloque_pago = '''
      <p style="margin:0 0 14px 0;font-size:15px;"><strong>Medio de pago:</strong> Transferencia bancaria</p>
      <div style="border:2px dashed #c0768a;border-radius:12px;padding:20px 24px;background:#fdf5f6;margin-bottom:14px;">
        <p style="margin:0 0 14px 0;font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#8b2035;font-weight:bold;">✦ Datos para transferir</p>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;color:#888;">Alias</td>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;font-weight:bold;text-align:right;">missocba</td>
          </tr>
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;color:#888;">CBU</td>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;font-weight:bold;text-align:right;">1430001713038905120013</td>
          </tr>
          <tr>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;color:#888;">Titular</td>
            <td style="padding:8px 0;border-bottom:1px solid #e8cdd4;font-size:14px;font-weight:bold;text-align:right;">Abril Bugna</td>
          </tr>
          <tr>
            <td style="padding:8px 0;font-size:14px;color:#888;">Banco</td>
            <td style="padding:8px 0;font-size:14px;font-weight:bold;text-align:right;">Brubank</td>
          </tr>
        </table>
      </div>
      <p style="margin:0;font-size:13px;color:#888;">📩 Una vez realizada la transferencia envianos el comprobante por <a href="https://wa.me/543517727224" style="color:#6b0f1a;">WhatsApp</a> o <a href="https://instagram.com/misso.cba" style="color:#6b0f1a;">Instagram</a> con el número de pedido.</p>
'''
    elif metodo_pago == "efectivo":
        bloque_pago = '''
      <p style="margin:0;font-size:15px;"><strong>Medio de pago:</strong> Efectivo — el pago se abona al momento de recibir el pedido.</p>
'''
    elif metodo_pago == "mercadopago":
        bloque_pago = '''
      <p style="margin:0;font-size:15px;"><strong>Medio de pago:</strong> MercadoPago ✅ — tu pago fue procesado correctamente.</p>
'''
    else:
        bloque_pago = f'''
      <p style="margin:0;font-size:15px;"><strong>Medio de pago:</strong> {metodo_pago}</p>
'''

    return f'''
    <div style="border:1px solid #f0d6da;padding:20px 24px;box-sizing:border-box;margin:20px 0;background:#fff8f9;border-radius:8px;">
      {bloque_pago}
      <p style="margin:14px 0 0 0;font-size:15px;"><strong>Medio de envío:</strong> {envio_nombre}</p>
    </div>'''

def _filas_items(items):
    filas = ""
    subtotal = 0
    for item in items:
        color_txt = item.color.nombre if item.color else "Sin color"
        talle_txt = item.talle.talle if item.talle else "Sin talle"
        precio_item = item.precio * item.cantidad
        subtotal += precio_item
        filas += f'''
        <tr>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;vertical-align:middle;">
            <span style="display:block;font-size:14px;">{item.cantidad}x {item.producto.nombre}</span>
            <span style="display:block;font-size:12px;color:#888;margin-top:3px;">Color: {color_txt} &nbsp;|&nbsp; Talle: {talle_txt}</span>
          </td>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;text-align:right;font-size:14px;">${precio_item:,.2f}</td>
        </tr>'''
    return filas, subtotal

def html_comprobante_cliente(orden, items):
    filas, subtotal = _filas_items(items)
    envio_costo = orden.envio.costo if orden.envio else 0

    return f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="font-family:Helvetica,Arial,sans-serif;color:#222;padding:0;margin:0;background-color:#fdf5f6;">
  <div style="max-width:600px;margin:0 auto;background:#fff;padding:36px 28px 28px 28px;">

    {_logo()}

    <h1 style="font-weight:400;font-size:26px;text-align:center;margin-bottom:4px;">¡Hola {orden.nombre}, gracias por tu compra!</h1>
    <h3 style="font-weight:400;font-size:18px;text-align:center;color:#888;margin-top:4px;">Orden #{orden.pk}</h3>

    <p style="font-size:15px;line-height:1.6;margin-top:24px;">
      Recibimos tu pedido correctamente. Nos estaremos contactando a tu número <strong>{orden.telefono}</strong> para coordinar los detalles de la venta. ♡
    </p>

    {_bloque_pago_envio(orden)}

    <h3 style="font-weight:600;font-size:15px;margin-top:28px;margin-bottom:0;">Detalle de la orden</h3>
    <div style="border:1px solid #E2E6EA;padding:4px 20px;box-sizing:border-box;margin-top:10px;">
      <table style="width:100%;" border="0" cellpadding="0" cellspacing="0">
        {filas}
        <tr>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;font-size:14px;">Subtotal</td>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;text-align:right;font-size:14px;">${subtotal:,.2f}</td>
        </tr>
        <tr>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;font-size:14px;">Envío</td>
          <td style="border-bottom:1px solid #E2E6EA;padding:14px 0;text-align:right;font-size:14px;">${envio_costo:,.2f}</td>
        </tr>
        <tr>
          <td style="padding:14px 0;font-size:15px;font-weight:bold;">Total</td>
          <td style="padding:14px 0;text-align:right;font-size:15px;font-weight:bold;">${orden.total:,.2f}</td>
        </tr>
      </table>
    </div>

    <div style="border-top:1px solid #f0d6da;margin-top:40px;padding-top:20px;text-align:center;">
      <p style="font-size:13px;color:#888;">Cualquier duda comunicate a <a href="mailto:missocba@gmail.com" style="color:#6b0f1a;">missocba@gmail.com</a> o respondé este email.</p>
      <p style="font-size:13px;color:#888;"><a href="https://misso.ar" style="color:#6b0f1a;">www.misso.ar</a></p>
    </div>

  </div>
</body>
</html>'''

def enviar_comprobante_cliente(orden):
    items = orden.itemorden_set.select_related("producto", "color", "talle").all()
    html = html_comprobante_cliente(orden, items)
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Misso <hola@misso.ar>",
            "to": [orden.email],
            "subject": f"Tu pedido #{orden.pk} fue confirmado — Misso",
            "html": html,
        },
        timeout=5,
    )

def enviar_notificacion_tienda(orden, items):
    filas = ""
    for item in items:
        color_txt = item.color.nombre if item.color else "Sin color"
        talle_txt = item.talle.talle if item.talle else "Sin talle"
        filas += f"- {item.cantidad}x {item.producto.nombre} | Color: {color_txt} | Talle: {talle_txt} | ${item.precio}\n"

    texto = (
        f"Nuevo pedido #{orden.pk}\n\n"
        f"Cliente: {orden.nombre}\n"
        f"Email: {orden.email}\n"
        f"Tel: {orden.telefono}\n"
        f"Dirección: {orden.direccion}\n\n"
        f"Productos:\n{filas}\n"
        f"Envío: {orden.envio}\n"
        f"Método de pago: {orden.metodo_pago}\n"
        f"Total: ${orden.total}\n"
    )
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Misso <hola@misso.ar>",
            "to": [settings.NOTIFICACION_EMAIL],
            "subject": f"¡Nuevo pedido #{orden.pk}!",
            "text": texto,
        },
        timeout=5,
    )
