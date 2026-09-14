(() => {
  const init = () => {
    const nav = document.querySelector('.home-page .site-bubble-nav')
      || document.querySelector('body > .site-bubble-nav');
    if (!nav || document.querySelector('.campaign-hero')) return;

    nav.querySelector('.shop-brand-shimmer')?.classList.add('is-shimmering');

    if (document.querySelector('.catalog-page') && window.gsap) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

    nav.querySelectorAll('.hero-social').forEach((button, index) => {
      const bubble = button.querySelector('.hero-social-bubble');
      const icon = bubble?.querySelector('svg');
      if (!bubble || !icon) return;

      const reset = () => {
        bubble.style.transform = '';
        icon.style.transform = '';
      };
      const enter = () => {
        bubble.style.transform = `translateY(-2px) rotate(${index ? 5 : -5}deg) scale(1.06)`;
        icon.style.transform = `rotate(${index ? 5 : -6}deg)`;
      };
      button.addEventListener('pointerenter', enter);
      button.addEventListener('focusin', enter);
      button.addEventListener('pointermove', event => {
        const rect = button.getBoundingClientRect();
        const x = Math.max(-3, Math.min(3, (event.clientX - rect.left - rect.width / 2) * .12));
        const y = Math.max(-3, Math.min(3, (event.clientY - rect.top - rect.height / 2) * .12));
        icon.style.transform = `translate(${x}px, ${y}px) rotate(${index ? 5 : -6}deg)`;
      });
      button.addEventListener('pointerleave', reset);
      button.addEventListener('focusout', reset);
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
