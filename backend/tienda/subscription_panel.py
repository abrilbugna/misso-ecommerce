from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from .models import Suscripcion
from .panel_access import panel_required
from .panel_views import page_context
from .subscription_forms import SuscripcionFilterForm


@panel_required('tienda.view_suscripcion')
def listado(request):
    form = SuscripcionFilterForm(request.GET)
    subs = Suscripcion.objects.all()
    if form.is_valid():
        data = form.cleaned_data
        if data['q']:
            query = Q()
            for field in ('nombre', 'email', 'telefono', 'external_reference', 'mp_preapproval_id'):
                query |= Q(**{f'{field}__icontains': data['q']})
            if data['q'].isdigit():
                query |= Q(pk=int(data['q']))
            subs = subs.filter(query)
        if data['estado']:
            subs = subs.filter(estado=data['estado'])
        if data['desde']:
            subs = subs.filter(creado__date__gte=data['desde'])
        if data['hasta']:
            subs = subs.filter(creado__date__lte=data['hasta'])
    else:
        subs = subs.none()
    return render(request, 'panel/suscripciones.html', {
        **page_context(request, subs), 'filter_form': form, 'section': 'suscripciones'})


@panel_required('tienda.view_suscripcion')
def detalle(request, pk):
    sub = get_object_or_404(Suscripcion.objects.prefetch_related('pagos', 'emails', 'eventos'), pk=pk)
    return render(request, 'panel/suscripcion_detalle.html', {'sub': sub, 'section': 'suscripciones'})
