"""Read-only contacts for the MISSO panel; monthly subscriptions stay separate."""

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.db.models.functions import Lower, Trim
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import NewsletterContacto, Orden
from .panel_access import panel_required
from .panel_views import page_context


@panel_required()
@require_GET
def contactos(request):
    can_newsletter = request.user.has_perm('tienda.view_newslettercontacto')
    can_buyers = request.user.has_perm('tienda.view_orden')
    if not (can_newsletter or can_buyers):
        raise PermissionDenied

    section = request.GET.get('tipo') or ('novedades' if can_newsletter else 'compradores')
    if section not in ('novedades', 'compradores'):
        raise PermissionDenied
    if (section == 'novedades' and not can_newsletter) or (section == 'compradores' and not can_buyers):
        raise PermissionDenied

    search = request.GET.get('q', '').strip()[:254]
    if section == 'novedades':
        contacts = NewsletterContacto.objects.annotate(email_key=Lower(Trim('email')))
        if search:
            contacts = contacts.filter(email__icontains=search)
        contacts = contacts.values('email_key').annotate(
            creado=Min('creado'),
            consentimiento_fecha=Max('consentimiento_fecha', filter=Q(activo=True, consentimiento_comercial=True)),
            vigentes=Count('pk', filter=Q(activo=True, consentimiento_comercial=True)),
        ).order_by('-creado', 'email_key')
    else:
        orders = Orden.objects.exclude(email='').annotate(email_key=Lower(Trim('email')))
        if search:
            matching = orders.filter(
                Q(email__icontains=search) | Q(nombre__icontains=search) | Q(telefono__icontains=search)
            ).values('email_key')
            orders = orders.filter(email_key__in=Subquery(matching))
        latest = Orden.objects.annotate(email_key=Lower(Trim('email'))).filter(
            email_key=OuterRef('email_key')
        ).order_by('-creado', '-pk')
        contacts = orders.values('email_key').annotate(
            pedidos=Count('pk'),
            ultima_compra=Max('creado'),
            nombre=Subquery(latest.values('nombre')[:1]),
            telefono=Subquery(latest.values('telefono')[:1]),
        ).order_by('-ultima_compra', 'email_key')

    return render(request, 'panel/contactos.html', {
        **page_context(request, contacts),
        'section': 'contactos', 'contact_type': section, 'search': search,
        'can_newsletter': can_newsletter, 'can_buyers': can_buyers,
    })


@panel_required('tienda.view_newslettercontacto')
@require_GET
def emails_novedades(request):
    emails = NewsletterContacto.objects.filter(
        activo=True, consentimiento_comercial=True,
    ).values_list('email', flat=True).order_by('email')
    # The field is unique, but old/manual data can differ only in letter case.
    unique = {email.strip().casefold(): email.strip() for email in emails if email.strip()}
    response = JsonResponse({'emails': list(unique.values())})
    response['Cache-Control'] = 'no-store'
    return response
