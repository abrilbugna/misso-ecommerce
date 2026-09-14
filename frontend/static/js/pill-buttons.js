(() => {
  const root = document.querySelector('.home-page, .purchase-page');
  if (!root || !window.gsap || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const { gsap } = window;
  const buttons = Array.from(root.querySelectorAll('.misso-pill-button'));
  if (!buttons.length) return;
  root.classList.add('pill-motion-ready');

  const mm = gsap.matchMedia();
  mm.add('(hover: hover) and (pointer: fine)', () => {
    const listeners = [];
    buttons.forEach(button => {
      const circle = button.querySelector('.misso-pill-arrow');
      const label = button.querySelector('.misso-pill-label');
      const icon = circle?.querySelector('svg');
      if (!circle || !label || !icon) return;

      const incoming = icon.cloneNode(true);
      incoming.classList.add('misso-arrow-in');
      circle.appendChild(incoming);
      gsap.set(incoming, { autoAlpha: 0, x: -9, y: 9 });

      const styles = getComputedStyle(button);
      const rose = styles.getPropertyValue('--pill-hover-label').trim() || styles.getPropertyValue('--rose-light').trim() || '#efb6c8';
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
    return () => listeners.forEach(cleanup => cleanup());
  });

  mm.add('(hover: none), (pointer: coarse)', () => {
    const listeners = [];
    buttons.forEach(button => {
      const press = () => gsap.to(button, { scale: .96, duration: .12, overwrite: true });
      const release = () => gsap.to(button, { scale: 1, duration: .2, overwrite: true });
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
})();
