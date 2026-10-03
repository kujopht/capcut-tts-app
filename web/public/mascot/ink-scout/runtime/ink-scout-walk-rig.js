/* Continuous cutout gait. Two-bone legs, level planted soles, independent views. */
(function (global) {
  'use strict';
  const tau = Math.PI * 2, mix = (a, b, t) => a + (b - a) * t;
  class InkScoutWalkRig {
    constructor(s, spec) {
      this.s = s; this.spec = spec; this.parts = {};
      this.ready = Promise.all(Object.entries(spec.parts).map(async ([name, part]) => {
        const image = await s.image(part.image);
        this.parts[name] = { ...part, image };
      }));
    }
    paint(ctx, name, x, y, angle = 0) {
      const p = this.parts[name]; if (!p) return;
      ctx.save(); ctx.translate(x, y); ctx.rotate(angle);
      ctx.drawImage(p.image, -p.pivot[0], -p.pivot[1]); ctx.restore();
    }
    bone(ctx, name, a, b) {
      const p = this.parts[name];
      const rest = Math.atan2(p.end[1] - p.pivot[1], p.end[0] - p.pivot[0]);
      this.paint(ctx, name, a.x, a.y, Math.atan2(b.y - a.y, b.x - a.x) - rest);
    }
    pose(phase, stride = 120, weight = 1) {
      const dir = this.spec.direction === 'left' ? -1 : 1;
      const q = ((phase % 1) + 1) % 1;
      const bob = 2.2 * Math.sin(tau * q) ** 2 * weight;
      const hipY = this.spec.hipY - bob;
      const legs = {};
      for (const [name, offset] of [['near', 0], ['far', .5]]) {
        const p = (q + offset) % 1, swing = p >= .5;
        const t = swing ? (p - .5) * 2 : 0;
        // Quintic swing matches stance velocity and acceleration at both ends.
        // A cosine swing starts with a velocity jump and looks like a kick.
        const travel = swing ? stride * (-.25 - .5 * t + 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5) : stride * (.25 - p);
        const lift = swing ? 13 * Math.sin(Math.PI * t) ** 3 : 0;
        const hip = { x: 160 + (name === 'near' ? -4 : 4), y: hipY };
        const boot = this.parts[name + '-boot'];
        const foot = { x: hip.x + dir * travel * weight, y: 307 - lift * weight };
        const ankle = { x: foot.x, y: foot.y - (boot.image.height - boot.pivot[1]) };
        const thigh = this.parts[name + '-thigh'], shin = this.parts[name + '-shin'];
        const l1 = Math.hypot(thigh.end[0] - thigh.pivot[0], thigh.end[1] - thigh.pivot[1]);
        const l2 = Math.hypot(shin.end[0] - shin.pivot[0], shin.end[1] - shin.pivot[1]);
        const dx = ankle.x - hip.x, dy = ankle.y - hip.y;
        const distance = Math.max(.01, Math.min(Math.hypot(dx, dy), l1 + l2 - .05));
        const ax = dx / Math.hypot(dx, dy), ay = dy / Math.hypot(dx, dy);
        const along = (l1 * l1 - l2 * l2 + distance * distance) / (2 * distance);
        const bend = Math.sqrt(Math.max(0, l1 * l1 - along * along));
        const knee = { x: hip.x + ax * along + dir * ay * bend, y: hip.y + ay * along - dir * ax * bend };
        legs[name] = { hip, knee, ankle, foot, phase: p, planted: !swing,
          bootAngle: swing ? -dir * .10 * Math.sin(tau * t) * weight : 0,
          armAngle: dir * .19 * Math.cos(tau * p) * weight };
      }
      return { hipY, bob, legs, weight };
    }
    render(ctx, phase, stride = 120, weight = 1) {
      const pose = this.pose(phase, stride, weight), legs = pose.legs;
      ctx.clearRect(0, 0, 320, 320);
      const drawLeg = name => {
        const leg = legs[name];
        this.bone(ctx, name + '-thigh', leg.hip, leg.knee);
        this.bone(ctx, name + '-shin', leg.knee, leg.ankle);
        this.paint(ctx, name + '-boot', leg.ankle.x, leg.ankle.y, leg.bootAngle);
      };
      const shoulders = this.spec.shoulders;
      this.paint(ctx, 'far-arm', shoulders.far[0], shoulders.far[1] - pose.bob, legs.far.armAngle);
      drawLeg('far'); drawLeg('near');
      this.paint(ctx, 'body', 160, pose.hipY);
      this.paint(ctx, 'near-arm', shoulders.near[0], shoulders.near[1] - pose.bob, legs.near.armAngle);
      return pose;
    }
  }
  global.InkScoutWalkRig = InkScoutWalkRig;
})(window);
