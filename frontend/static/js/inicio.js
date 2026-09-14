(() => {
  const root = document.querySelector('.home-page');
  if (!root || !window.gsap || !window.ScrollTrigger) return;
  const { gsap, ScrollTrigger } = window;
  gsap.registerPlugin(ScrollTrigger);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) return;
  root.classList.add('motion-ready');

  const mm = gsap.matchMedia();
  const cards = gsap.utils.toArray('.benefit-card');
  const cardCount = document.querySelector('[data-card-count]');
  const product = document.querySelector('[data-product-motion]');

  function initHeroAnimation(mobile) {
    const distance = mobile ? 24 : 60;
    const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } });
    entrance
      .from('.hero-social', { opacity: 0, stagger: .07, duration: .34 })
      .from('.hero-nav-actions a', { opacity: 0, stagger: .05, duration: .35 }, .13)
      .from('.hero-message-kicker', { y: 15, opacity: 0, duration: .3 }, .63)
      .from('.hero-message h2 > span', { y: mobile ? 23 : 40, opacity: 0, stagger: .075, duration: .42 }, .72)
      .from('.hero-message p', { y: 15, opacity: 0, duration: .35 }, 1.04)
      .from('.hero-price', { y: 13, opacity: 0, duration: .32 }, 1.2)
      .from('.hero-subscribe', { y: 14, opacity: 0, duration: .35 }, 1.34)
      .from('.hero-product-ring', { scale: .84, opacity: 0, duration: .48 }, 1.49)
      .from(product, { y: distance, rotation: mobile ? -2 : -5, opacity: 0, duration: .56 }, 1.54)
      .from('.hero-badge', { y: mobile ? 13 : 24, scale: .86, opacity: 0, stagger: .08, duration: .4, ease: 'back.out(1.25)' }, 1.72)
      .from('.hero-handwritten, .hero-bottomline', { y: 12, opacity: 0, stagger: .05, duration: .3 }, 1.88);
    if (!mobile) entrance.fromTo('.hero-nav-wordmark', { autoAlpha: 0, y: 7, scale: .94 }, { autoAlpha: 1, y: 0, scale: 1, duration: .6, clearProps: 'transform,opacity,visibility' }, .14);
  }

  function initNavWordmark() {
    const link = document.querySelector('.hero-nav-wordmark');
    if (!link) return;
    const showOnReturn = event => {
      if (!event.persisted || window.innerWidth < 768) return;
      gsap.fromTo(link, { autoAlpha: 0, y: 7, scale: .94 }, { autoAlpha: 1, y: 0, scale: 1, duration: .6, ease: 'power3.out', clearProps: 'transform,opacity,visibility' });
    };
    const hideOnLeave = () => {
      if (window.innerWidth >= 768) gsap.to(link, { autoAlpha: 0, y: -6, duration: .22, ease: 'power2.in', overwrite: true });
    };
    window.addEventListener('pageshow', showOnReturn);
    window.addEventListener('pagehide', hideOnLeave);
  }

  function initProductMotion(mobile) {
    if (!product) return;
    const trigger = { trigger: '.campaign-hero', start: 'top top', end: 'bottom top', scrub: true };
    gsap.to(product, { yPercent: mobile ? -3 : -7, rotation: mobile ? 2 : 4, ease: 'none', scrollTrigger: { ...trigger } });
    gsap.to('.hero-product-ring', { scale: mobile ? 1.025 : 1.07, ease: 'none', scrollTrigger: { ...trigger } });
    if (!mobile) {
      gsap.to('.hero-message', { yPercent: -5, ease: 'none', scrollTrigger: { ...trigger } });
      gsap.to('.hero-badge', { yPercent: index => index % 2 ? -7 : 7, ease: 'none', scrollTrigger: { ...trigger } });
    }
  }

  function initHeroArrows() {
    gsap.to('.scroll-arrow', { y: 5, duration: .8, repeat: -1, yoyo: true, ease: 'sine.inOut' });
    mm.add('(hover: hover) and (pointer: fine)', () => {
      const listeners = [];
      document.querySelectorAll('.misso-pill-button').forEach(button => {
        const circle = button.querySelector('.misso-pill-arrow');
        const label = button.querySelector('.misso-pill-label');
        const icon = circle?.querySelector('svg');
        if (!circle || !label || !icon) return;
        const incoming = icon.cloneNode(true);
        incoming.classList.add('misso-arrow-in');
        circle.appendChild(incoming);
        gsap.set(incoming, { autoAlpha: 0, x: -9, y: 9 });
        const styles = getComputedStyle(root);
        const rose = styles.getPropertyValue('--rose-light').trim() || '#efb6c8';
        const wine = styles.getPropertyValue('--wine-dark').trim() || '#4a0d22';
        const cream = styles.getPropertyValue('--cream').trim() || '#fff5f1';
        const swap = gsap.timeline({ paused: true });
        swap
          .to(circle, { x: () => -circle.offsetLeft, y: -7, scale: 1.07, duration: .26, ease: 'power2.out' }, 0)
          .to(circle, { y: 0, scale: 1, duration: .26, ease: 'power3.out' }, .26)
          .to(label, { x: () => circle.offsetWidth + circle.offsetLeft - label.offsetWidth, y: -2, duration: .27, ease: 'power2.out' }, 0)
          .to(label, { y: 0, duration: .25, ease: 'power3.out' }, .27)
          .to(label, { backgroundColor: rose, duration: .35, ease: 'power2.out' }, .08)
          .to(circle, { backgroundColor: wine, color: cream, duration: .3, ease: 'power2.out' }, .16)
          .to(icon, { x: 9, y: -9, autoAlpha: 0, duration: .2, ease: 'power2.in' }, .07)
          .to(incoming, { x: 0, y: 0, autoAlpha: 1, duration: .25, ease: 'power3.out' }, .23)
          .to(button, { scale: 1.01, duration: .25, ease: 'power2.out' }, .1);
        const enter = () => swap.play();
        const leave = () => swap.reverse();
        button.addEventListener('pointerenter', enter);
        button.addEventListener('pointerleave', leave);
        button.addEventListener('focusin', enter);
        button.addEventListener('focusout', leave);
        listeners.push(() => {
          button.removeEventListener('pointerenter', enter);
          button.removeEventListener('pointerleave', leave);
          button.removeEventListener('focusin', enter);
          button.removeEventListener('focusout', leave);
          swap.kill();
          incoming.remove();
          gsap.set([button, circle, label, icon], { clearProps: 'transform,backgroundColor,color,opacity,visibility' });
        });
      });
      document.querySelectorAll('.hero-social').forEach((button, index) => {
        const bubble = button.querySelector('.hero-social-bubble');
        const icon = bubble?.querySelector('svg');
        if (!bubble || !icon) return;
        const moveX = gsap.quickTo(icon, 'x', { duration: .28, ease: 'power2.out' });
        const moveY = gsap.quickTo(icon, 'y', { duration: .28, ease: 'power2.out' });
        const bubbleScale = gsap.quickTo(bubble, 'scale', { duration: .34, ease: 'power3.out' });
        const bubbleY = gsap.quickTo(bubble, 'y', { duration: .34, ease: 'power3.out' });
        const bubbleRotation = gsap.quickTo(bubble, 'rotation', { duration: .34, ease: 'power3.out' });
        const iconRotation = gsap.quickTo(icon, 'rotation', { duration: .34, ease: 'power3.out' });
        const enter = () => {
          bubbleScale(1.06);
          bubbleY(-2);
          bubbleRotation(index ? 5 : -5);
          iconRotation(index ? 5 : -6);
        };
        const move = event => {
          const rect = button.getBoundingClientRect();
          moveX(Math.max(-3, Math.min(3, (event.clientX - rect.left - rect.width / 2) * .12)));
          moveY(Math.max(-3, Math.min(3, (event.clientY - rect.top - rect.height / 2) * .12)));
        };
        const leave = () => {
          bubbleScale(1);
          bubbleY(0);
          bubbleRotation(0);
          iconRotation(0);
          moveX(0);
          moveY(0);
        };
        button.addEventListener('pointerenter', enter);
        button.addEventListener('pointermove', move);
        button.addEventListener('pointerleave', leave);
        button.addEventListener('focusin', enter);
        button.addEventListener('focusout', leave);
        listeners.push(() => {
          button.removeEventListener('pointerenter', enter);
          button.removeEventListener('pointermove', move);
          button.removeEventListener('pointerleave', leave);
          button.removeEventListener('focusin', enter);
          button.removeEventListener('focusout', leave);
          gsap.set([bubble, icon], { clearProps: 'transform' });
        });
      });
      return () => listeners.forEach(cleanup => cleanup());
    });
    mm.add('(hover: none), (pointer: coarse)', () => {
      const listeners = [];
      document.querySelectorAll('.misso-pill-button, .hero-social').forEach(button => {
        const target = button.querySelector('.hero-social-bubble') || button;
        const press = () => gsap.to(target, { scale: .96, duration: .12, overwrite: true });
        const release = () => gsap.to(target, { scale: 1, duration: .2, overwrite: true });
        button.addEventListener('pointerdown', press);
        button.addEventListener('pointerup', release);
        button.addEventListener('pointercancel', release);
        listeners.push(() => {
          button.removeEventListener('pointerdown', press);
          button.removeEventListener('pointerup', release);
          button.removeEventListener('pointercancel', release);
        });
      });
      return () => listeners.forEach(cleanup => cleanup());
    });
  }

  function initBrandIntro() {
    gsap.to('.intro-marquee span', { xPercent: -32, ease: 'none', scrollTrigger: { trigger: '.brand-intro', start: 'top bottom', end: 'bottom top', scrub: true } });
    gsap.from('.intro-copy > *', { y: 55, opacity: 0, stagger: .11, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: '.intro-copy', start: 'top 78%' } });
    gsap.from('.intro-image-wrap', { y: 80, rotation: 4, opacity: 0, duration: 1.1, ease: 'power3.out', scrollTrigger: { trigger: '.intro-grid', start: 'top 78%' } });
    gsap.to('.intro-image-wrap img', { yPercent: -8, ease: 'none', scrollTrigger: { trigger: '.intro-grid', start: 'top bottom', end: 'bottom top', scrub: true } });
  }

  function initBenefitsScroll(config) {
    const section = document.querySelector('.benefits-scroll');
    if (!section || !cards.length) return;
    const path = section.querySelector('.benefits-doodle path');
    if (path) {
      const length = path.getTotalLength();
      gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
    }
    const tl = gsap.timeline({ scrollTrigger: { trigger: section, start: 'top top', end: 'bottom bottom', scrub: 1, onUpdate: self => {
      if (cardCount) cardCount.textContent = String(Math.min(cards.length, Math.floor(self.progress * cards.length) + 1)).padStart(2, '0');
    } } });
    tl.to('.benefits-heading', { yPercent: -20, opacity: .28, ease: 'none', duration: 1 }, 0);
    if (path) tl.to(path, { strokeDashoffset: 0, ease: 'none', duration: 1 }, 0);
    const slot = 1 / cards.length;
    cards.forEach((card, index) => {
      const fromLeft = index % 2 === 0;
      const fromTop = index % 3 === 2;
      const xStart = fromTop ? 0 : (fromLeft ? -config.distanceX : config.distanceX);
      const yStart = fromTop ? -config.distanceY : config.distanceY;
      const xEnd = fromTop ? 0 : -xStart;
      const yEnd = fromTop ? config.distanceY : -config.distanceY;
      const rotation = (fromLeft ? -1 : 1) * config.rotation;
      const start = index * slot;
      gsap.set(card, { xPercent: xStart, yPercent: yStart, rotation: rotation * 1.6, scale: .82, opacity: 1, zIndex: index + 3 });
      // Each card travels quickly at the edges, lingers around the center, then accelerates away.
      tl.to(card, { xPercent: xStart * .23, yPercent: yStart * .23, rotation: rotation, scale: .96, duration: slot * .28, ease: 'power3.out' }, start);
      tl.to(card, { xPercent: 0, yPercent: 0, rotation: rotation * .28, scale: 1, duration: slot * .24, ease: 'sine.out' }, start + slot * .28);
      tl.to(card, { xPercent: xEnd * .07, yPercent: yEnd * .07, rotation: rotation * .45, scale: 1, duration: slot * .19, ease: 'sine.inOut' }, start + slot * .52);
      tl.to(card, { xPercent: xEnd, yPercent: yEnd, rotation: -rotation * 1.5, scale: .87, duration: slot * .29, ease: 'power3.in' }, start + slot * .71);
      const decor = card.querySelector('.card-star');
      if (decor) tl.fromTo(decor, { rotation: -rotation * 7 }, { rotation: rotation * 7, ease: 'none', duration: slot }, start);
    });
  }

  function initButtonInteractions() {
    gsap.from('.home-outro > *:not(.outro-mark)', { y: 35, opacity: 0, stagger: .12, duration: .8, ease: 'power3.out', scrollTrigger: { trigger: '.home-outro', start: 'top 72%' } });
    mm.add('(min-width: 992px) and (pointer: fine)', () => {
      const listeners = [];
      cards.forEach(card => {
        const image = card.querySelector('.card-image img');
        const move = event => {
          const rect = card.getBoundingClientRect();
          gsap.to(image, { x: ((event.clientX - rect.left) / rect.width - .5) * 8, y: ((event.clientY - rect.top) / rect.height - .5) * 8, duration: .45, overwrite: true });
        };
        const leave = () => gsap.to(image, { x: 0, y: 0, duration: .5, overwrite: true });
        card.addEventListener('pointermove', move);
        card.addEventListener('pointerleave', leave);
        listeners.push(() => { card.removeEventListener('pointermove', move); card.removeEventListener('pointerleave', leave); });
      });
      return () => listeners.forEach(cleanup => cleanup());
    });
  }

  function initOutroProducts() {
    const viewport = document.querySelector('.outro-products');
    const track = viewport?.querySelector('.outro-products-track');
    const group = track?.querySelector('.outro-products-group');
    if (!viewport || !track || !group) return;
    const originals = Array.from(group.children).map(item => item.cloneNode(true));
    if (!originals.length) return;
    let motion;
    let resizeTimer;

    const build = () => {
      motion?.kill();
      gsap.set(track, { clearProps: 'transform' });
      track.querySelectorAll('.outro-products-group:not(:first-child)').forEach(item => item.remove());
      group.replaceChildren(...originals.map(item => item.cloneNode(true)));
      let repetitions = 0;
      while (group.scrollWidth < viewport.clientWidth + 280 && repetitions < 12) {
        originals.forEach(item => {
          const copy = item.cloneNode(true);
          copy.setAttribute('aria-hidden', 'true');
          copy.tabIndex = -1;
          group.appendChild(copy);
        });
        repetitions += 1;
      }
      const duplicate = group.cloneNode(true);
      duplicate.setAttribute('aria-hidden', 'true');
      duplicate.querySelectorAll('a').forEach(link => { link.tabIndex = -1; });
      track.appendChild(duplicate);
      const distance = group.getBoundingClientRect().width;
      motion = gsap.to(track, { x: -distance, duration: distance / 42, ease: 'none', repeat: -1 });
    };

    build();
    const resize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(build, 150); };
    window.addEventListener('resize', resize);
    if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
      viewport.addEventListener('pointerenter', () => motion?.pause());
      viewport.addEventListener('pointerleave', () => motion?.resume());
    }
    viewport.addEventListener('focusin', () => motion?.pause());
    viewport.addEventListener('focusout', () => motion?.resume());
  }

  mm.add('(min-width: 768px)', () => { initHeroAnimation(false); initProductMotion(false); });
  mm.add('(max-width: 767px)', () => { initHeroAnimation(true); initProductMotion(true); });
  initHeroArrows();
  initNavWordmark();
  initBrandIntro();
  mm.add('(min-width: 992px)', () => initBenefitsScroll({ distanceX: 250, distanceY: 190, rotation: 11 }));
  mm.add('(min-width: 768px) and (max-width: 991px)', () => initBenefitsScroll({ distanceX: 215, distanceY: 160, rotation: 8 }));
  mm.add('(max-width: 767px)', () => initBenefitsScroll({ distanceX: 150, distanceY: 135, rotation: 5 }));
  initButtonInteractions();
  initOutroProducts();
  window.addEventListener('load', () => ScrollTrigger.refresh(), { once: true });
})();
