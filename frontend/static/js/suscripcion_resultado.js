(() => {
  const result = document.querySelector('[data-status-url]');
  if (!result || result.dataset.status !== 'pendiente') return;
  let attempts = 0;
  const check = async () => {
    if (attempts++ >= 24) return;
    try {
      const response = await fetch(result.dataset.statusUrl, {cache: 'no-store'});
      if (response.ok && (await response.json()).estado !== 'pendiente') {
        window.location.reload();
        return;
      }
    } catch { /* Manual refresh remains available. */ }
    window.setTimeout(check, 5000);
  };
  window.setTimeout(check, 5000);
})();
