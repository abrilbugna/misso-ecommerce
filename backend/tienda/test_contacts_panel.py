from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import NewsletterContacto, Orden


class ContactsPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser('contacts_staff', 'staff@example.test', 'test-password')
        cls.newsletter_only = get_user_model().objects.create_user('newsletter_staff', is_staff=True)
        cls.newsletter_only.user_permissions.add(Permission.objects.get(codename='view_newslettercontacto'))
        cls.orders_only = get_user_model().objects.create_user('orders_staff', is_staff=True)
        cls.orders_only.user_permissions.add(Permission.objects.get(codename='view_orden'))
        cls.unprivileged = get_user_model().objects.create_user('unprivileged_staff', is_staff=True)

        now = timezone.now()
        NewsletterContacto.objects.create(email='news@example.test', consentimiento_comercial=True, consentimiento_fecha=now)
        NewsletterContacto.objects.create(email='NEWS@example.test', consentimiento_comercial=True, consentimiento_fecha=now)
        NewsletterContacto.objects.create(email='inactive@example.test', consentimiento_comercial=True, consentimiento_fecha=now, activo=False)
        NewsletterContacto.objects.create(email='no-consent@example.test', consentimiento_comercial=False, consentimiento_fecha=now)
        Orden.objects.create(nombre='Primera compra', email='buyer@example.test', telefono='3510000000', total=100)
        Orden.objects.create(nombre='Segunda compra', email='BUYER@example.test', telefono='3511111111', total=200)
        Orden.objects.create(nombre='Otro comprador', email='other@example.test', telefono='3512222222', total=300)

    def test_newsletter_and_buyers_are_separate_and_not_duplicated(self):
        self.client.force_login(self.staff)
        newsletter = self.client.get(reverse('panel:contactos'))
        self.assertEqual(newsletter.status_code, 200)
        self.assertEqual(newsletter.context['page'].paginator.count, 3)
        self.assertContains(newsletter, 'Suscriptos a novedades')
        self.assertContains(newsletter, '<strong>news@example.test</strong>', count=1)
        self.assertContains(newsletter, 'data-copy-email="news@example.test"', count=1)
        self.assertNotContains(newsletter, 'buyer@example.test')
        self.assertNotContains(newsletter, 'Suscripciones <b>')
        self.assertContains(newsletter, 'Contactos <b>')

        buyers = self.client.get(reverse('panel:contactos'), {'tipo': 'compradores'})
        self.assertEqual(buyers.context['page'].paginator.count, 2)
        self.assertContains(buyers, 'data-copy-email="buyer@example.test"', count=1)
        self.assertContains(buyers, 'Segunda compra')
        self.assertNotContains(buyers, 'news@example.test')
        self.assertNotContains(buyers, 'Copiar todos')

    def test_copy_all_only_includes_active_consented_newsletter_once(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('panel:contactos_emails_novedades'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(len(response.json()['emails']), 1)
        self.assertEqual(response.json()['emails'][0].lower(), 'news@example.test')

    def test_search_filters_correct_section_and_preserves_buyer_order_count(self):
        self.client.force_login(self.staff)
        news = self.client.get(reverse('panel:contactos'), {'tipo': 'novedades', 'q': 'inactive'})
        self.assertEqual(news.context['page'].paginator.count, 1)
        self.assertContains(news, 'inactive@example.test')
        buyers = self.client.get(reverse('panel:contactos'), {'tipo': 'compradores', 'q': 'Primera'})
        self.assertEqual(buyers.context['page'].paginator.count, 1)
        contact = list(buyers.context['page'])[0]
        self.assertEqual(contact['pedidos'], 2)

    def test_permissions_and_monthly_subscription_route_remain_separate(self):
        list_url = reverse('panel:contactos')
        export_url = reverse('panel:contactos_emails_novedades')
        self.assertEqual(Client().get(list_url).status_code, 302)
        self.assertEqual(Client().get(export_url).status_code, 302)

        self.client.force_login(self.newsletter_only)
        self.assertEqual(self.client.get(list_url).status_code, 200)
        self.assertEqual(self.client.get(list_url, {'tipo': 'compradores'}).status_code, 403)
        self.assertNotContains(self.client.get(list_url), 'Compradores</a>')

        self.client.force_login(self.orders_only)
        self.assertEqual(self.client.get(list_url).context['contact_type'], 'compradores')
        self.assertEqual(self.client.get(list_url, {'tipo': 'novedades'}).status_code, 403)
        self.assertEqual(self.client.get(export_url).status_code, 403)

        self.client.force_login(self.unprivileged)
        self.assertEqual(self.client.get(list_url).status_code, 403)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('panel:suscripciones')).status_code, 200)
