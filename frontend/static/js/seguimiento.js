(() => {
  const root = document.querySelector('.tracking-page');
  if (!root) return;

  const button = root.querySelector('[data-copy-tracking]');
  const code = root.querySelector('#tracking-code');
  const status = root.querySelector('[data-copy-status]');
  if (button && code && status) {
    button.hidden = false;
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(code.textContent.trim());
        status.textContent = 'Código copiado.';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'No pudimos copiarlo. El código quedó seleccionado para que lo copies manualmente.';
      }
    });
  }

  const releasePending = () => {
    window.clearTimeout(window.trackingMotionFallback);
    document.documentElement.classList.remove('tracking-motion-pending');
  };
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!window.gsap || reduced.matches) {
    releasePending();
    return;
  }

  const { gsap } = window;
  // If the fail-open timer already released the page, avoid hiding it again.
  const animateEntrance = document.documentElement.classList.contains('tracking-motion-pending');
  const nav = document.querySelector('.tracking-nav');
  const titleParts = [...root.querySelectorAll('.tracking-title-part')];
  const subtitle = root.querySelector('.tracking-intro > p');
  const orderCard = root.querySelector('.tracking-card:not(.tracking-lookup)');
  const lookup = root.querySelector('.tracking-lookup');
  const lookupHasError = Boolean(lookup?.querySelector('[role="alert"]'));
  const animated = [];
  let observer;
  let leaving = false;
  const deferred = new Set();

  const revealDeferredElement = element => {
    if (!deferred.delete(element)) return;
    observer?.unobserve(element);
    gsap.to(element, { opacity: 1, y: 0, duration: .45, ease: 'power3.out', clearProps: 'transform,opacity' });
    if (!deferred.size) {
      window.removeEventListener('scroll', checkDeferred);
      window.removeEventListener('resize', checkDeferred);
    }
  };
  const checkDeferred = () => {
    deferred.forEach(element => {
      if (element.getBoundingClientRect().top <= window.innerHeight - 24) revealDeferredElement(element);
    });
  };
  const clearDeferred = () => {
    observer?.disconnect();
    deferred.clear();
    window.removeEventListener('scroll', checkDeferred);
    window.removeEventListener('resize', checkDeferred);
  };

  const prepare = (targets, properties) => {
    if (!animateEntrance || !targets || (Array.isArray(targets) && !targets.length)) return;
    gsap.set(targets, properties);
    animated.push(...(Array.isArray(targets) ? targets : [targets]));
  };
  const intro = gsap.timeline({ defaults: { ease: 'power3.out' } });

  prepare(nav, { autoAlpha: 0, y: -15 });
  prepare(titleParts, { autoAlpha: 0, y: 18 });
  prepare(subtitle, { autoAlpha: 0, y: 10 });
  prepare(orderCard, { autoAlpha: 0, y: 30 });
  if (!lookupHasError) prepare(lookup, { autoAlpha: 0, y: 30 });

  if (animateEntrance && nav) intro.to(nav, { autoAlpha: 1, y: 0, duration: .4, clearProps: 'transform,opacity,visibility' }, 0);
  if (animateEntrance && titleParts.length) intro.to(titleParts, { autoAlpha: 1, y: 0, duration: .6, stagger: .09, clearProps: 'transform,opacity,visibility' }, .15);
  if (animateEntrance && subtitle) intro.to(subtitle, { autoAlpha: 1, y: 0, duration: .42, clearProps: 'transform,opacity,visibility' }, .48);

  if (orderCard && animateEntrance) {
    const number = orderCard.querySelector('.tracking-heading > div');
    const badge = orderCard.querySelector('.tracking-status');
    const steps = [...orderCard.querySelectorAll('.tracking-progress li')];
    prepare(number, { opacity: 0, y: 10 });
    prepare(badge, { opacity: 0, y: 8 });
    prepare(steps, { opacity: 0, y: 12 });
    intro.to(orderCard, { autoAlpha: 1, y: 0, duration: .6, clearProps: 'transform,opacity,visibility' }, .56);
    if (number) intro.to(number, { opacity: 1, y: 0, duration: .42, clearProps: 'transform,opacity' }, .77);
    if (badge) intro.to(badge, { opacity: 1, y: 0, duration: .38, clearProps: 'transform,opacity' }, .85);
    if (steps.length) intro.to(steps, { opacity: 1, y: 0, duration: .42, stagger: .08, clearProps: 'transform,opacity' }, 1.0);

    const lowerBlocks = [
      ...orderCard.querySelectorAll(':scope > p:not(.tracking-copy-status), .tracking-details, .tracking-actions, .tracking-help')
    ];
    const reveal = (element, at) => {
      prepare(element, { opacity: 0, y: 12 });
      const bounds = element.getBoundingClientRect();
      if ('IntersectionObserver' in window && bounds.top >= window.innerHeight - 24) {
        observer ||= new IntersectionObserver(entries => {
          entries.forEach(entry => {
            if (!entry.isIntersecting && entry.boundingClientRect.bottom >= 0) return;
            revealDeferredElement(entry.target);
          });
        }, { rootMargin: '0px 0px -24px 0px', threshold: 0 });
        if (!deferred.size) {
          window.addEventListener('scroll', checkDeferred, { passive: true });
          window.addEventListener('resize', checkDeferred, { passive: true });
        }
        deferred.add(element);
        observer.observe(element);
      } else {
        intro.to(element, { opacity: 1, y: 0, duration: .42, clearProps: 'transform,opacity' }, at);
      }
    };
    lowerBlocks.forEach((element, index) => reveal(element, 1.16 + index * .08));
  }

  if (lookup && !lookupHasError && animateEntrance) {
    const lookupAt = orderCard ? 1.03 : .68;
    const heading = lookup.querySelector('h2');
    const fields = [...lookup.querySelectorAll('form > div')];
    const submit = lookup.querySelector('form > button');
    prepare(heading, { opacity: 0, y: 8 });
    prepare(fields, { opacity: 0, y: 10 });
    // pill-buttons.js owns the button transform for hover and touch.
    prepare(submit, { opacity: 0 });
    intro.to(lookup, { autoAlpha: 1, y: 0, duration: .6, clearProps: 'transform,opacity,visibility' }, lookupAt);
    if (heading) intro.to(heading, { opacity: 1, y: 0, duration: .38, clearProps: 'transform,opacity' }, lookupAt + .16);
    if (fields.length) intro.to(fields, { opacity: 1, y: 0, duration: .4, stagger: .08, clearProps: 'transform,opacity' }, lookupAt + .26);
    if (submit) intro.to(submit, { opacity: 1, duration: .35, clearProps: 'opacity' }, lookupAt + .38 + Math.max(0, fields.length - 1) * .08);
  }

  releasePending();

  const restore = () => {
    intro.kill();
    clearDeferred();
    gsap.set([nav, root, ...animated].filter(Boolean), { clearProps: 'transform,opacity,visibility' });
    leaving = false;
    releasePending();
  };
  window.addEventListener('pageshow', event => { if (event.persisted) restore(); });
  reduced.addEventListener('change', () => { if (reduced.matches && !leaving) restore(); });

  document.addEventListener('click', event => {
    const link = event.target.closest('.tracking-nav a.hero-nav-wordmark, .tracking-nav a.hero-shop, .tracking-nav a.hero-cart');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || leaving) return;
    if (link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const destination = new URL(link.href, window.location.href);
    if (!['http:', 'https:'].includes(destination.protocol) || destination.origin !== window.location.origin) return;
    if (destination.pathname === window.location.pathname && destination.search === window.location.search) return;

    event.preventDefault();
    leaving = true;
    intro.kill();
    clearDeferred();
    let navigated = false;
    const navigate = () => {
      if (navigated) return;
      navigated = true;
      window.clearTimeout(fallback);
      window.location.assign(destination.href);
    };
    const fallback = window.setTimeout(navigate, 350);
    gsap.to([nav, root].filter(Boolean), { opacity: 0, y: 8, duration: .28, ease: 'power2.in', onComplete: navigate });
  });
})();
