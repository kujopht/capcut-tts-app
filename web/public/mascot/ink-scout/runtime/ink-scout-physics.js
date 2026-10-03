/* Bounded directional gait, pickup and spring landing. No autonomous roaming. */
(function (global) {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = t => t * t * (3 - 2 * t);
  class InkScoutPhysics {
    constructor(s, { surfaces = () => [] } = {}) {
      if (!s.manifest.physics?.poses) throw new Error('Load the current mascot manifest before enabling physics.');
      this.s = s; this.surfaces = surfaces; this.enabled = true;
      this.mode = null; this.epoch = 0; this.raf = 0; this.images = {}; this.handlers = []; this.rigs = {};
      this.base = { transition: s.transition.bind(s), cancel: s.cancelMotion.bind(s), destroy: s.destroy.bind(s) };
      s.transition = (n, o = {}) => ['hop-left', 'hop-right', 'jump-onto-panel', 'walk', 'walk-left', 'walk-right', 'return-home'].includes(n) ? this.transition(n, o) : this.base.transition(n, o);
      s.cancelMotion = () => { this.cancel(true); this.base.cancel(); };
      s.destroy = () => { this.destroy(); this.base.destroy(); };
      s.host.style.touchAction = 'none'; s.host.style.cursor = 'grab'; s.host.tabIndex = 0;
      s.host.setAttribute('aria-label', 'Drag Ink Scout. Space to pick up or drop; arrow keys to move.');
      const on = (el, n, fn) => { el.addEventListener(n, fn); this.handlers.push(() => el.removeEventListener(n, fn)); };
      on(s.host, 'pointerdown', e => {
        if (!this.enabled || s.paused || e.button !== 0 || this.pointer != null) return;
        e.preventDefault(); this.pickup(); this.pointer = e.pointerId;
        this.last = { x: e.clientX, y: e.clientY, t: performance.now() };
        s.host.setPointerCapture(e.pointerId);
      });
      on(s.host, 'pointermove', e => {
        if (e.pointerId !== this.pointer || this.mode !== 'drag') return;
        const now = performance.now(), dt = Math.max(.008, (now - this.last.t) / 1000);
        const dx = e.clientX - this.last.x, dy = e.clientY - this.last.y;
        s.position = s.constrain({ x: s.position.x + dx, y: s.position.y + dy }); s.applyPosition();
        this.vx = this.vx * .45 + dx / dt * .55; this.vy = this.vy * .45 + dy / dt * .55;
        this.last = { x: e.clientX, y: e.clientY, t: now };
      });
      const release = e => {
        if (e.pointerId !== this.pointer) return;
        this.pointer = null;
        if (s.host.hasPointerCapture(e.pointerId)) s.host.releasePointerCapture(e.pointerId);
        this.drop(e.type !== 'pointerup' || performance.now() - this.last.t > 90);
      };
      on(s.host, 'pointerup', release); on(s.host, 'pointercancel', release); on(s.host, 'lostpointercapture', release);
      on(window, 'blur', () => { if (this.mode === 'drag') { this.releasePointer(); this.drop(true); } });
      on(s.host, 'keydown', e => {
        if (!this.enabled || s.paused) return;
        if (e.code === 'Space') { e.preventDefault(); this.mode === 'drag' ? this.drop(true) : this.pickup(); }
        else if (this.mode === 'drag' && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Escape'].includes(e.key)) {
          e.preventDefault();
          if (e.key === 'Escape') this.drop(true);
          else { s.position = s.constrain({ x: s.position.x + (e.key === 'ArrowRight' ? 16 : e.key === 'ArrowLeft' ? -16 : 0), y: s.position.y + (e.key === 'ArrowDown' ? 16 : e.key === 'ArrowUp' ? -16 : 0) }); s.applyPosition(); }
        }
      });
      this.ready = Promise.all(Object.entries(s.manifest.physics.poses).map(async ([n, p]) => { this.images[n] = await s.image(p); }));
    }
    support(x, y = -Infinity) {
      const s = this.s, c = x + s.size / 2;
      return [...this.surfaces(), { left: -Infinity, right: Infinity, y: s.bounds.bottom }]
        .filter(p => c >= p.left && c <= p.right && p.y >= y - .5).sort((a, b) => a.y - b.y)[0]?.y ?? s.bounds.bottom;
    }
    visual(angle = 0, sx = 1, sy = 1, lift = 0) {
      this.s.canvas.style.transformOrigin = this.mode === 'drag' ? '50% 24%' : '50% 96%';
      this.s.canvas.style.transform = `translateY(${lift}px) rotate(${angle}deg) scale(${sx},${sy})`;
    }
    pose(n) {
      if (!this.images[n] || (this.poseName === n && this.s.anim?.image === this.images[n])) return;
      this.poseName = n; this.s.stopClock();
      this.s.anim = { image: this.images[n], static: true, complete: true };
      this.s.lastFrame = -1; this.s.draw(0);
    }
    releasePointer() {
      const pointer = this.pointer; this.pointer = null;
      if (pointer != null && this.s.host.hasPointerCapture(pointer)) this.s.host.releasePointerCapture(pointer);
    }
    cancel(snap = false) {
      const wasActive = !!this.mode; ++this.epoch;
      cancelAnimationFrame(this.raf); this.raf = 0; this.mode = null;
      this.releasePointer(); this.visual(); this.s.host.style.cursor = 'grab';
      if (this.resolve) { this.resolve({ cancelled: true }); this.resolve = null; }
      if (snap && wasActive) { this.s.position.y = this.support(this.s.position.x, this.s.position.y - this.s.seatOffset); this.s.seatOffset = 0; this.s.applyPosition(); }
    }
    pickup() {
      this.cancel(); this.base.cancel(); ++this.s.token; this.s.seatOffset = 0;
      this.mode = 'drag'; this.vx = this.vy = this.angle = this.angular = 0;
      this.s.host.style.cursor = 'grabbing'; const epoch = this.epoch;
      this.ready.then(() => { if (epoch === this.epoch && this.mode === 'drag') this.pose('picked-up'); });
      this.s.event('pickup', {}); this.start();
    }
    drop(zero = false) {
      if (this.mode !== 'drag') return;
      this.releasePointer(); this.s.host.style.cursor = 'grab'; this.mode = 'fall'; this.name = 'drop';
      this.vx = zero ? 0 : clamp(this.vx, -600, 600); this.vy = zero ? 0 : clamp(this.vy, -500, 700);
      this.bounces = 0; this.pose('jump-airborne'); this.visual();
      if (this.s.reducedMotion) { this.s.position.y = this.support(this.s.position.x, this.s.position.y); this.finish(); }
      else this.start();
    }
    async transition(name, o = {}) {
      this.cancel(); this.base.cancel();
      if (this.s.seatOffset) { this.s.position.y -= this.s.seatOffset; this.s.seatOffset = 0; }
      const epoch = this.epoch; await this.ready;
      if (epoch !== this.epoch || this.s.destroyed) return { cancelled: true };
      const s = this.s; ++s.token; this.from = { ...s.position }; this.to = { ...s.position }; this.name = name;
      const walking = name.startsWith('walk') || (name === 'return-home' && Math.abs(s.position.y - s.home.y) < .5);
      const left = name === 'walk-left' || name === 'hop-left' || o.direction === 'left';
      if (name === 'return-home') this.to = { ...s.home };
      else if (name === 'jump-onto-panel') this.to = s.constrain({ x: o.x, y: o.y });
      else this.to.x += (left ? -1 : 1) * (walking ? clamp(+o.distance || 180, 100, 300) : clamp(+o.distance || 78, 16, 100));
      this.to = s.constrain(this.to);
      if (name !== 'jump-onto-panel' && name !== 'return-home') this.to.y = this.support(this.to.x, this.from.y);
      this.t = 0; this.walkVy = 0; this.mode = walking ? 'walk' : 'jump';
      this.direction = this.to.x < this.from.x || (this.to.x === this.from.x && left) ? 'left' : 'right';
      const distance = Math.abs(this.to.x - this.from.x);
      if (walking && distance < .5) {
        const reason = name === 'return-home' ? 'home' : 'edge';
        this.finish(reason);
        return { cancelled: false, reason, position: { ...s.position } };
      }
      this.ramp = .22;
      this.duration = walking ? distance / (s.size * .50) + this.ramp : .82;
      this.arc = Math.min(s.size * .60, Math.max(0, Math.min(this.from.y, this.to.y) - s.bounds.top));
      if (s.reducedMotion) { s.position = { ...this.to }; this.finish(); return { cancelled: false, position: { ...s.position } }; }
      if (walking) {
        // Direction-specific art; the gait is driven by distance rather than a clock.
        this.walkAnimation = s.manifest.physics.walkCycles?.[this.direction] || 'walk';
        const started = await s.play(this.walkAnimation, { hold: true });
        if (!started || epoch !== this.epoch) return { cancelled: true };
        s.stopClock(); s.anim.complete = true; this.walkSpec = s.anim;
        this.walkRig = null;
        if (global.InkScoutWalkRig && this.walkSpec.rig) {
          const rig = this.rigs[this.direction] ||= new global.InkScoutWalkRig(s, this.walkSpec.rig);
          let loaded = true;
          try { await rig.ready; }
          catch (error) {
            loaded = false; delete this.rigs[this.direction];
            s.event('assetfallback', { animation: this.walkAnimation, error });
          }
          if (epoch !== this.epoch || s.destroyed) return { cancelled: true };
          if (loaded) this.walkRig = rig;
        }
        // End on a passing pose: the planted foot is centered under the hip,
        // so the other foot can lower gently without a final sliding half-step.
        const nominalStride = (this.walkSpec.strideAt128Px || 40) * s.size / 128;
        this.steps = Math.max(1, Math.ceil(distance / nominalStride));
        this.stride = distance / this.steps;
        this.gait = .25; this.gaitWeight = 0; this.mode = 'walk'; this.s.event('directionchange', { direction: this.direction, animation: this.walkAnimation });
      } else this.pose('jump-anticipation');
      const result = new Promise(r => this.resolve = r); this.start(); return result;
    }
    start() {
      if (this.raf || !this.mode) return;
      this.lastTime = null; this.raf = requestAnimationFrame(t => this.tick(t));
    }
    finish(reason = null) {
      const resolve = this.resolve; this.resolve = null; const name = this.name;
      this.mode = null; this.visual(); this.s.applyPosition();
      this.s.setState('idle').catch(e => this.s.report(e));
      resolve?.({ cancelled: false, position: { ...this.s.position } });
      this.s.event('movementcomplete', { name, direction: this.direction, reason, position: { ...this.s.position } });
    }
    drawGait() {
      const count = this.walkSpec.cycleFrames || this.walkSpec.frames.length;
      if (this.walkRig) {
        this.gaitPose = this.walkRig.render(this.s.ctx, this.gait, this.stride * 320 / this.s.size, this.gaitWeight);
        this.s.lastFrame = Math.floor(this.gait * count) % count;
      } else this.s.draw(Math.floor(this.gait * count) % count);
    }
    tick(now) {
      this.raf = 0; if (!this.mode || this.s.destroyed) return;
      const s = this.s, dt = this.lastTime == null ? 0 : Math.min(.032, (now - this.lastTime) / 1000);
      this.lastTime = now;
      if (!s.paused && !document.hidden && s.visible) {
        if (this.mode === 'drag') {
          const target = s.reducedMotion ? 0 : clamp(this.vx * .025, -22, 22);
          this.angular += (target - this.angle) * 100 * dt; this.angular *= Math.exp(-12 * dt); this.angle += this.angular * dt;
          this.vx *= Math.exp(-7 * dt); this.visual(this.angle, 1, 1.025);
        } else if (this.mode === 'jump') {
          this.t += dt; const t = this.t;
          if (t < .12) { this.pose('jump-anticipation'); const a = .1 * Math.sin(t / .12 * Math.PI); this.visual(0, 1 + a, 1 - a); }
          else if (t < .72) {
            const u = (t - .12) / .60; this.pose('jump-airborne');
            s.position = s.constrain({ x: this.from.x + (this.to.x - this.from.x) * u, y: this.from.y + (this.to.y - this.from.y) * u - 4 * this.arc * u * (1 - u) });
            this.visual((this.to.x - this.from.x) * .035 * Math.sin(Math.PI * u));
          } else { s.position = s.constrain(this.to); this.mode = 'land'; this.t = 0; this.pose('jump-landing'); }
          s.applyPosition();
        } else if (this.mode === 'walk') {
          this.t += dt;
          const prep = .16, elapsed = clamp(this.t - prep, 0, this.duration);
          const r = this.ramp, total = this.duration;
          const rampDistance = t => .5 * (t - r / Math.PI * Math.sin(Math.PI * t / r));
          let traveled;
          if (elapsed < r) traveled = rampDistance(elapsed);
          else if (elapsed > total - r) traveled = total - r - rampDistance(total - elapsed);
          else traveled = elapsed - r / 2;
          const progress = clamp(traveled / (total - r), 0, 1);
          const x = this.from.x + (this.to.x - this.from.x) * progress;
          this.gait = .25 + Math.abs(x - this.from.x) / this.stride;
          this.gaitWeight = smooth(clamp(this.t / prep, 0, 1));
          s.position.x = clamp(x, s.bounds.left, s.bounds.right);
          const floor = this.support(s.position.x, s.position.y);
          if (s.position.y < floor) { this.walkVy += 1500 * dt; s.position.y = Math.min(floor, s.position.y + this.walkVy * dt); } else this.walkVy = 0;
          // Never rotate/squash planted feet with a whole-canvas transform.
          this.visual();
          this.drawGait(); s.applyPosition();
          if (elapsed === total) { this.mode = 'walk-settle'; this.t = 0; this.settleGait = this.gait; this.settleY = s.position.y; }
        } else if (this.mode === 'walk-settle') {
          this.t += dt; const u = clamp(this.t / .20, 0, 1);
          this.gait = this.settleGait; this.gaitWeight = 1 - smooth(u);
          this.drawGait(); this.visual();
          const floor = this.support(s.position.x, this.settleY);
          if (s.position.y < floor) { this.walkVy += 1500 * dt; s.position.y = Math.min(floor, s.position.y + this.walkVy * dt); }
          s.applyPosition(); if (u === 1 && s.position.y >= floor - .5) this.finish();
        } else if (this.mode === 'fall') {
          for (let rem = dt; rem > 0;) {
            const h = Math.min(rem, 1 / 120); rem -= h; const oldY = s.position.y;
            this.vy += 1500 * h; s.position.x += this.vx * h; s.position.y += this.vy * h;
            if (s.position.x < s.bounds.left || s.position.x > s.bounds.right) { s.position.x = clamp(s.position.x, s.bounds.left, s.bounds.right); this.vx *= -.25; }
            if (s.position.y < s.bounds.top) { s.position.y = s.bounds.top; this.vy = Math.max(0, this.vy); }
            const ground = this.support(s.position.x, oldY);
            if (this.vy > 0 && s.position.y >= ground) {
              s.position.y = ground;
              if (this.bounces++ === 0 && this.vy > 280) { this.vy *= -.22; this.vx *= .5; }
              else { this.mode = 'land'; this.t = 0; this.pose('jump-landing'); this.vx = this.vy = 0; break; }
            }
          }
          this.visual(clamp(this.vx * .012, -10, 10)); s.applyPosition();
        } else if (this.mode === 'land') {
          this.t += dt; const a = Math.sin(clamp(this.t / .20, 0, 1) * Math.PI) * .12;
          this.visual(0, 1 + a, 1 - a); if (this.t >= .20) this.finish();
        }
      }
      if (this.mode) this.raf = requestAnimationFrame(t => this.tick(t));
    }
    destroy() { this.cancel(); this.handlers.forEach(fn => fn()); this.images = {}; this.rigs = {}; }
  }
  global.InkScoutPhysics = InkScoutPhysics;
})(window);
