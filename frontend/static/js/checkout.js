const total = document.currentScript.dataset.total;

async function iniciarAutocomplete() {
    const input = document.querySelector("textarea#direccion");
    if (!input) return;

    const { PlaceAutocompleteElement } = await google.maps.importLibrary("places");
    const autocompleteEl = new PlaceAutocompleteElement({ componentRestrictions: { country: "ar" } });

    input.style.display = "none";
    input.required = false;
    autocompleteEl.style.cssText = "width: 100%;";
    input.parentNode.insertBefore(autocompleteEl, input);

    autocompleteEl.addEventListener("gmp-placeselect", async ({ place }) => {
        await place.fetchFields({ fields: ["formattedAddress"] });
        input.value = place.formattedAddress;
        input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    window._autocompleteEl = autocompleteEl;
}

function confirmarPedido() {
    const form = document.getElementById('checkout-form');
    const input = document.querySelector('textarea#direccion');
    const ac = window._autocompleteEl;

    if (!input.value.trim() && ac) {
        const valor = ac.value || '';
        if (valor.trim()) {
            input.value = valor.trim();
        } else {
            alert('Por favor ingresá tu dirección.');
            return;
        }
    }

    if (!input.value.trim()) {
        alert('Por favor ingresá tu dirección.');
        return;
    }

    form.requestSubmit();
}

window.addEventListener("load", iniciarAutocomplete);

document.addEventListener('DOMContentLoaded', function () {
    const selectEnvio = document.getElementById('id_envio');
    const spanEnvio = document.getElementById('resumen-envio-costo');
    const spanTotal = document.getElementById('resumen-total-valor');
    const divRecargo = document.getElementById('resumen-recargo-mp');
    const spanRecargo = document.getElementById('resumen-recargo-valor');
    const subtotalConDescuento = parseFloat(total.replace(',', '.'));
    const ES_CORREO = /correo\s*argentino/i;

    function filtrarPagoSegunEnvio() {
        const textoEnvioElegido = selectEnvio.options[selectEnvio.selectedIndex]?.text || '';
        const esCorreo = ES_CORREO.test(textoEnvioElegido);
        document.querySelectorAll('input[name="metodo_pago"]').forEach(radio => {
            const labelEl = radio.closest('label') || radio.parentElement;
            if (radio.value === 'efectivo') {
                radio.disabled = esCorreo;
                if (labelEl) {
                    labelEl.style.opacity = esCorreo ? '0.35' : '';
                    labelEl.style.pointerEvents = esCorreo ? 'none' : '';
                    labelEl.title = esCorreo ? 'No disponible para envíos por Correo Argentino' : '';
                }
                if (esCorreo && radio.checked) radio.checked = false;
            }
        });
    }

    function actualizarResumen() {
        const textoEnvio = selectEnvio.options[selectEnvio.selectedIndex]?.text || '';
        const matchEnvio = textoEnvio.match(/\$([\d.]+)/);
        const costoEnvio = matchEnvio ? parseFloat(matchEnvio[1]) : 0;
        spanEnvio.textContent = costoEnvio > 0 ? '$' + costoEnvio.toLocaleString('es-AR') : 'Se calcula al elegir';
        const mpSeleccionado = document.querySelector('input[name="metodo_pago"]:checked')?.value === 'mercadopago';
        const baseTotal = subtotalConDescuento + costoEnvio;
        const recargo = mpSeleccionado ? Math.round(baseTotal * 0.10 * 100) / 100 : 0;
        divRecargo.classList.toggle('visible', mpSeleccionado);
        spanRecargo.textContent = '$' + recargo.toLocaleString('es-AR');
        spanTotal.textContent = '$' + (baseTotal + recargo).toLocaleString('es-AR');
    }

    if (selectEnvio) {
        selectEnvio.addEventListener('change', function () {
            filtrarPagoSegunEnvio();
            actualizarResumen();
        });
    }

    document.querySelectorAll('input[name="metodo_pago"]').forEach(radio => {
        radio.addEventListener('change', actualizarResumen);
    });

    filtrarPagoSegunEnvio();
    actualizarResumen();

    document.getElementById('id_email').addEventListener('input', function () {
        const val = this.value;
        const esValido = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val);
        let error = document.getElementById('email-error');
        if (!error) {
            error = document.createElement('p');
            error.id = 'email-error';
            error.className = 'form-error';
            this.parentNode.appendChild(error);
        }
        error.textContent = val && !esValido ? 'Ingresá un email válido.' : '';
    });

    document.getElementById('id_telefono').addEventListener('input', function () {
        const antes = this.value;
        this.value = this.value.replace(/[^0-9+\-\s]/g, '');
        let error = document.getElementById('telefono-error');
        if (!error) {
            error = document.createElement('p');
            error.id = 'telefono-error';
            error.className = 'form-error';
            this.parentNode.appendChild(error);
        }
        error.textContent = antes !== this.value ? 'Solo se permiten números.' : '';
    });
});
