/* Small local gestures while resting. Never moves the mascot around the UI. */
(function (global) {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  class InkScoutPresence {
    constructor(s, { stage = s.host.parentElement, physics = null } = {}) {
      this.s = s; this.physics = physics; this.time = 0; this.angle = 0;
      this.target = 0; this.patTime = 0; this.raf = 0; this.enabled = true;
      this.listeners = [];
      this.raw = document.createElement('canvas'); this.raw.width = this.raw.height = 320;
      this.rawCtx = this.raw.getContext('2d');
      this.baseDraw = s.draw.bind(s);
      const previousDestroy = s.destroy.bind(s);
      s.destroy = () => { this.destroy(); previousDestroy(); };
      const on = (el, name, fn) => { el.addEventListener(name, fn); this.listeners.push(() => el.removeEventListener(name, fn)); };
      on(stage, 'pointermove', event => {
        const r = s.host.getBoundingClientRect();
        this.target = clamp((event.clientX - r.left - r.width / 2) / Math.max(1, r.width) * 1.7, -2.5, 2.5);
        this.start();
      });
      on(stage, 'pointerleave', () => { this.target = 0; });
      on(s.host, 'statechange', () => { this.patTime = 0; this.start(); });
      on(s.host, 'movementcomplete', () => { this.settle = .55; this.start(); });
      on(s.host, 'pickup', () => { this.patTime = 0; this.reset(); });
      on(document, 'visibilitychange', () => { this.last = null; if (document.hidden) this.stop(); else this.start(); });
      on(s.media, 'change', () => { this.reset(); this.start(); });
      // Base frame playback still owns expressions/blinks. Decoration never
      // accumulates because each tick redraws from its source atlas.
      s.draw = frame => {
        if (this.eligible() && this.patTime > .20 && this.patTime < .82 && s.anim.animation === 'idle') frame = 68;
        s.lastFrame = -1; this.baseDraw(frame);
        if (this.eligible()) { this.decorate(); this.start(); }
      };
      s.ready.then(() => this.start());
    }
    eligible() {
      const s = this.s;
      return this.enabled && !s.destroyed && !s.reducedMotion && !this.physics?.mode && !s.motion &&
        s.state === 'idle' && !s.anim?.static && ['idle', 'idle-breathing', 'blink'].includes(s.anim?.animation);
    }
    start() {
      if (this.raf || !this.eligible() || this.s.paused || !this.s.visible || document.hidden) return;
      this.last = null; this.raf = requestAnimationFrame(t => this.tick(t));
    }
    stop() { cancelAnimationFrame(this.raf); this.raf = 0; this.last = null; }
    reset() { this.s.canvas.style.transform = ''; this.angle = 0; }
    async pat() {
      const s = this.s;
      if (s.destroyed || s.paused || this.physics?.mode || s.motion) return false;
      if (s.reducedMotion) { s.event('affection', { reducedMotion: true }); return true; }
      if (s.anim?.animation !== 'idle') await s.setState('idle');
      if (!this.eligible()) return false;
      this.patTime = .95; this.start(); s.event('affection', { reducedMotion: false }); return true;
    }
    decorate() {
      const s = this.s;
      this.rawCtx.clearRect(0, 0, 320, 320); this.rawCtx.drawImage(s.canvas, 0, 0);
      const ctx = s.ctx, cut = 169;
      // The upper segment overlaps the neck; a small rotation reads as a head
      // tilt while the torso and planted feet remain steady.
      ctx.clearRect(0, 0, 320, 320);
      ctx.drawImage(this.raw, 0, cut, 320, 320 - cut, 0, cut, 320, 320 - cut);
      ctx.save(); ctx.translate(160, cut - 3); ctx.rotate(this.angle * Math.PI / 180); ctx.translate(-160, -(cut - 3));
      ctx.drawImage(this.raw, 0, 0, 320, cut + 3, 0, 0, 320, cut + 3); ctx.restore();
    }
    tick(now) {
      this.raf = 0; const s = this.s;
      if (!this.eligible() || s.paused || !s.visible || document.hidden) { this.reset(); this.last = null; return; }
      const dt = this.last == null ? 0 : Math.min(.032, (now - this.last) / 1000); this.last = now; this.time += dt;
      this.patTime = Math.max(0, this.patTime - dt); this.settle = Math.max(0, (this.settle || 0) - dt);
      const pat = this.patTime ? Math.sin((1 - this.patTime / .95) * Math.PI) : 0;
      const settling = this.settle ? Math.sin((1 - this.settle / .55) * Math.PI) * 1.6 : 0;
      const desired = this.target + Math.sin(this.time * 1.12) * .65 - pat * 4 + settling;
      this.angle += (desired - this.angle) * (1 - Math.exp(-7 * dt));
      let frame = s.lastFrame < 0 ? 0 : s.lastFrame;
      if (this.patTime > .20 && this.patTime < .82 && s.anim.animation === 'idle') frame = 68;
      else if (this.patTime > 0 && s.anim.animation === 'idle') frame = Math.floor(s.elapsed * s.anim.fps / 1000) % s.anim.frames.length;
      s.lastFrame = -1; this.baseDraw(frame); this.decorate();
      const breath = Math.sin(this.time * 1.8) * .0025;
      const bounce = -s.size * .025 * pat;
      s.canvas.style.transformOrigin = '50% 96%';
      s.canvas.style.transform = `translateY(${bounce}px) scale(${1 - breath * .3},${1 + breath})`;
      this.raf = requestAnimationFrame(t => this.tick(t));
    }
    destroy() { this.stop(); this.reset(); this.listeners.forEach(fn => fn()); this.s.draw = this.baseDraw; this.raw.width = this.raw.height = 0; }
  }
  global.InkScoutPresence = InkScoutPresence;
})(window);
