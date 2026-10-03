/* Ink Scout raster player. No third-party runtime dependency. */
(function (global) {
  'use strict';
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const ease = t => t * t * (3 - 2 * t);
  class InkScout {
    constructor(host, options = {}) {
      if (!(host instanceof HTMLElement)) throw new TypeError('A host element is required.');
      this.host = host;
      this.manifest = options.manifest || global.INK_SCOUT_MANIFEST;
      if (!this.manifest) throw new Error('Pass manifest, or load mascot/manifest.js first.');
      this.base = new URL(options.assetBase || 'mascot/', document.baseURI);
      this.size = clamp(Number(options.size) || 128, 64, 320);
      this.position = { x: 0, y: 0 };
      this.seatOffset = 0;
      this.home = { x: 0, y: 0 };
      this.bounds = options.bounds || { left: -300, right: 300, top: -200, bottom: 0 };
      this.cache = new Map();
      this.pending = new Map();
      this.token = 0;
      this.state = 'idle';
      this.anim = null;
      this.raf = 0;
      this.destroyed = false;
      this.visible = true;
      this.paused = false;
      this.elapsed = 0;
      this.lastTime = null;
      this.lastFrame = -1;
      this.motion = null;
      this.reducedOverride = null;
      this.media = matchMedia('(prefers-reduced-motion: reduce)');
      this.host.classList.add('ink-scout');
      this.host.style.cssText += `;width:${this.size}px;height:${this.size}px;display:block;position:relative;`;
      this.canvas = document.createElement('canvas');
      this.canvas.width = this.canvas.height = 320;
      this.canvas.style.cssText = 'display:block;width:100%;height:100%;';
      this.canvas.setAttribute('role', 'img');
      this.canvas.setAttribute('aria-label', 'Ink Scout, Fanfic World assistant: idle');
      this.host.append(this.canvas);
      this.ctx = this.canvas.getContext('2d');
      this.ctx.imageSmoothingEnabled = true;
      this.ctx.imageSmoothingQuality = 'high';
      this.onMedia = () => this.setState(this.state).catch(e => this.report(e));
      this.onVisibility = () => {
        this.lastTime = null;
        if (document.hidden) this.stopClock(); else this.startClock();
      };
      this.media.addEventListener('change', this.onMedia);
      document.addEventListener('visibilitychange', this.onVisibility);
      this.observer = new IntersectionObserver(entries => {
        this.visible = entries[0]?.isIntersecting !== false;
        this.lastTime = null;
        if (this.visible) this.startClock(); else this.stopClock();
      });
      this.observer.observe(host);
      this.ready = this.setState(options.state || 'idle');
    }

    get reducedMotion() { return this.reducedOverride ?? this.media.matches; }
    report(error) { this.host.dispatchEvent(new CustomEvent('mascoterror', { detail: error })); }
    event(name, detail) { this.host.dispatchEvent(new CustomEvent(name, { detail })); }
    url(path) {
      const url = new URL(path, this.base);
      if (this.manifest.version) url.searchParams.set('v', this.manifest.version);
      return url.href;
    }

    async image(path, fallback) {
      if (this.cache.has(path)) {
        const value = this.cache.get(path);
        this.cache.delete(path); this.cache.set(path, value); return value;
      }
      if (this.pending.has(path)) return this.pending.get(path);
      const load = async () => {
        const img = new Image();
        img.decoding = 'async';
        try {
          await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = () => reject(new Error(`Unable to load ${path}`));
            img.src = this.url(path);
          });
        } catch (error) {
          if (fallback) return this.image(fallback);
          throw error;
        }
        if (!this.destroyed) {
          this.cache.set(path, img);
          while (this.cache.size > 3) this.cache.delete(this.cache.keys().next().value);
        }
        return img;
      };
      const promise = load().finally(() => this.pending.delete(path));
      this.pending.set(path, promise);
      return promise;
    }

    cancelMotion() {
      if (this.motion) {
        this.motion.resolve({ cancelled: true, position: { ...this.position } });
        this.motion = null;
      }
    }

    async setState(state) {
      if (this.destroyed) return false;
      const spec = this.manifest.states[state];
      if (!spec) throw new RangeError(`Unknown mascot state: ${state}`);
      const token = ++this.token;
      this.cancelMotion();
      this.stopClock();
      if (this.seatOffset) {
        this.position = this.constrain({ x: this.position.x, y: this.position.y - this.seatOffset });
        this.seatOffset = 0; this.applyPosition();
      }
      if (this.anim) this.anim.complete = true;
      this.state = state;
      this.canvas.setAttribute('aria-label', `Ink Scout, Fanfic World assistant: ${state}`);
      try {
        const image = await this.image(this.reducedMotion ? spec.static : spec.image, this.reducedMotion ? null : spec.png);
        if (this.destroyed || token !== this.token) return false;
        this.anim = { ...spec, image, static: this.reducedMotion, complete: false };
        this.elapsed = 0; this.lastTime = null; this.lastFrame = -1;
        this.draw(0);
        this.event('statechange', { state });
        this.startClock();
        return true;
      } catch (error) {
        if (token === this.token) this.report(error);
        throw error;
      }
    }

    async play(name, { loop = true, hold = false } = {}) {
      if (this.destroyed) return false;
      const spec = this.manifest.animations[name];
      if (!spec) throw new RangeError(`Unknown mascot animation: ${name}`);
      const token = ++this.token;
      this.stopClock();
      if (this.anim) this.anim.complete = true;
      const image = await this.image(this.reducedMotion ? spec.poster : spec.image, this.reducedMotion ? null : spec.png);
      if (this.destroyed || token !== this.token) return false;
      this.anim = { ...spec, animation: name, image, static: this.reducedMotion, playback: hold ? 'hold' : loop ? 'loop' : 'once', after: null, complete: false };
      this.elapsed = 0; this.lastTime = null; this.lastFrame = -1;
      this.draw(0); this.startClock(); return true;
    }

    draw(frame) {
      if (!this.anim || (frame === this.lastFrame && !this.anim.static)) return;
      this.ctx.clearRect(0, 0, 320, 320);
      if (this.anim.static) this.ctx.drawImage(this.anim.image, 0, 0, 320, 320);
      else {
        const rect = this.anim.frames[frame] || this.anim.frames[0];
        this.ctx.drawImage(this.anim.image, rect.x, rect.y, rect.w, rect.h, 0, 0, 320, 320);
      }
      this.lastFrame = frame;
    }

    startClock() {
      if (this.raf || this.destroyed || this.paused || !this.visible || document.hidden) return;
      if (!this.motion && (!this.anim || this.anim.static || this.anim.complete)) return;
      this.raf = requestAnimationFrame(t => this.tick(t));
    }
    stopClock() { cancelAnimationFrame(this.raf); this.raf = 0; this.lastTime = null; }
    tick(now) {
      this.raf = 0;
      if (this.destroyed || this.paused || document.hidden || !this.visible) return;
      const dt = this.lastTime === null ? 0 : Math.min(80, now - this.lastTime);
      this.lastTime = now;
      this.elapsed += dt;
      if (this.anim && !this.anim.static && !this.anim.complete) {
        const n = this.anim.frames.length;
        let frame = Math.floor(this.elapsed * this.anim.fps / 1000);
        if (this.anim.playback === 'loop') frame %= n;
        else if (this.anim.playback === 'hold') { frame = 0; this.anim.complete = true; }
        else if (frame >= n) {
          frame = n - 1; this.anim.complete = true;
          const after = this.anim.after;
          this.event('animationcomplete', { state: this.state });
          if (after && !this.motion) this.setState(after).catch(e => this.report(e));
        }
        this.draw(frame);
      }
      if (this.motion) {
        const m = this.motion;
        m.elapsed += dt;
        const t = clamp(m.elapsed / m.duration, 0, 1), progress = m.linear ? t : ease(t);
        this.position = {
          x: m.from.x + (m.to.x - m.from.x) * progress,
          y: m.from.y + (m.to.y - m.from.y) * progress - Math.sin(Math.PI * t) * m.arc
        };
        this.applyPosition();
        if (t === 1) {
          this.motion = null;
          this.position = { ...m.to }; this.applyPosition();
          m.resolve({ cancelled: false, position: { ...this.position } });
          this.event('movementcomplete', { name: m.name, position: { ...this.position } });
        }
      }
      this.startClock();
    }

    applyPosition() { this.host.style.transform = `translate(${this.position.x}px, ${this.position.y}px)`; }
    constrain(point) {
      return { x: clamp(Number(point.x) || 0, this.bounds.left, this.bounds.right), y: clamp(Number(point.y) || 0, this.bounds.top, this.bounds.bottom) };
    }
    setBounds(bounds) {
      this.bounds = { ...this.bounds, ...bounds };
      this.position = this.constrain(this.position);
      if (this.motion) { this.motion.from = { ...this.position }; this.motion.to = this.constrain(this.motion.to); this.motion.elapsed = 0; }
      this.applyPosition();
    }
    setSize(size) {
      this.size = clamp(Number(size) || 128, 64, 320);
      this.host.style.width = this.host.style.height = `${this.size}px`;
    }
    setReducedMotion(value = null) { this.reducedOverride = value; return this.setState(this.state); }
    setPaused(value) { this.paused = !!value; this.lastTime = null; if (this.paused) this.stopClock(); else this.startClock(); }

    async transition(name, options = {}) {
      if (this.destroyed) return { cancelled: true };
      if (!this.manifest.transitions[name]) throw new RangeError(`Unknown transition: ${name}`);
      this.cancelMotion();
      this.canvas.setAttribute('aria-label', `Ink Scout: ${name.replaceAll('-', ' ')}`);
      if (this.seatOffset && name !== 'stand-up' && name !== 'sit-down') {
        this.position.y -= this.seatOffset; this.seatOffset = 0; this.applyPosition();
      }
      const from = { ...this.position };
      let to = { ...from }, arc = 0, duration = 650, animation = name;
      const walking = name === 'walk' || name === 'walk-left' || name === 'walk-right';
      if (walking) {
        const distance = clamp(Math.abs(Number(options.distance) || 180), 100, 300);
        const direction = name === 'walk-left' || options.direction === 'left' ? 'left' : 'right';
        to.x += (direction === 'left' ? -1 : 1) * distance;
        animation = this.manifest.physics?.walkCycles?.[direction] || name;
        duration = distance / 95 * 1000;
      } else if (name === 'hop-left' || name === 'hop-right') {
        to.x += (name === 'hop-left' ? -1 : 1) * clamp(Number(options.distance) || 64, 16, 100);
        arc = 26; duration = 520;
      } else if (name === 'jump-onto-panel') {
        to = { x: Number(options.x) || 0, y: Number(options.y) || -90 };
        arc = 42; duration = 850;
      } else if (name === 'return-home') {
        to = { ...this.home }; duration = Math.max(350, Math.hypot(from.x, from.y) / 130 * 1000);
      } else if (name === 'sit-down' || name === 'stand-up') {
        duration = 1000;
        if (name === 'sit-down' && !this.seatOffset && from.y < 0) to.y += this.size * .19;
        if (name === 'stand-up') to.y -= this.seatOffset;
      } else if (name === 'peek-out') {
        duration = 600;
      }
      to = this.constrain(to);
      // Keep the whole canvas within the host's explicitly supplied bounds.
      arc = Math.min(arc, Math.max(0, Math.min(from.y, to.y) - this.bounds.top));
      const started = await this.play(animation, { loop: walking || name === 'return-home' });
      if (!started) return { cancelled: true };
      const token = this.token;
      if (this.reducedMotion) {
        this.position = to; this.applyPosition();
        this.seatOffset = name === 'sit-down' ? to.y - from.y : 0;
        if (name === 'sit-down') await this.showPose('sitting-edge');
        else if (name === 'peek-out') await this.showPose('peeking');
        else await this.setState('idle');
        this.event('movementcomplete', { name, position: { ...to } });
        return { cancelled: false, position: to };
      }
      const outcome = await new Promise(resolve => {
        this.motion = { name, from, to, arc, duration, elapsed: 0, resolve, linear: walking || name === 'return-home' };
        this.startClock();
      });
      if (!outcome.cancelled && token === this.token) {
        this.seatOffset = name === 'sit-down' ? to.y - from.y : 0;
        if (name === 'sit-down') { this.anim.complete = true; this.draw(this.anim.frames.length - 1); this.stopClock(); }
        else if (name === 'peek-out') await this.showPose('peeking');
        else await this.setState('idle');
      }
      return outcome;
    }

    async showPose(name) {
      const path = this.manifest.poses[name]?.webp;
      if (!path) throw new RangeError(`Unknown pose: ${name}`);
      const token = ++this.token;
      const image = await this.image(path);
      if (this.destroyed || token !== this.token) return;
      this.anim = { image, static: true, complete: true };
      this.lastFrame = -1; this.draw(0); this.stopClock();
    }

    destroy() {
      this.destroyed = true; ++this.token;
      this.cancelMotion(); this.stopClock(); this.observer.disconnect();
      this.media.removeEventListener('change', this.onMedia);
      document.removeEventListener('visibilitychange', this.onVisibility);
      this.cache.clear(); this.canvas.remove(); this.host.classList.remove('ink-scout');
    }
  }
  global.InkScout = InkScout;
})(window);
