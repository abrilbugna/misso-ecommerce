"""No real MP requests, plans, charges or emails: every transport is mocked."""
import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Suscripcion, PagoSuscripcion, EventoMercadoPago, EmailSuscripcion
from .subscription_api import MPSubscriptionError, SubscriptionAPI
from .subscription_services import process_event, sync_subscription, start_checkout, store_invoice
from .subscription_emails import send_welcome
from .subscription_forms import PREGUNTAS


@override_settings(MP_SUBSCRIPTION_ENABLED=True, MP_SUBSCRIPTION_AMOUNT=Decimal('25000'), MP_SUBSCRIPTION_CURRENCY='ARS',
                   MP_SUBSCRIPTION_MODE='test', MP_SUBSCRIPTION_TEST_ACCESS_TOKEN='test-credential', PUBLIC_BASE_URL='https://misso.ar',
                   MP_SUBSCRIPTION_PLAN_ID='', MP_WEBHOOK_SECRET='secret-for-tests', SITE_URL='https://misso.ar',
                   MISSO_ADMIN_EMAIL='staff@example.test', RESEND_API_KEY='fake', MERCADOPAGO_ACCESS_TOKEN='fake',
                   ALLOWED_HOSTS=['testserver'])
class SubscriptionTests(TestCase):
    def setUp(self):
        self.api_patch = patch('tienda.subscription_services.SubscriptionAPI')
        self.api = self.api_patch.start().return_value
        self.addCleanup(self.api_patch.stop)
        self.transport = patch('requests.sessions.Session.request', side_effect=AssertionError('Unmocked network call'))
        self.transport.start()
        self.addCleanup(self.transport.stop)
        self.form_url = reverse('comenzar_suscripcion')
        self.api.search_subscription.return_value = {'results': []}
        self.api.create_pending.side_effect = lambda sub: self.remote(sub)
        self.send_patch = patch('tienda.subscription_emails.requests.post')
        self.send = self.send_patch.start()
        self.addCleanup(self.send_patch.stop)
        self.send.return_value = Mock(status_code=200, json=lambda: {'id': 'email-id'})

    def form_data(self, **overrides):
        response = self.client.get(self.form_url)
        data = {'nombre': 'Abril Prueba', 'email': 'abril@example.test', 'telefono': '+54 351 1234567',
                'destino': 'mismo', 'talle': '90', 'tipo_prenda': 'conjuntos', 'estilo': 'detalles',
                'color_preferido': 'Negro', 'color_evitar': 'Verde', 'carta': '', 'comentarios': 'Sin aros <script>test</script>',
                'terminos_aceptados': 'on', 'submission_token': response.context['form']['submission_token'].value()}
        return {**data, **overrides}

    def intention(self):
        response = self.client.post(self.form_url, self.form_data())
        self.assertEqual(response.status_code, 302)
        return Suscripcion.objects.get()

    def remote(self, sub, status='pending', **extra):
        return {'id': 'mp-sub-1', 'external_reference': sub.external_reference, 'status': status,
                'init_point': 'https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=mp-sub-1',
                'auto_recurring': {'transaction_amount': 25000, 'currency_id': 'ARS', 'frequency': 1, 'frequency_type': 'months'},
                'last_modified': timezone.now().isoformat(), **extra}

    def notify(self, identifier='mp-sub-1', topic='subscription_preapproval', event_id='event-1', valid=True, **extra):
        stamp = '1704908010'
        manifest = f'id:{identifier.lower()};request-id:req-test;ts:{stamp};'
        signature = hmac.new(b'secret-for-tests', manifest.encode(), hashlib.sha256).hexdigest()
        body = {'id': event_id, 'type': topic, 'action': topic+'.updated', 'data': {'id': identifier}, **extra}
        return self.client.post(reverse('suscripciones_webhook')+'?data.id='+identifier,
            json.dumps(body), content_type='application/json', HTTP_X_REQUEST_ID='req-test',
            HTTP_X_SIGNATURE=f'ts={stamp},v1={signature if valid else "bad"}')

    def activate(self, sub):
        self.api.get_subscription.return_value = self.remote(sub, 'authorized')
        self.notify()
        process_event(EventoMercadoPago.objects.get().pk)
        sub.refresh_from_db()

    def invoice(self, **extra):
        return {'id': 101, 'preapproval_id': 'mp-sub-1', 'currency_id': 'ARS', 'transaction_amount': 25000,
                'status': 'processed', 'last_modified': timezone.now().isoformat(), 'debit_date': timezone.now().isoformat(),
                'payment': {'id': 501, 'status': 'approved'}, **extra}

    def payment(self, **extra):
        return {'id': 501, 'status': 'approved', 'currency_id': 'ARS', 'transaction_amount': 25000,
                'date_last_updated': timezone.now().isoformat(), **extra}

    def test_invalid_form(self):
        response = self.client.post(self.form_url, self.form_data(talle='', email='invalid'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Suscripcion.objects.exists())
        self.api.create_pending.assert_not_called()

    def test_terms_required(self):
        self.assertEqual(self.client.post(self.form_url, self.form_data(terminos_aceptados='')).status_code, 400)
        self.assertFalse(Suscripcion.objects.exists())

    def test_pending_redirect_snapshot_and_terms(self):
        sub = self.intention()
        self.assertEqual(sub.estado, 'pendiente')
        self.assertEqual(sub.mp_preapproval_id, 'mp-sub-1')
        self.assertTrue(sub.terminos_aceptados)
        self.assertIsNotNone(sub.terminos_aceptados_at)
        self.assertEqual(sub.terminos_url, 'https://misso.ar/suscripcion/#terminos')
        self.assertTrue(sub.external_reference.startswith('MISSO-SUB-'))
        self.assertEqual({r['campo'] for r in sub.respuestas}, {*PREGUNTAS, 'nombre', 'email', 'telefono'})
        self.assertEqual(sub.respuestas[0]['respuesta'], 'Para mí')
        self.assertFalse(EmailSuscripcion.objects.exists())
        self.send.assert_not_called()

    def test_double_submit_reuses_local_and_remote(self):
        data = self.form_data()
        first = self.client.post(self.form_url, data)
        second = self.client.post(self.form_url, data)
        self.assertEqual(first.url, second.url)
        self.assertEqual(Suscripcion.objects.count(), 1)
        self.api.create_pending.assert_called_once()

    def test_submission_token_is_bound_to_session(self):
        data = self.form_data()
        self.client.cookies.clear()
        self.assertEqual(self.client.post(self.form_url, data).status_code, 400)
        self.assertFalse(Suscripcion.objects.exists())

    def test_checkout_failure_preserves_answers_and_retry(self):
        self.api.create_pending.side_effect = MPSubscriptionError('mp_http_400')
        data = self.form_data()
        response = self.client.post(self.form_url, data)
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'No pudimos iniciar el pago', status_code=503)
        sub = Suscripcion.objects.get()
        self.assertEqual(sub.estado, 'pendiente')
        self.assertEqual(sub.respuestas[3]['valor'], 'Negro')
        self.api.create_pending.side_effect = lambda sub: self.remote(sub)
        self.assertEqual(self.client.post(self.form_url, data).status_code, 302)
        self.assertEqual(Suscripcion.objects.count(), 1)

    def test_ambiguous_timeout_never_reposts(self):
        self.api.create_pending.side_effect = MPSubscriptionError('mp_transport_error', uncertain=True)
        data = self.form_data()
        self.client.post(self.form_url, data)
        sub = Suscripcion.objects.get()
        self.assertEqual(sub.checkout_estado, 'uncertain')
        self.client.post(self.form_url, data)
        self.api.create_pending.assert_called_once()
        self.api.search_subscription.return_value = {'results': [self.remote(sub)]}
        response = self.client.post(self.form_url, data)
        self.assertIn('mercadopago.com.ar/subscriptions/checkout', response.url)
        self.api.create_pending.assert_called_once()

    def test_invalid_signature_and_mismatched_signed_id(self):
        self.assertEqual(self.notify(valid=False).status_code, 401)
        self.assertEqual(self.notify(data={'id': 'different'}).status_code, 400)
        self.assertFalse(EventoMercadoPago.objects.exists())

    def test_signature_missing_is_rejected(self):
        response = self.client.post(reverse('suscripciones_webhook')+'?data.id=1',
            {'type': 'payment', 'data': {'id': '1'}}, content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_valid_webhook_durable_and_duplicate(self):
        sub = self.intention()
        self.api.get_subscription.return_value = self.remote(sub, 'authorized')
        self.assertEqual(self.notify().status_code, 200)
        self.assertEqual(self.notify().status_code, 200)
        self.assertEqual(EventoMercadoPago.objects.count(), 1)
        self.api.get_subscription.assert_not_called()  # verification belongs to worker
        process_event(EventoMercadoPago.objects.get().pk)
        sub.refresh_from_db()
        self.assertEqual(sub.estado, 'activa')
        self.assertEqual(EmailSuscripcion.objects.count(), 2)

    def test_authorized_only_sends_two_welcome_emails_once(self):
        sub = self.intention()
        self.activate(sub)
        for item in sub.emails.all():
            send_welcome(item.pk)
            send_welcome(item.pk)
        self.notify(event_id='new-delivery')
        for event in EventoMercadoPago.objects.all():
            process_event(event.pk)
        for item in sub.emails.all():
            send_welcome(item.pk)
        self.assertEqual(self.send.call_count, 2)
        sub.refresh_from_db()
        self.assertIsNotNone(sub.confirmation_email_sent_at)
        self.assertIsNotNone(sub.admin_email_sent_at)
        customer = sub.emails.get(tipo='cliente').payload
        admin = sub.emails.get(tipo='admin').payload
        self.assertEqual(customer['to'], ['abril@example.test'])
        self.assertEqual(admin['to'], ['staff@example.test'])
        self.assertIn('https://misso.ar/suscripcion/#terminos', customer['html'])
        self.assertIn(f'https://misso.ar/panel/suscripciones/{sub.pk}/', admin['html'])
        self.assertNotIn('mp-sub-1', customer['html'])
        for label in PREGUNTAS.values():
            self.assertIn(label, customer['html'])
        self.assertIn('&lt;script&gt;', customer['html'])
        self.assertNotIn('<script>', customer['html'])

    def test_email_failure_does_not_change_active_and_retries_only_failed(self):
        sub = self.intention()
        self.activate(sub)
        self.send.side_effect = [Mock(status_code=200, json=lambda: {'id': 'client-ok'}), Mock(status_code=503), Mock(status_code=200, json=lambda: {'id': 'admin-ok'})]
        customer = sub.emails.get(tipo='cliente')
        admin = sub.emails.get(tipo='admin')
        send_welcome(customer.pk)
        send_welcome(admin.pk)
        sub.refresh_from_db()
        self.assertEqual(sub.estado, 'activa')
        self.assertIsNone(sub.admin_email_sent_at)
        send_welcome(customer.pk)
        send_welcome(admin.pk)
        self.assertEqual(self.send.call_count, 3)
        keys = [c.kwargs['headers']['Idempotency-Key'] for c in self.send.call_args_list]
        self.assertEqual(keys[1], keys[2])

    def test_ambiguous_email_after_provider_window_requires_review(self):
        sub = self.intention(); self.activate(sub)
        email = sub.emails.get(tipo='cliente')
        EmailSuscripcion.objects.filter(pk=email.pk).update(primer_intento_at=timezone.now()-timedelta(hours=25))
        send_welcome(email.pk)
        self.send.assert_not_called()
        email.refresh_from_db()
        self.assertTrue(email.revision_manual)

    def test_pending_never_emails(self):
        sub = self.intention()
        self.api.get_subscription.return_value = self.remote(sub)
        sync_subscription('mp-sub-1')
        self.assertFalse(EmailSuscripcion.objects.exists())

    def test_pause_cancel_reactivate_no_new_welcome(self):
        sub = self.intention(); self.activate(sub)
        first_date = sub.autorizado_at
        for remote, local in [('paused','pausada'), ('cancelled','cancelada'), ('authorized','activa')]:
            self.api.get_subscription.return_value = self.remote(sub, remote)
            sync_subscription('mp-sub-1')
            sub.refresh_from_db()
            self.assertEqual(sub.estado, local)
        self.assertIsNotNone(sub.cancelado_at)
        self.assertEqual(sub.autorizado_at, first_date)
        self.assertEqual(EmailSuscripcion.objects.count(), 2)

    def test_mismatched_amount_or_currency_cannot_activate(self):
        sub = self.intention()
        data = self.remote(sub, 'authorized')
        data['auto_recurring']['transaction_amount'] = 1
        self.api.get_subscription.return_value = data
        self.notify()
        event = EventoMercadoPago.objects.get()
        process_event(event.pk)
        event.refresh_from_db();sub.refresh_from_db()
        self.assertEqual(sub.estado, 'pendiente')
        self.assertIsNone(event.procesado_at)
        self.assertEqual(event.error, 'subscription_terms_mismatch')
        self.assertFalse(EmailSuscripcion.objects.exists())

    def test_invoice_new_and_duplicate_payment_topics_merge(self):
        sub = self.intention()
        self.api.get_subscription.return_value = self.remote(sub, 'authorized')
        self.api.get_invoice.return_value = self.invoice()
        self.api.get_payment.return_value = self.payment()
        self.api.invoices_for_payment.return_value = {'results': [self.invoice()]}
        self.notify(identifier='101', topic='subscription_authorized_payment')
        self.notify(identifier='101', topic='subscription_authorized_payment')
        self.notify(identifier='501', topic='payment', event_id='event-2')
        for event in EventoMercadoPago.objects.all():
            process_event(event.pk)
        self.assertEqual(PagoSuscripcion.objects.count(), 1)
        payment = PagoSuscripcion.objects.get()
        self.assertEqual(payment.mp_payment_id, '501')
        self.assertEqual(payment.mp_authorized_payment_id, '101')
        self.assertEqual(payment.estado, 'approved')
        self.assertEqual(EmailSuscripcion.objects.count(), 2)

    def test_invoice_before_payment_then_refund(self):
        sub = self.intention()
        self.api.get_subscription.return_value = self.remote(sub, 'authorized')
        store_invoice(self.invoice(payment={}))
        self.api.get_payment.return_value = self.payment()
        store_invoice(self.invoice())
        self.assertEqual(PagoSuscripcion.objects.count(), 1)
        self.api.get_payment.return_value = self.payment(status='refunded')
        store_invoice(self.invoice())
        self.assertEqual(PagoSuscripcion.objects.get().estado, 'refunded')

    def test_other_order_payment_is_not_subscription(self):
        self.api.get_payment.return_value = self.payment(external_reference='42')
        self.api.invoices_for_payment.return_value = {'results': []}
        self.notify(identifier='501', topic='payment')
        process_event(EventoMercadoPago.objects.get().pk)
        self.assertFalse(PagoSuscripcion.objects.exists())
        self.assertFalse(Suscripcion.objects.exists())

    def test_api_failure_is_retriable_event(self):
        self.api.get_subscription.side_effect = MPSubscriptionError('mp_http_503')
        self.notify()
        event = EventoMercadoPago.objects.get()
        process_event(event.pk);event.refresh_from_db()
        self.assertIsNone(event.procesado_at)
        self.assertEqual(event.intentos, 1)
        self.assertIsNotNone(event.proximo_intento_at)

    def test_out_of_order_snapshot_does_not_revert_active(self):
        sub = self.intention();self.activate(sub)
        self.api.get_subscription.return_value = self.remote(sub, 'pending', last_modified=(timezone.now()-timedelta(days=1)).isoformat())
        sync_subscription('mp-sub-1');sub.refresh_from_db()
        self.assertEqual(sub.estado, 'activa')

    def test_return_ignores_success_query_and_does_not_call_mp(self):
        sub = self.intention()
        url = reverse('suscripcion_resultado', args=[sub.referencia_publica])
        response = self.client.get(url+'?status=authorized&collection_status=approved')
        self.assertContains(response, 'Estamos confirmando')
        sub.refresh_from_db();self.assertEqual(sub.estado, 'pendiente')
        self.api.get_subscription.assert_not_called()
        for status, text in [('activa','está'), ('pausada','pausada'), ('cancelada','cancelada'), ('error','No pudimos confirmar')]:
            sub.estado=status;sub.save()
            self.assertContains(self.client.get(url), text)
        self.assertFalse(EmailSuscripcion.objects.exists())

    def test_return_uuid_and_public_status_only(self):
        sub = self.intention()
        response = self.client.get(reverse('suscripcion_estado', args=[sub.referencia_publica]))
        self.assertEqual(response.json(), {'estado':'pendiente'})
        self.assertEqual(self.client.get(reverse('suscripcion_resultado', args=[uuid.uuid4()])).status_code, 404)

    def test_staff_permission_required_for_both_panel_pages(self):
        sub = self.intention()
        urls = [reverse('panel:suscripciones'), reverse('panel:suscripcion_detalle', args=[sub.pk])]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        user = get_user_model().objects.create_user(username='regular', password='test')
        self.client.force_login(user)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        user.is_staff = True;user.save()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename='view_suscripcion'))
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)
        detail = self.client.get(urls[1])
        for label in PREGUNTAS.values():
            self.assertContains(detail, label)
        self.assertContains(detail, '&lt;script&gt;')
        self.assertContains(self.client.get(urls[0]+'?q='+sub.external_reference), sub.nombre)
        self.assertNotContains(self.client.get(urls[0]+'?estado=activa'), sub.nombre)

    def test_existing_preference_questions_and_gift(self):
        data = self.form_data(destino='regalo',tipo_prenda='',estilo='',carta='Feliz cumple ♡')
        response = self.client.post(self.form_url, data)
        self.assertEqual(response.status_code, 302)
        sub=Suscripcion.objects.get()
        self.assertEqual(next(r for r in sub.respuestas if r['campo']=='carta')['valor'], 'Feliz cumple ♡')

    def test_malicious_init_point_is_not_redirected(self):
        self.api.create_pending.side_effect=lambda sub:self.remote(sub, init_point='https://evil.example/steal')
        self.assertEqual(self.client.post(self.form_url,self.form_data()).status_code, 503)
        self.assertEqual(Suscripcion.objects.get().checkout_estado, 'uncertain')

    def test_disabled_preserves_valid_intention_without_remote_request(self):
        with override_settings(MP_SUBSCRIPTION_ENABLED=False):
            self.assertEqual(self.client.post(self.form_url,self.form_data()).status_code,503)
        self.api.create_pending.assert_not_called()
        self.assertEqual(Suscripcion.objects.get().estado,'pendiente')

    def test_worker_drains_inbox_and_outbox(self):
        sub=self.intention();self.api.get_subscription.return_value=self.remote(sub,'authorized')
        self.notify()
        call_command('process_subscriptions', verbosity=0)
        sub.refresh_from_db()
        self.assertEqual(sub.estado,'activa')
        self.assertEqual(self.send.call_count,2)

    def test_hosted_api_payload_is_recurrent_not_checkout_pro(self):
        sub=self.intention()
        with patch.object(SubscriptionAPI,'request',return_value=self.remote(sub)) as request:
            SubscriptionAPI().create_pending(sub)
        self.assertEqual(request.call_args.args,('POST','/preapproval'))
        payload=request.call_args.kwargs['payload']
        self.assertEqual(payload['status'],'pending')
        self.assertEqual(payload['auto_recurring']['frequency_type'],'months')
        self.assertEqual(payload['external_reference'],sub.external_reference)
        self.assertNotIn('card_token_id',payload)
        self.assertNotIn('preapproval_plan_id',payload)
        self.assertNotIn('items',payload)
        self.assertTrue(payload['back_url'].startswith('https://misso.ar/suscripcion/resultado/'))

    def test_associated_plan_is_not_silently_mixed_with_pending_flow(self):
        sub=self.intention()
        with override_settings(MP_SUBSCRIPTION_PLAN_ID='plan-id'), self.assertRaises(MPSubscriptionError):
            SubscriptionAPI().create_pending(sub)

    def test_historical_payment_does_not_replace_latest_invoice_payment(self):
        sub=self.intention()
        self.api.get_subscription.return_value=self.remote(sub,'authorized')
        self.api.get_payment.return_value=self.payment(id=502)
        store_invoice(self.invoice(payment={'id':502}))
        store_invoice(self.invoice(payment={'id':502}), payment_override=self.payment(id=501,status='rejected'))
        self.assertEqual(PagoSuscripcion.objects.count(),2)
        self.assertEqual(PagoSuscripcion.objects.get(mp_authorized_payment_id='101').mp_payment_id,'502')
        self.assertIsNone(PagoSuscripcion.objects.get(mp_payment_id='501').mp_authorized_payment_id)

    def test_remote_created_with_missing_identifier_is_not_recreated(self):
        self.api.create_pending.side_effect=lambda sub:self.remote(sub,id=None)
        data=self.form_data()
        self.assertEqual(self.client.post(self.form_url,data).status_code,503)
        sub=Suscripcion.objects.get()
        self.assertEqual(sub.checkout_estado,'uncertain')
        self.client.post(self.form_url,data)
        self.api.create_pending.assert_called_once()

    def test_csrf_required_for_public_form(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.form_url,self.form_data()).status_code,403)
        self.assertFalse(Suscripcion.objects.exists())

    def test_shared_price_context_changes_without_remote_writes(self):
        with override_settings(MP_SUBSCRIPTION_AMOUNT=Decimal('31000')):
            response=self.client.get(reverse('informacion_suscripcion'))
            self.assertContains(response,'$31.000')
            self.assertNotContains(response,'$25.000')
            self.assertContains(self.client.get(self.form_url),'31000')
        self.api.create_pending.assert_not_called()

    def test_admin_subscription_state_is_read_only(self):
        sub=self.intention()
        user=get_user_model().objects.create_superuser(username='admin',password='test',email='admin@example.test')
        self.client.force_login(user)
        url=reverse('admin:tienda_suscripcion_change',args=[sub.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'estado':'activa'}).status_code,403)
        sub.refresh_from_db();self.assertEqual(sub.estado,'pendiente')

    def test_payment_invoice_mismatch_does_not_activate(self):
        sub=self.intention()
        self.api.get_subscription.return_value=self.remote(sub,'authorized')
        self.api.get_invoice.return_value=self.invoice(id=999)
        self.notify(identifier='101',topic='subscription_authorized_payment')
        event=EventoMercadoPago.objects.get();process_event(event.pk)
        sub.refresh_from_db();self.assertEqual(sub.estado,'pendiente')
        self.assertFalse(PagoSuscripcion.objects.exists())

    def test_worker_crash_recovery_finds_existing_remote_checkout(self):
        sub=self.intention()
        Suscripcion.objects.filter(pk=sub.pk).update(mp_preapproval_id=None,init_point='',checkout_estado='creating',checkout_intentado_at=timezone.now()-timedelta(minutes=5))
        self.api.search_subscription.return_value={'results':[self.remote(sub)]}
        call_command('process_subscriptions',verbosity=0)
        sub.refresh_from_db()
        self.assertEqual(sub.mp_preapproval_id,'mp-sub-1')
        self.assertEqual(sub.estado,'pendiente')
        self.api.create_pending.assert_called_once()  # only the fixture's original creation

    def test_api_adapter_does_not_leak_remote_error_body(self):
        with patch('tienda.subscription_api.requests.request',return_value=Mock(status_code=503,text='secret-token')):
            with self.assertRaises(MPSubscriptionError) as error:
                SubscriptionAPI().request('POST','/preapproval',payload={})
        self.assertEqual(str(error.exception),'mp_http_503')
        self.assertTrue(error.exception.uncertain)

    def test_signed_uppercase_resource_id_is_normalized(self):
        self.assertEqual(self.notify(identifier='ABC123').status_code,200)
        self.assertEqual(EventoMercadoPago.objects.get().recurso_id,'abc123')

    def test_unknown_mp_status_is_error_not_active(self):
        sub=self.intention()
        self.api.get_subscription.return_value=self.remote(sub,'unrecognized')
        sync_subscription('mp-sub-1')
        sub.refresh_from_db()
        self.assertEqual(sub.estado,'error')
        self.assertFalse(EmailSuscripcion.objects.exists())

    def test_deliberate_new_form_after_active_can_start_gift(self):
        first=self.intention();self.activate(first)
        self.api.create_pending.side_effect=lambda sub:self.remote(sub,id='mp-sub-2',init_point='https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_id=mp-sub-2')
        response=self.client.post(self.form_url,self.form_data(destino='regalo',carta='Un regalo'))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Suscripcion.objects.count(),2)
        self.assertEqual(Suscripcion.objects.get(mp_preapproval_id='mp-sub-2').estado,'pendiente')

    def test_checkout_without_webhook_or_email_configuration_redirects(self):
        with override_settings(MP_WEBHOOK_SECRET='', MISSO_ADMIN_EMAIL='', RESEND_API_KEY=''):
            response = self.client.post(self.form_url, self.form_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, Suscripcion.objects.get().init_point)
        self.assertEqual(Suscripcion.objects.get().estado, 'pendiente')

    def test_real_adapter_success_redirect_and_double_submit(self):
        self.api_patch.stop()
        def created(method, url, **kwargs):
            sub = Suscripcion.objects.get()
            self.assertEqual(url, 'https://api.mercadopago.com/preapproval')
            payload = kwargs['json']
            self.assertEqual(payload['payer_email'], sub.email)
            self.assertEqual(payload['external_reference'], sub.external_reference)
            self.assertTrue(sub.external_reference.startswith('MISSO-SUB-'))
            self.assertEqual(payload['auto_recurring'], {'frequency': 1, 'frequency_type': 'months',
                'transaction_amount': 25000.0, 'currency_id': 'ARS'})
            self.assertEqual(payload['back_url'], 'https://dev.example.test' + reverse('suscripcion_resultado', kwargs={'referencia': sub.referencia_publica}))
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-credential')
            return Mock(status_code=201, json=lambda: self.remote(sub))
        with override_settings(PUBLIC_BASE_URL='https://dev.example.test'), patch('tienda.subscription_api.requests.request', side_effect=created) as transport:
            data = self.form_data()
            response = self.client.post(self.form_url, data)
            again = self.client.post(self.form_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, Suscripcion.objects.get().init_point)
        self.assertEqual(again.url, response.url)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(Suscripcion.objects.count(), 1)

    def test_http_errors_logged_and_answers_preserved(self):
        self.api_patch.stop()
        data = self.form_data()
        for status in (400, 401, 500):
            with self.subTest(status=status), patch('tienda.subscription_api.requests.request', return_value=Mock(
                    status_code=status, json=lambda: {'error':'bad_request', 'message':'Invalid payer_email test@example.test token=test-credential'},
                    headers={'x-request-id':'req-123'})), self.assertLogs('tienda.subscription_api', level='WARNING') as logs:
                response = self.client.post(self.form_url, data)
            self.assertEqual(response.status_code, 503)
            sub = Suscripcion.objects.get()
            self.assertTrue(sub.respuestas_snapshot)
            self.assertTrue(sub.terminos_aceptados)
            self.assertEqual(sub.ultimo_error, f'mp_http_{status}')
            output = ' '.join(logs.output)
            self.assertIn(f'status={status}', output)
            self.assertIn('req-123', output)
            self.assertNotIn('test-credential', output)
            self.assertNotIn('test@example.test', output)

    def test_missing_test_token_never_falls_back_to_normal_payments(self):
        self.api_patch.stop()
        with override_settings(MP_SUBSCRIPTION_TEST_ACCESS_TOKEN='', MERCADOPAGO_ACCESS_TOKEN='existing-normal-token'), patch('tienda.subscription_api.requests.request') as transport:
            response = self.client.post(self.form_url, self.form_data())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Suscripcion.objects.get().ultimo_error, 'missing_test_access_token')
        transport.assert_not_called()

    def test_missing_init_point_is_uncertain_and_never_reposted(self):
        self.api.create_pending.side_effect = lambda sub: self.remote(sub, init_point=None)
        data = self.form_data()
        self.assertEqual(self.client.post(self.form_url, data).status_code, 503)
        self.client.post(self.form_url, data)
        self.assertEqual(self.api.create_pending.call_count, 1)
        self.assertEqual(Suscripcion.objects.get().checkout_estado, 'uncertain')

    def test_public_base_requires_explicit_https_test_origin(self):
        from .subscription_api import public_base
        for base in ('', 'http://127.0.0.1:8000', 'https://localhost', 'https://127.0.0.1', 'https://dev.example/path'):
            with self.subTest(base=base), override_settings(PUBLIC_BASE_URL=base), self.assertRaises(MPSubscriptionError):
                public_base()

    def test_configuration_checks_do_not_require_network(self):
        from .subscription_checks import subscription_configuration
        with override_settings(MP_SUBSCRIPTION_TEST_ACCESS_TOKEN='', PUBLIC_BASE_URL='', MP_WEBHOOK_SECRET=''):
            self.assertEqual({w.id for w in subscription_configuration(None)}, {'tienda.W101','tienda.W102','tienda.W103'})
