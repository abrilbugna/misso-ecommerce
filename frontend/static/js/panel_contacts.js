(() => {
  const feedback = document.querySelector('[data-copy-feedback]');
  if (!feedback) return;

  async function copyText(value) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const input = document.createElement('textarea');
    input.value = value;
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.select();
    const copied = document.execCommand('copy');
    input.remove();
    if (!copied) throw new Error('Clipboard unavailable');
  }

  document.addEventListener('click', async event => {
    const one = event.target.closest('[data-copy-email]');
    const all = event.target.closest('[data-copy-all-url]');
    const button = one || all;
    if (!button) return;
    button.disabled = true;
    try {
      if (one) {
        await copyText(one.dataset.copyEmail);
        feedback.textContent = 'Email copiado.';
      } else {
        const response = await fetch(all.dataset.copyAllUrl, {credentials: 'same-origin', cache: 'no-store'});
        if (!response.ok) throw new Error('Could not load contacts');
        const {emails} = await response.json();
        if (!emails.length) {
          feedback.textContent = 'No hay suscriptos activos con consentimiento vigente.';
          return;
        }
        await copyText(emails.join(', '));
        feedback.textContent = `${emails.length} email${emails.length === 1 ? '' : 's'} copiado${emails.length === 1 ? '' : 's'}.`;
      }
    } catch (_) {
      feedback.textContent = 'No se pudo copiar. Probá de nuevo desde un navegador seguro.';
    } finally {
      button.disabled = false;
    }
  });
})();
