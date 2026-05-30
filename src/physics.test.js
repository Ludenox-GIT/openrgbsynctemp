import { describe, it, expect } from 'vitest';

// Pure physics functions for testing
function calculateGravityForce(m1, m2, dist, G = 0.15, isAntigravity = false) {
  const distSq = dist * dist + 100; // soft factor
  let force = (G * m1 * m2) / distSq;
  return isAntigravity ? -force : force;
}

function calculateCircularVelocity(sunMass, r, G = 0.15) {
  return Math.sqrt((G * sunMass) / r);
}

describe('Newtonian Physics Calculator', () => {
  it('calculates gravity force correctly', () => {
    // Normal gravity
    const force = calculateGravityForce(10, 100, 50, 0.15, false);
    const expected = (0.15 * 10 * 100) / (50 * 50 + 100);
    expect(force).toBeCloseTo(expected, 5);
  });

  it('calculates antigravity force correctly (repellor)', () => {
    // Antigravity (repulsive)
    const force = calculateGravityForce(10, 100, 50, 0.15, true);
    const expected = -((0.15 * 10 * 100) / (50 * 50 + 100));
    expect(force).toBeCloseTo(expected, 5);
  });

  it('calculates circular orbit velocity correctly', () => {
    const v = calculateCircularVelocity(10000, 200, 0.15);
    const expected = Math.sqrt((0.15 * 10000) / 200);
    expect(v).toBeCloseTo(expected, 5);
    expect(v).toBe(Math.sqrt(7.5));
  });
});
