const csrfToken = document.currentScript.dataset.csrfToken;

function aplicarCodigo() {
    const codigo = document.getElementById('input-codigo').value.trim();
    const msg = document.getElementById('codigo-msg');
    if (!codigo) return;
    fetch('/tienda/carrito/aplicar-codigo/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ codigo })
    })
    .then(r => r.json())
    .then(data => {
        if (data.valido) {
            location.reload();
        } else {
            msg.textContent = data.mensaje;
            msg.className = 'codigo-msg error';
        }
    });
}
document.getElementById('input-codigo')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') aplicarCodigo();
});
