(() => {
  const run = () => {
    const root = document.querySelector('.catalog-page');
    if (!root) return;

    const grid = root.querySelector('.catalog-grid');
    const sort = root.querySelector('#catalog-sort-select');
    const cards = [...root.querySelectorAll('[data-catalog-card]')];
    const promo = root.querySelector('[data-catalog-promo]');
    const initialOrder = new Map(cards.map((card, index) => [card, index]));

    // Category links still navigate through Django; only the local order changes here.
    sort?.addEventListener('change', () => {
      if (!grid) return;
      const mode = sort.value;
      const ordered = [...cards].sort((a, b) => {
        let difference = 0;
        if (mode === 'caros') difference = Number(b.dataset.price) - Number(a.dataset.price);
        else if (mode === 'baratos') difference = Number(a.dataset.price) - Number(b.dataset.price);
        else if (mode === 'az') difference = a.dataset.name.localeCompare(b.dataset.name, 'es');
        else difference = Number(b.dataset.relevance) - Number(a.dataset.relevance);
        return difference || initialOrder.get(a) - initialOrder.get(b);
      });
      ordered.forEach((card, index) => {
        grid.appendChild(card);
        if (index === 3 && promo) grid.appendChild(promo);
      });
      window.ScrollTrigger?.refresh();
    });

    if (!window.gsap || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const { gsap } = window;
    const nav = root.querySelector('.hero-nav');
    const socials = [...root.querySelectorAll('.hero-social')];
    const wordmark = root.querySelector('.hero-nav-wordmark');
    const shopBrand = root.querySelector('.shop-brand-shimmer');
    const cart = root.querySelector('.hero-cart');
    const eyebrow = root.querySelector('.catalog-eyebrow');
    const lines = [...root.querySelectorAll('.catalog-title-line')];
    const lineText = lines.map(line => line.firstElementChild).filter(Boolean);
    const toolbarTop = root.querySelector('.catalog-toolbar-top');
    const filters = [...root.querySelectorAll('.catalog-filter')];
    const empty = root.querySelector('.catalog-empty');

    // The nav uses Home's classes, SVGs and reveal durations.
    if (nav) gsap.set(nav, { autoAlpha: 0 });
    if (socials.length) gsap.set(socials, { autoAlpha: 0, y: -12 });
    if (wordmark) gsap.set(wordmark, { autoAlpha: 0 });
    if (cart) gsap.set(cart, { autoAlpha: 0, y: -12 });
    if (lineText.length) {
      gsap.set(lines, { overflow: 'hidden' });
      gsap.set(lineText, { autoAlpha: 0, yPercent: 110 });
    }
    const intro = gsap.timeline({ defaults: { ease: 'power3.out' } });
    if (nav) intro.to(nav, { autoAlpha: 1, duration: .01 }, 0);
    if (socials.length) intro.to(socials, { autoAlpha: 1, y: 0, stagger: .06, duration: .34 }, .02);
    if (wordmark) intro.to(wordmark, { autoAlpha: 1, duration: .22 }, .06);
    if (cart) intro.to(cart, { autoAlpha: 1, y: 0, duration: .34 }, .11);
    if (eyebrow) intro.from(eyebrow, { autoAlpha: 0, y: 12, duration: .35 }, .27);
    if (lineText.length) intro.to(lineText, { autoAlpha: 1, yPercent: 0, stagger: .09, duration: .55, ease: 'power4.out', onComplete: () => { lines.forEach(line => line.classList.add('reveal-complete')); gsap.set(lines, { overflow: 'visible' }); } }, .38);
    if (toolbarTop) intro.from(toolbarTop, { autoAlpha: 0, y: 12, duration: .42 }, .8);
    if (filters.length) intro.from(filters, { autoAlpha: 0, y: 12, stagger: .05, duration: .42 }, .88);
    if (empty) intro.from(empty, { autoAlpha: 0, y: 24, duration: .6 }, 1.03);
    if (shopBrand) intro.eventCallback('onComplete', () => shopBrand.classList.add('is-shimmering'));

    if (window.ScrollTrigger) {
      gsap.registerPlugin(window.ScrollTrigger);
      if (cards.length) {
        gsap.set(cards, { autoAlpha: 0, y: 40 });
        window.ScrollTrigger.batch(cards, {
          start: 'top 88%',
          once: true,
          onEnter: batch => gsap.to(batch, { autoAlpha: 1, y: 0, stagger: .08, duration: .7, ease: 'power3.out', clearProps: 'transform,opacity,visibility' })
        });
      }
      if (promo) gsap.fromTo(promo, { autoAlpha: 0, scale: .97 }, { autoAlpha: 1, scale: 1, duration: .8, ease: 'power3.out', clearProps: 'transform,opacity,visibility', scrollTrigger: { trigger: promo, start: 'top 85%', once: true } });
    }

    // Match the magnetic social bubbles in Home; only fine pointers receive it.
    if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
      socials.forEach((button, index) => {
        const bubble = button.querySelector('.hero-social-bubble');
        const icon = bubble?.querySelector('svg');
        if (!bubble || !icon) return;
        const moveX = gsap.quickTo(icon, 'x', { duration: .28, ease: 'power2.out' });
        const moveY = gsap.quickTo(icon, 'y', { duration: .28, ease: 'power2.out' });
        const bubbleScale = gsap.quickTo(bubble, 'scale', { duration: .34, ease: 'power3.out' });
        const bubbleY = gsap.quickTo(bubble, 'y', { duration: .34, ease: 'power3.out' });
        const bubbleRotation = gsap.quickTo(bubble, 'rotation', { duration: .34, ease: 'power3.out' });
        const iconRotation = gsap.quickTo(icon, 'rotation', { duration: .34, ease: 'power3.out' });
        const enter = () => { bubbleScale(1.06); bubbleY(-2); bubbleRotation(index ? 5 : -5); iconRotation(index ? 5 : -6); };
        const move = event => {
          const rect = button.getBoundingClientRect();
          moveX(Math.max(-3, Math.min(3, (event.clientX - rect.left - rect.width / 2) * .12)));
          moveY(Math.max(-3, Math.min(3, (event.clientY - rect.top - rect.height / 2) * .12)));
        };
        const leave = () => { bubbleScale(1); bubbleY(0); bubbleRotation(0); iconRotation(0); moveX(0); moveY(0); };
        button.addEventListener('pointerenter', enter);
        button.addEventListener('pointermove', move);
        button.addEventListener('pointerleave', leave);
        button.addEventListener('focusin', enter);
        button.addEventListener('focusout', leave);
      });
    } else {
      socials.forEach(button => {
        const bubble = button.querySelector('.hero-social-bubble');
        if (!bubble) return;
        const press = () => gsap.to(bubble, { scale: .96, duration: .12, overwrite: true });
        const release = () => gsap.to(bubble, { scale: 1, duration: .2, overwrite: true });
        button.addEventListener('pointerdown', press);
        button.addEventListener('pointerup', release);
        button.addEventListener('pointercancel', release);
      });
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, { once: true });
  else run();
})();
