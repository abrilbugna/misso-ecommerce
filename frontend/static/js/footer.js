document.querySelectorAll('[data-newsletter-form]').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector('button[type="submit"]');
    const message = form.querySelector('[data-newsletter-message]');
    const formData = new FormData(form, event.submitter || button);
    button.disabled = true;
    message.textContent = '';
    delete message.dataset.error;
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      const data = await response.json();
      message.textContent = data.message || 'No pudimos procesar tu solicitud.';
      if (response.ok && data.ok) form.reset();
      else message.dataset.error = 'true';
    } catch {
      message.textContent = 'No pudimos conectarnos. Probá de nuevo más tarde.';
      message.dataset.error = 'true';
    } finally {
      button.disabled = false;
    }
  });
});
