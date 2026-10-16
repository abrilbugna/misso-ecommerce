(() => {
  const button = document.querySelector('[data-copy-tracking]');
  const code = document.getElementById('tracking-code');
  const status = document.querySelector('[data-copy-status]');
  if (!button || !code || !status) return;
  button.hidden = false;
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      status.textContent = 'Código copiado ♡';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = 'No pudimos copiarlo. El código quedó seleccionado para que lo copies manualmente.';
    }
  });
})();
