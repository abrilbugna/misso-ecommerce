(() => {
  const root = document.querySelector('.home-page');
  function initIntroCarousel() {
    const carousel = root?.querySelector('.intro-carousel');
    if (!carousel) return;
    const slides = Array.from(carousel.querySelectorAll('[data-intro-slide]'));
    const dots = Array.from(carousel.querySelectorAll('[data-intro-dot]'));
    const videos = slides.map(slide => slide.querySelector('video'));
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let active = 0;
    let visible = !('IntersectionObserver' in window);
    let focused = false;
    let autoTimer;
    let touchStart;
    let swiped = false;

    videos.forEach(video => {
      if (!video) return;
      const fitFrame = () => {
        if (video.videoWidth && video.videoHeight) {
          video.closest('[data-intro-slide]').style.setProperty('--intro-video-ratio', `${video.videoWidth} / ${video.videoHeight}`);
        }
      };
      video.addEventListener('loadedmetadata', fitFrame);
      fitFrame();
      const ready = () => video.classList.add('is-ready');
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) ready();
      else video.addEventListener('loadeddata', ready);
      video.addEventListener('error', () => video.classList.remove('is-ready'));
      video.pause();
    });

    const playActive = () => {
      videos.forEach((video, index) => {
        if (!video) return;
        if (index === active && visible && !reduced && !document.hidden) video.play().catch(() => {});
        else video.pause();
      });
    };
    const schedule = () => {
      window.clearTimeout(autoTimer);
      if (visible && !reduced && !focused && !document.hidden) {
        autoTimer = window.setTimeout(() => show((active + 1) % slides.length), 6200);
      }
    };
    const show = next => {
      if (next === active || !slides[next]) return;
      active = next;
      slides.forEach((slide, index) => {
        const depth = (index - active + slides.length) % slides.length;
        slide.dataset.stackPosition = ['front', 'next', 'last'][depth];
        slide.classList.toggle('is-active', depth === 0);
        if (depth === 0) slide.removeAttribute('aria-hidden');
        else slide.setAttribute('aria-hidden', 'true');
      });
      dots.forEach((dot, index) => {
        dot.classList.toggle('is-active', index === active);
        if (index === active) dot.setAttribute('aria-current', 'true');
        else dot.removeAttribute('aria-current');
      });
      videos.forEach((video, index) => { if (index !== active) video?.pause(); });
      if (videos[active]?.readyState >= HTMLMediaElement.HAVE_METADATA) videos[active].currentTime = 0;
      playActive();
      schedule();
    };

    carousel.querySelector('[data-intro-prev]')?.addEventListener('click', () => show((active + slides.length - 1) % slides.length));
    carousel.querySelector('[data-intro-next]')?.addEventListener('click', () => show((active + 1) % slides.length));
    dots.forEach((dot, index) => dot.addEventListener('click', () => show(index)));
    slides.forEach((slide, index) => slide.addEventListener('click', () => {
      if (swiped) { swiped = false; return; }
      if (index !== active) show(index);
    }));
    carousel.addEventListener('focusin', event => {
      if (event.target.matches(':focus-visible')) { focused = true; schedule(); }
    });
    carousel.addEventListener('focusout', event => {
      if (!carousel.contains(event.relatedTarget)) { focused = false; schedule(); }
    });
    carousel.addEventListener('pointerdown', event => { touchStart = { x: event.clientX, y: event.clientY }; });
    carousel.addEventListener('pointerup', event => {
      if (!touchStart) return;
      if (event.target.closest('button')) { touchStart = null; return; }
      const dx = event.clientX - touchStart.x;
      const dy = event.clientY - touchStart.y;
      touchStart = null;
      if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy)) {
        swiped = true;
        show((active + (dx < 0 ? 1 : slides.length - 1)) % slides.length);
        window.setTimeout(() => { swiped = false; }, 250);
      }
    });
    carousel.addEventListener('pointercancel', () => { touchStart = null; });
    document.addEventListener('visibilitychange', () => { playActive(); schedule(); });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => {
        visible = entries[0].isIntersecting;
        playActive();
        schedule();
      }, { threshold: .2 }).observe(carousel);
    } else { playActive(); schedule(); }
  }
  initIntroCarousel();
  if (!root || !window.gsap || !window.ScrollTrigger) {
    window.clearTimeout(window.missoIntroFallback);
    document.documentElement.classList.remove('misso-intro-pending', 'misso-intro-running', 'misso-intro-waiting');
    window.unlockIntroScroll?.();
    return;
  }
  const { gsap, ScrollTrigger } = window;
  gsap.registerPlugin(ScrollTrigger);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reducedMotion) root.classList.add('motion-ready');

  const mm = gsap.matchMedia();
  const cards = gsap.utils.toArray('.benefit-card');
  const cardCount = document.querySelector('[data-card-count]');
  const product = document.querySelector('[data-product-motion]');

  let introStarted = false;
  let introComplete = false;
  let scrollArrowMotion;

  // letram.svg is a filled silhouette, not an open pen path. These guides only
  // expose its ink: every visible edge still comes from the fetched original.
  // Coordinates below are in the asset's 600 × 365 viewBox after its g transform.
  const logoGestures = [
    { d: 'M187 123 Q213 122 231 113', width: 28, at: .10, duration: .10 },
    { d: 'M222 119 L222 231 Q222 245 209 246', width: 42, at: .18, duration: .22 },
    { d: 'M189 247 Q219 241 250 247', width: 22, at: .37, duration: .08 },
    { d: 'M239 153 C260 108 286 102 298 132 Q302 143 302 170 L302 232', width: 42, at: .43, duration: .28 },
    { d: 'M302 231 Q302 245 268 247 L336 247', width: 24, at: .69, duration: .08 },
    { d: 'M318 153 C338 111 365 100 377 129 Q381 140 380 181 L382 233 Q385 272 403 280', width: 42, at: .75, duration: .32 },
    { d: 'M402 280 C428 300 449 275 450 245', width: 25, at: 1.05, duration: .16 },
    { d: 'M450 243 C434 235 423 220 434 211 Q444 205 452 221 Q466 201 472 216 C479 230 460 239 450 243', width: 21, at: 1.19, duration: .16 },
  ];

  async function prepareIntroLogo() {
    const overlay = root.querySelector('.hero-intro-mark');
    if (!overlay) return false;
    try {
      const response = await fetch(overlay.dataset.logoSrc, { signal: AbortSignal.timeout(3500) });
      if (!response.ok) return false;
      const documentSvg = new DOMParser().parseFromString(await response.text(), 'image/svg+xml');
      const original = documentSvg.querySelector('svg > g');
      if (!original || documentSvg.querySelector('parsererror')) return false;
      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', '170 92 325 218');
      svg.setAttribute('class', 'hero-intro-logo');
      svg.setAttribute('focusable', 'false');
      svg.innerHTML = `
        <defs>
          <mask id="misso-ink-reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="600" height="365" style="mask-type:luminance">
            ${logoGestures.map(gesture => `<path class="hero-intro-guide" d="${gesture.d}" stroke-width="${gesture.width}"/>`).join('')}
          </mask>
          <radialGradient id="misso-pen-light" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="19">
            <stop class="hero-intro-warm" stop-opacity=".95"/>
            <stop class="hero-intro-rose" offset=".35" stop-opacity=".7"/>
            <stop class="hero-intro-rose" offset="1" stop-opacity="0"/>
          </radialGradient>
          <linearGradient id="misso-finish-light" gradientUnits="userSpaceOnUse" x1="-26" y1="0" x2="26" y2="0" gradientTransform="translate(120 200) rotate(20)">
            <stop class="hero-intro-rose" stop-opacity="0"/>
            <stop class="hero-intro-rose" offset=".36" stop-opacity=".15"/>
            <stop class="hero-intro-warm" offset=".5" stop-opacity=".95"/>
            <stop class="hero-intro-rose" offset=".64" stop-opacity=".15"/>
            <stop class="hero-intro-rose" offset="1" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <g class="hero-intro-ink" mask="url(#misso-ink-reveal)">
          <use class="hero-intro-base" href="#misso-original-mark"/>
          <use class="hero-intro-pen" href="#misso-original-mark" fill="url(#misso-pen-light)" opacity="0"/>
        </g>
        <use class="hero-intro-finish" href="#misso-original-mark" fill="url(#misso-finish-light)" opacity="0"/>`;
      const geometry = document.importNode(original, true);
      geometry.setAttribute('id', 'misso-original-mark');
      // Inherit the brand color from each use; d and the original transform stay intact.
      geometry.removeAttribute('fill');
      svg.querySelector('defs').prepend(geometry);
      overlay.replaceChildren(svg);
      return true;
    } catch {
      return false; // The watchdog also releases the hero if the script fails entirely.
    }
  }

  function addLogoDrawing(intro, logo, mobile) {
    const guides = Array.from(logo.querySelectorAll('.hero-intro-guide'));
    const pen = logo.querySelector('.hero-intro-pen');
    const light = logo.querySelector('#misso-pen-light');
    const finishLight = logo.querySelector('#misso-finish-light');
    const finishInk = logo.querySelector('.hero-intro-finish');
    // Paint servers inherit the original path's inverted, scaled coordinate space.
    // Cancel that transform so both highlights travel in the guides' viewBox units.
    const inverse = logo.querySelector('#misso-original-mark').transform.baseVal.consolidate().matrix.inverse();
    const paintSpace = `matrix(${inverse.a} ${inverse.b} ${inverse.c} ${inverse.d} ${inverse.e} ${inverse.f})`;
    finishLight.setAttribute('gradientTransform', `${paintSpace} translate(120 200) rotate(20)`);
    guides.forEach((path, index) => {
      const length = path.getTotalLength();
      const gesture = logoGestures[index];
      gsap.set(path, { strokeDasharray: length, strokeDashoffset: length, opacity: 0 });
      // A small overlap joins the gestures; the newest stroke owns the moving light.
      intro.set(path, { opacity: 1 }, gesture.at);
      intro.to(path, { strokeDashoffset: 0, duration: gesture.duration, ease: 'sine.inOut', onUpdate() {
        if (intro.time() >= (logoGestures[index + 1]?.at ?? Infinity)) return;
        const distance = length * this.ratio;
        const point = path.getPointAtLength(distance);
        const before = path.getPointAtLength(Math.max(0, distance - .5));
        const after = path.getPointAtLength(Math.min(length, distance + .5));
        const angle = Math.atan2(after.y - before.y, after.x - before.x) * 180 / Math.PI + 90;
        light.setAttribute('gradientTransform', `${paintSpace} translate(${point.x} ${point.y}) rotate(${angle}) scale(1 .28)`);
      } }, gesture.at);
    });
    intro.to(logo, { opacity: 1, duration: .08 }, .10)
      .to(pen, { opacity: .9, duration: .14 }, .26)
      // The last curved gesture fills both heart lobes, then a single small glint settles.
      .to(pen, { opacity: 1, duration: .06 }, 1.33)
      .to(pen, { opacity: 0, duration: .13 }, 1.39)
      // Also retain the four microscopic isolated marks in the original export.
      .set(logo.querySelector('.hero-intro-ink'), { attr: { mask: 'none' } }, 1.36)
      .set(finishInk, { opacity: 1 }, 1.48)
      .to(finishLight, { attr: { gradientTransform: `${paintSpace} translate(580 200) rotate(20)` }, duration: .34, ease: 'none' }, 1.48)
      .set(finishInk, { opacity: 0 }, 1.82)
      .to(logo, { opacity: 0, scale: mobile ? 1.035 : 1.06, y: mobile ? -6 : -10, duration: .52, ease: 'power3.inOut' }, 1.80);
  }

  function initHeroAnimation(mobile) {
    const html = document.documentElement;
    const overlay = document.querySelector('.hero-intro-mark');
    const logo = overlay?.querySelector('.hero-intro-logo');
    const headlineLines = gsap.utils.toArray('.collection-title > span');
    const collectionActions = root.querySelector('.collection-actions');
    const heroBottomline = root.querySelector('.hero-bottomline');
    const lowerHeroBlock = [collectionActions, heroBottomline].filter(Boolean);
    const notices = gsap.utils.toArray('.collection-notice').filter(notice => {
      const container = notice.closest('.collection-notices');
      return getComputedStyle(notice).display !== 'none' && getComputedStyle(container).display !== 'none';
    });
    // The original logo presentation must not depend on the hero's markup.
    if (!overlay || !logo) {
      window.clearTimeout(window.missoIntroFallback);
      html.classList.remove('misso-intro-pending', 'misso-intro-running', 'misso-intro-waiting');
      window.unlockIntroScroll?.();
      return;
    }

    html.classList.add('misso-intro-running');
    gsap.set(overlay, { clearProps: 'opacity,visibility,transform' });
    gsap.set(logo, { opacity: 0, y: 0, scale: 1 });
    if (reducedMotion) {
      logo.querySelector('.hero-intro-ink').removeAttribute('mask');
      const reducedIntro = gsap.timeline({ onComplete: () => {
        window.clearTimeout(window.missoIntroFallback);
        html.classList.remove('misso-intro-pending', 'misso-intro-running');
        window.unlockIntroScroll?.();
      } });
      reducedIntro.to(logo, { opacity: 1, duration: .14 })
        .to(logo, { opacity: 0, duration: .18 }, .30)
        .call(() => html.classList.remove('misso-intro-pending'), [], .34);
      return;
    }
    const entranceElements = [
      ...headlineLines, ...notices, product,
      ...root.querySelectorAll('.hero-nav, .collection-backdrop, .collection-kicker'),
      ...lowerHeroBlock,
    ];
    gsap.set(entranceElements, { autoAlpha: 0 });
    gsap.set(headlineLines, { y: mobile ? 18 : 32 });
    gsap.set(product, { y: mobile ? 60 : 80 });
    if (notices.length) gsap.set(notices, { y: 15, scale: .85 });
    gsap.set(lowerHeroBlock, { y: mobile ? 60 : 80 });
    html.classList.remove('misso-intro-pending');

    let intro;
    const finishOnPageHide = () => {
      if (!introComplete && intro) intro.progress(1);
    };
    const finish = () => {
      if (introComplete) return;
      introComplete = true;
      window.removeEventListener('pagehide', finishOnPageHide);
      window.clearTimeout(window.missoIntroFallback);
      html.classList.remove('misso-intro-running');
      window.unlockIntroScroll?.();
      gsap.set([overlay, ...entranceElements], { clearProps: 'opacity,visibility,transform' });
      scrollArrowMotion?.play();
      initProductMotion(mobile);
      ScrollTrigger.refresh();
    };

    intro = gsap.timeline({ defaults: { ease: 'power3.out' }, onComplete: finish }).timeScale(1.4);
    window.addEventListener('pagehide', finishOnPageHide, { once: true });
    addLogoDrawing(intro, logo, mobile);
    // Original handoff from 7a93b4c: overlap the hero with the logo's soft exit.
    // Keep the original drawing and shimmers while the product and lower CTA
    // emerge upward in sequence.
    intro.addLabel('hero', 1.95)
      .to('.collection-backdrop', { autoAlpha: 1, duration: .42 }, 'hero')
      .to('.hero-nav', { autoAlpha: 1, duration: .35 }, 'hero')
      .to('.collection-kicker', { autoAlpha: 1, duration: .35 }, 'hero+=.10')
      .to(headlineLines, { autoAlpha: 1, y: 0, stagger: .14, duration: .8 }, 'hero+=.16')
      .to(product, { autoAlpha: 1, y: 0, duration: 1.2, ease: 'power3.out' }, 'hero+=.40');
    if (notices.length) {
      intro.to(notices, { autoAlpha: 1, y: 0, scale: 1, stagger: .14, duration: .7, ease: 'back.out(1.2)' }, 'hero+=1.05');
    }
    intro.to(lowerHeroBlock, { autoAlpha: 1, y: 0, duration: 1.1, ease: 'power3.out', onComplete: () => document.querySelector('.collection-cta')?.classList.add('is-shimmering') }, 'hero+=.80');
    return () => {
      if (!introComplete) {
        intro.progress(1);
        // matchMedia may already have reverted the timeline and suppressed its
        // onComplete callback. Always release the existing intro lock on resize.
        finish();
      }
    };
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

  let productMotionCleanup;
  function initProductMotion() {
    productMotionCleanup?.();
    const motionMedia = gsap.matchMedia();
    motionMedia.add('(prefers-reduced-motion: no-preference)', () => {
      const float = root.querySelector('.collection-product-float');
      const link = root.querySelector('.collection-product-link');
      if (!float || !link) return;
      const ambient = gsap.timeline({ repeat: -1, yoyo: true })
        .to(float, { y: -8, duration: 3.4, ease: 'sine.inOut' });
      const notes = gsap.utils.toArray('.collection-notice').filter(note => {
        const container = note.closest('.collection-notices');
        return getComputedStyle(note).display !== 'none' && getComputedStyle(container).display !== 'none';
      });
      const noteMotions = notes.map((note, index) => gsap.to(note, {
        y: index % 2 ? 3 : -4, duration: 2.8 + index * .4,
        delay: index * .25, repeat: -1, yoyo: true, ease: 'sine.inOut',
      }));
      const pause = () => { ambient.pause(); noteMotions.forEach(tween => tween.pause()); };
      let inView = true;
      const resume = () => {
        if (document.hidden || !inView) return pause();
        ambient.resume(); noteMotions.forEach(tween => tween.resume());
      };
      const observer = new IntersectionObserver(entries => { inView = entries[0].isIntersecting; resume(); });
      observer.observe(product);
      document.addEventListener('visibilitychange', resume);
      window.addEventListener('pagehide', pause);
      window.addEventListener('pageshow', resume);
      const hoverMedia = gsap.matchMedia();
      // The outer notice keeps its entrance/float; only its inner bubble is magnetic.
      hoverMedia.add('(min-width: 768px) and (hover: hover) and (pointer: fine)', () => {
        const hero = root.querySelector('.campaign-hero');
        const magnets = notes.map(note => {
          const bubble = note.querySelector(':scope > span');
          return {
            note,
            x: gsap.quickTo(bubble, 'x', { duration: .3, ease: 'power3.out', overwrite: 'auto' }),
            y: gsap.quickTo(bubble, 'y', { duration: .3, ease: 'power3.out', overwrite: 'auto' }),
          };
        });
        let frame = 0;
        let pointer;
        const update = () => {
          frame = 0;
          // Read stable outer boxes first, so the attraction cannot chase itself.
          const offsets = magnets.map(({ note }) => {
            const rect = note.getBoundingClientRect();
            const dx = pointer.x - (rect.left + rect.width / 2);
            const dy = pointer.y - (rect.top + rect.height / 2);
            const distance = Math.hypot(dx, dy);
            const pull = Math.max(0, 1 - distance / 120);
            const amount = Math.min(8, distance * pull * .3);
            return distance ? [dx / distance * amount, dy / distance * amount] : [0, 0];
          });
          magnets.forEach((magnet, index) => {
            magnet.x(offsets[index][0]);
            magnet.y(offsets[index][1]);
          });
        };
        const reset = () => {
          cancelAnimationFrame(frame);
          frame = 0;
          magnets.forEach(magnet => { magnet.x(0); magnet.y(0); });
        };
        const move = event => {
          if (event.pointerType !== 'mouse') return;
          pointer = { x: event.clientX, y: event.clientY };
          if (!frame) frame = requestAnimationFrame(update);
        };
        hero.addEventListener('pointermove', move, { passive: true });
        hero.addEventListener('pointerleave', reset);
        hero.addEventListener('pointercancel', reset);
        window.addEventListener('resize', reset);
        window.addEventListener('scroll', reset, { passive: true });
        window.addEventListener('blur', reset);
        window.addEventListener('pagehide', reset);
        return () => {
          cancelAnimationFrame(frame);
          hero.removeEventListener('pointermove', move);
          hero.removeEventListener('pointerleave', reset);
          hero.removeEventListener('pointercancel', reset);
          window.removeEventListener('resize', reset);
          window.removeEventListener('scroll', reset);
          window.removeEventListener('blur', reset);
          window.removeEventListener('pagehide', reset);
        };
      });
      hoverMedia.add('(hover: hover) and (pointer: fine)', () => {
        const x = gsap.quickTo(link, 'x', { duration: .6, ease: 'power3.out' });
        const y = gsap.quickTo(link, 'y', { duration: .6, ease: 'power3.out' });
        const rotation = gsap.quickTo(link, 'rotation', { duration: .6, ease: 'power3.out' });
        const move = event => {
          const rect = product.getBoundingClientRect();
          const px = gsap.utils.clamp(-1, 1, (event.clientX - rect.left) / rect.width * 2 - 1);
          const py = gsap.utils.clamp(-1, 1, (event.clientY - rect.top) / rect.height * 2 - 1);
          x(px * 5); y(py * 4); rotation(px * 1.2);
        };
        const leave = () => { x(0); y(0); rotation(0); };
        product.addEventListener('pointermove', move);
        product.addEventListener('pointerleave', leave);
        window.addEventListener('resize', leave);
        return () => {
          product.removeEventListener('pointermove', move);
          product.removeEventListener('pointerleave', leave);
          window.removeEventListener('resize', leave);
        };
      });
      return () => {
        hoverMedia.revert(); observer.disconnect();
        document.removeEventListener('visibilitychange', resume);
        window.removeEventListener('pagehide', pause);
        window.removeEventListener('pageshow', resume);
      };
    });
    productMotionCleanup = () => motionMedia.revert();
  }

  function initHeroArrows() {
    scrollArrowMotion = gsap.to('.scroll-arrow', { y: 5, duration: .8, repeat: -1, yoyo: true, ease: 'sine.inOut', paused: !introComplete });
    mm.add('(hover: hover) and (pointer: fine)', () => {
      const listeners = [];
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
      document.querySelectorAll('.hero-social').forEach(button => {
        const target = button.querySelector('.hero-social-bubble');
        if (!target) return;
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
    gsap.from('.intro-notification', { y: -18, scale: .96, opacity: 0, duration: .5, delay: .45, ease: 'back.out(1.3)', scrollTrigger: { trigger: '.intro-grid', start: 'top 78%' } });
    // Animate the stack wrapper, keeping each complete video flush with its card.
  }

  function initBenefitsScroll(config, autoplay = false) {
    const section = document.querySelector('.benefits-scroll');
    if (!section || !cards.length) return;
    const path = section.querySelector('.benefits-doodle path');
    const originalPath = path?.getAttribute('d');
    if (path) {
      const length = path.getTotalLength() + (autoplay ? 250 : 0);
      gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
    }
    const slot = autoplay ? 2.2 : 1 / cards.length;
    const duration = slot * cards.length;
    const updateCount = progress => {
      if (cardCount) cardCount.textContent = String(Math.min(cards.length, Math.floor(progress * cards.length) + 1)).padStart(2, '0');
    };
    const tl = gsap.timeline(autoplay
      ? { paused: true, repeat: -1, repeatDelay: .25, onUpdate() { updateCount(Math.min(1, this.time() / duration)); } }
      : { scrollTrigger: { trigger: section, start: 'top top', end: 'bottom bottom', scrub: 1, onUpdate: self => updateCount(self.progress) } });
    if (!autoplay) {
      tl.to('.benefits-heading', { yPercent: -20, opacity: .28, ease: 'none', duration }, 0);
      if (path) tl.to(path, { strokeDashoffset: 0, ease: 'none', duration }, 0);
    }
    cards.forEach((card, index) => {
      const fromLeft = index % 2 === 0;
      const fromTop = index % 3 === 2;
      const xStart = fromTop ? 0 : (fromLeft ? -config.distanceX : config.distanceX);
      const yStart = fromTop ? -config.distanceY : config.distanceY;
      const xEnd = fromTop ? 0 : -xStart;
      const yEnd = fromTop ? config.distanceY : -config.distanceY;
      const rotation = (fromLeft ? -1 : 1) * config.rotation;
      const start = index * slot;
      gsap.set(card, { xPercent: xStart, yPercent: yStart, rotation: rotation * (autoplay ? 1.2 : 1.6), scale: autoplay ? .91 : .82, opacity: 1, zIndex: index + 3 });
      if (autoplay) {
        // A single eased arrival, a readable pause, and an overlapping exit keep the loop fluid.
        tl.to(card, { xPercent: 0, yPercent: 0, rotation: rotation * .15, scale: 1, duration: slot * .42, ease: 'power3.out' }, start);
        tl.to(card, { xPercent: xEnd, yPercent: yEnd, rotation: -rotation * .85, scale: .94, duration: slot * .36, ease: 'power2.in' }, start + slot * .73);
      } else {
        // Each card travels quickly at the edges, lingers around the center, then accelerates away.
        tl.to(card, { xPercent: xStart * .23, yPercent: yStart * .23, rotation: rotation, scale: .96, duration: slot * .28, ease: 'power3.out' }, start);
        tl.to(card, { xPercent: 0, yPercent: 0, rotation: rotation * .28, scale: 1, duration: slot * .24, ease: 'sine.out' }, start + slot * .28);
        tl.to(card, { xPercent: xEnd * .07, yPercent: yEnd * .07, rotation: rotation * .45, scale: 1, duration: slot * .19, ease: 'sine.inOut' }, start + slot * .52);
        tl.to(card, { xPercent: xEnd, yPercent: yEnd, rotation: -rotation * 1.5, scale: .87, duration: slot * .29, ease: 'power3.in' }, start + slot * .71);
      }
      const decor = card.querySelector('.card-star');
      if (decor) tl.fromTo(decor, { rotation: -rotation * 7 }, { rotation: rotation * 7, ease: autoplay ? 'sine.inOut' : 'none', duration: slot }, start);
    });
    if (autoplay) {
      const scenery = gsap.timeline({ paused: true });
      scenery.to('.benefits-heading', { yPercent: -12, opacity: .5, duration: 1.3, ease: 'power2.out' }, 0);
      if (path) scenery.to(path, { strokeDashoffset: 0, duration: 2.4, ease: 'power1.inOut' }, 0);
      const wave = { phase: 0 };
      const lineMotion = path && gsap.to(wave, {
        phase: Math.PI * 2,
        duration: 8,
        ease: 'none',
        repeat: -1,
        paused: true,
        onUpdate: () => {
          const sway = Math.sin(wave.phase);
          const ripple = Math.sin(wave.phase * 2);
          path.setAttribute('d', `M-60 ${495 + 14 * sway} C190 ${80 + 55 * ripple} 275 ${830 - 65 * sway} 535 ${400 + 28 * ripple} S780 ${100 + 50 * sway} 1070 ${390 - 18 * ripple}`);
        },
      });
      const play = () => { scenery.play(); lineMotion?.play(); tl.play(); };
      ScrollTrigger.create({
        trigger: section,
        start: 'top 80%',
        end: 'bottom 20%',
        onEnter: play,
        onEnterBack: play,
        onLeave: () => { tl.pause(); lineMotion?.pause(); },
        onLeaveBack: () => { tl.pause(0); lineMotion?.pause(); },
      });
      return () => {
        lineMotion?.kill();
        if (path && originalPath) path.setAttribute('d', originalPath);
      };
    }
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

  document.documentElement.classList.add('misso-intro-waiting');
  prepareIntroLogo().then(ready => {
    document.documentElement.classList.remove('misso-intro-waiting');
    if (!ready || !document.documentElement.classList.contains('misso-intro-pending')) {
      introStarted = true;
      introComplete = true;
      window.clearTimeout(window.missoIntroFallback);
      document.documentElement.classList.remove('misso-intro-pending', 'misso-intro-running');
      window.unlockIntroScroll?.();
      scrollArrowMotion?.play();
      if (!reducedMotion) initProductMotion(window.innerWidth < 768);
      return;
    }
    if (reducedMotion) { initHeroAnimation(window.innerWidth < 768); return; }
    mm.add('(min-width: 768px)', () => {
      if (introStarted) { initProductMotion(false); return; }
      introStarted = true;
      return initHeroAnimation(false);
    });
    mm.add('(max-width: 767px)', () => {
      if (introStarted) { initProductMotion(true); return; }
      introStarted = true;
      return initHeroAnimation(true);
    });
  });
  if (reducedMotion) return;
  initHeroArrows();
  initNavWordmark();
  initBrandIntro();
  mm.add('(min-width: 992px)', () => initBenefitsScroll({ distanceX: 250, distanceY: 190, rotation: 11 }, true));
  mm.add('(min-width: 768px) and (max-width: 991px)', () => initBenefitsScroll({ distanceX: 215, distanceY: 160, rotation: 8 }, true));
  mm.add('(max-width: 767px)', () => initBenefitsScroll({ distanceX: 150, distanceY: 135, rotation: 5 }, true));
  initButtonInteractions();
  initOutroProducts();
  window.addEventListener('load', () => ScrollTrigger.refresh(), { once: true });
})();
