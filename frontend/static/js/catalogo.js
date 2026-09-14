(() => {
  const cards = [...document.querySelectorAll('[data-catalog-card]')];
  const promo = document.querySelector('[data-catalog-promo]');
  const sort = document.querySelector('#catalog-sort-select');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!window.gsap || reduced) return;
  const run = () => {
    gsap.from('.catalog-nav', { y: -24, opacity: 0, duration: .65, ease: 'power3.out' });
    gsap.from('.catalog-heading h1', { y: 36, opacity: 0, duration: .75, ease: 'power4.out' });
    gsap.from('.catalog-reveal-line > span', { yPercent: 115, duration: .7, stagger: .1, ease: 'power4.out' });
    gsap.from('.catalog-hero-kicker, .catalog-subtitle, .catalog-scribble', { opacity: 0, y: 22, duration: .55, stagger: .1, delay: .25, ease: 'power3.out' });
    gsap.from('.catalog-filter, .catalog-count', { opacity: 0, y: 12, duration: .45, stagger: .06, delay: .5, ease: 'power3.out' });
    if (window.ScrollTrigger) {
      gsap.from(cards, { opacity: 0, y: 42, duration: .7, stagger: .08, ease: 'power3.out', scrollTrigger: { trigger: '.catalog-grid', start: 'top 82%' } });
      if (promo) gsap.from(promo, { opacity: 0, scale: .96, duration: .8, ease: 'power3.out', scrollTrigger: { trigger: promo, start: 'top 85%' } });
    }
    sort?.addEventListener('change', () => {
      const grid = document.querySelector('.catalog-content > .catalog-grid');
      if (!grid) return;
      const products = [...grid.querySelectorAll('.catalog-product')];
      const mode = sort.value;
      products.sort((a, b) => mode === 'caros' ? Number(b.dataset.price) - Number(a.dataset.price) : mode === 'baratos' ? Number(a.dataset.price) - Number(b.dataset.price) : mode === 'az' ? a.dataset.name.localeCompare(b.dataset.name) : Number(b.dataset.relevance) - Number(a.dataset.relevance));
      products.forEach(card => grid.appendChild(card));
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, { once: true }); else run();
})();
