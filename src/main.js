/**
 * Delightful Newton - Gravity & Antigravity Simulator
 * Core Physics Engine and UI Binder
 */

// Simulation Configuration & State
const state = {
  // Simulator Parameters
  particleCount: 150,
  gravityConstant: 0.15,
  timeSpeed: 1.0,
  theme: 'cosmic',
  showOrbits: true,
  showVectors: false,
  enableCollisions: true,
  isAntigravity: false,
  
  // Interactive State
  activePreset: 'solar',
  isDragging: false,
  mousePos: { x: 0, y: 0 },
  mouseMass: 200,
  
  // Render loop tracking
  fps: 60,
  msCost: 0,
  lastTime: performance.now(),
  framesThisSecond: 0,
  fpsTimer: 0,
};

// Color Theme Definitions (HSL)
const themes = {
  cosmic: {
    bg: '#080914',
    particleColors: ['hsl(190, 80%, 50%)', 'hsl(250, 85%, 65%)', 'hsl(290, 80%, 60%)', 'hsl(330, 85%, 55%)'],
    centerColor: 'hsl(50, 95%, 65%)',
    trailColor: 'rgba(8, 9, 20, 0.08)',
    vectorColor: 'rgba(255, 255, 255, 0.35)',
  },
  aurora: {
    bg: '#040d0a',
    particleColors: ['hsl(145, 75%, 45%)', 'hsl(165, 80%, 45%)', 'hsl(185, 85%, 45%)', 'hsl(200, 80%, 50%)'],
    centerColor: 'hsl(130, 90%, 70%)',
    trailColor: 'rgba(4, 13, 10, 0.08)',
    vectorColor: 'rgba(255, 255, 255, 0.3)',
  },
  solar: {
    bg: '#0f0602',
    particleColors: ['hsl(15, 85%, 55%)', 'hsl(30, 90%, 55%)', 'hsl(45, 95%, 55%)', 'hsl(0, 85%, 50%)'],
    centerColor: 'hsl(60, 100%, 75%)',
    trailColor: 'rgba(15, 6, 2, 0.08)',
    vectorColor: 'rgba(255, 255, 255, 0.35)',
  },
  monochrome: {
    bg: '#050505',
    particleColors: ['hsl(0, 0%, 50%)', 'hsl(0, 0%, 65%)', 'hsl(0, 0%, 80%)', 'hsl(0, 0%, 95%)'],
    centerColor: 'hsl(0, 0%, 100%)',
    trailColor: 'rgba(5, 5, 5, 0.1)',
    vectorColor: 'rgba(255, 255, 255, 0.4)',
  }
};

// Physics Body Class
class Body {
  constructor(x, y, vx, vy, radius, mass, color, isStatic = false) {
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.radius = radius;
    this.mass = mass;
    this.color = color;
    this.isStatic = isStatic;
    this.trail = [];
    this.maxTrailLength = 40;
  }

  update(dt) {
    if (this.isStatic) return;
    
    // Add position to trail
    if (state.showOrbits) {
      this.trail.push({ x: this.x, y: this.y });
      if (this.trail.length > this.maxTrailLength) {
        this.trail.shift();
      }
    } else {
      this.trail = [];
    }

    // Apply speed factor and delta time to position update
    this.x += this.vx * dt * state.timeSpeed;
    this.y += this.vy * dt * state.timeSpeed;
  }

  draw(ctx) {
    // Draw trail
    if (state.showOrbits && this.trail.length > 1) {
      ctx.beginPath();
      ctx.moveTo(this.trail[0].x, this.trail[0].y);
      for (let i = 1; i < this.trail.length; i++) {
        ctx.lineTo(this.trail[i].x, this.trail[i].y);
      }
      ctx.strokeStyle = this.color;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.15;
      ctx.stroke();
      ctx.globalAlpha = 1.0;
    }

    // Draw body
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
    ctx.fillStyle = this.color;
    
    // Make central/static stars glow
    if (this.isStatic) {
      ctx.shadowBlur = this.radius * 2;
      ctx.shadowColor = this.color;
    }
    
    ctx.fill();
    ctx.shadowBlur = 0; // Reset shadow

    // Draw velocity vector
    if (state.showVectors && !this.isStatic) {
      ctx.beginPath();
      ctx.moveTo(this.x, this.y);
      ctx.lineTo(this.x + this.vx * 3.5, this.y + this.vy * 3.5);
      ctx.strokeStyle = themes[state.theme].vectorColor;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      // Draw small arrow head
      const angle = Math.atan2(this.vy, this.vx);
      ctx.beginPath();
      ctx.moveTo(this.x + this.vx * 3.5, this.y + this.vy * 3.5);
      ctx.lineTo(
        this.x + this.vx * 3.5 - 5 * Math.cos(angle - Math.PI / 6),
        this.y + this.vy * 3.5 - 5 * Math.sin(angle - Math.PI / 6)
      );
      ctx.lineTo(
        this.x + this.vx * 3.5 - 5 * Math.cos(angle + Math.PI / 6),
        this.y + this.vy * 3.5 - 5 * Math.sin(angle + Math.PI / 6)
      );
      ctx.fillStyle = themes[state.theme].vectorColor;
      ctx.fill();
    }
  }
}

// Setup Canvas and Engine
const canvas = document.getElementById('simCanvas');
const ctx = canvas.getContext('2d');
let bodies = [];

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  // Clear with background color instantly
  ctx.fillStyle = themes[state.theme].bg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// Physics forces calculation
function applyGravitationalForces() {
  const G = state.gravityConstant;
  const isAntigravity = state.isAntigravity;

  for (let i = 0; i < bodies.length; i++) {
    const b1 = bodies[i];
    if (b1.isStatic) continue;

    let fx = 0;
    let fy = 0;

    // Gravity between bodies
    for (let j = 0; j < bodies.length; j++) {
      if (i === j) continue;
      const b2 = bodies[j];

      const dx = b2.x - b1.x;
      const dy = b2.y - b1.y;
      const distSq = dx * dx + dy * dy + 100; // Softening factor to prevent divide by zero
      const dist = Math.sqrt(distSq);

      // Force magnitude F = G * m1 * m2 / r^2
      // Direction points towards b2 (if gravity) or away (if antigravity)
      let forceMag = (G * b1.mass * b2.mass) / distSq;
      
      if (isAntigravity && !b2.isStatic) {
        // Reverse force for non-static bodies in antigravity mode
        forceMag = -forceMag;
      }

      // Decompose force into component vectors
      fx += (forceMag * dx) / dist;
      fy += (forceMag * dy) / dist;
    }

    // Interactive mouse gravity well / repeller
    if (state.isDragging) {
      const dx = state.mousePos.x - b1.x;
      const dy = state.mousePos.y - b1.y;
      const distSq = dx * dx + dy * dy + 200;
      const dist = Math.sqrt(distSq);

      let mouseForceMag = (G * b1.mass * state.mouseMass) / distSq;
      if (isAntigravity) {
        mouseForceMag = -mouseForceMag;
      }
      fx += (mouseForceMag * dx) / dist;
      fy += (mouseForceMag * dy) / dist;
    }

    // Acceleration a = F / m
    b1.vx += fx / b1.mass;
    b1.vy += fy / b1.mass;
  }
}

// Collisions resolution
function resolveCollisions() {
  if (!state.enableCollisions) return;

  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const b1 = bodies[i];
      const b2 = bodies[j];

      const dx = b2.x - b1.x;
      const dy = b2.y - b1.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const minDist = b1.radius + b2.radius;

      if (dist < minDist) {
        // Overlap depth
        const overlap = minDist - dist;

        // Decompose vectors
        const nx = dx / dist;
        const ny = dy / dist;

        // Push bodies apart (only if they aren't static)
        if (!b1.isStatic && !b2.isStatic) {
          b1.x -= nx * overlap * 0.5;
          b1.y -= ny * overlap * 0.5;
        } else if (!b1.isStatic) {
          b1.x -= nx * overlap;
          b1.y -= ny * overlap;
        } else if (!b2.isStatic) {
          b2.x += nx * overlap;
          b2.y += ny * overlap;
        }

        // Relative velocity
        const rvx = b2.vx - b1.vx;
        const rvy = b2.vy - b1.vy;

        // Velocity along normal
        const velAlongNormal = rvx * nx + rvy * ny;

        // Do not resolve if velocities are separating
        if (velAlongNormal < 0) {
          // Elasticity coefficient (rebound)
          const restitution = 0.85;

          // Impulse scalar
          let impulse = -(1 + restitution) * velAlongNormal;
          impulse /= (1 / b1.mass + 1 / b2.mass);

          // Apply impulse vector
          const ix = impulse * nx;
          const iy = impulse * ny;

          if (!b1.isStatic) {
            b1.vx -= ix / b1.mass;
            b1.vy -= iy / b1.mass;
          }
          if (!b2.isStatic) {
            b2.vx += ix / b2.mass;
            b2.vy += iy / b2.mass;
          }
        }
      }
    }
  }
}

// Spawning presets
function applyPreset(presetName) {
  state.activePreset = presetName;
  bodies = [];
  
  const width = canvas.width;
  const height = canvas.height;
  const cx = width / 2;
  const cy = height / 2;
  const currentTheme = themes[state.theme];

  switch (presetName) {
    case 'solar': {
      // Massive sun in center
      const sun = new Body(cx, cy, 0, 0, 32, 10000, currentTheme.centerColor, true);
      bodies.push(sun);

      // Orbital planets
      const count = state.particleCount;
      for (let i = 0; i < count; i++) {
        // Random distance from sun
        const r = 80 + Math.random() * (Math.min(width, height) / 2 - 100);
        const theta = Math.random() * Math.PI * 2;
        const px = cx + r * Math.cos(theta);
        const py = cy + r * Math.sin(theta);

        // Circular orbit velocity formula: v = sqrt(G * M / r)
        const vMag = Math.sqrt((state.gravityConstant * sun.mass) / r);
        // Direction perpendicular to position vector
        const vx = -vMag * Math.sin(theta);
        const vy = vMag * Math.cos(theta);

        const radius = 2 + Math.random() * 5;
        const mass = radius * radius;
        const color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];

        bodies.push(new Body(px, py, vx, vy, radius, mass, color));
      }
      break;
    }
    case 'binary': {
      // Two massive stars orbiting each other
      const orbitRadius = 100;
      const starMass = 8000;
      const starRadius = 24;
      
      // Calculate star orbital velocities
      const starV = Math.sqrt((state.gravityConstant * starMass) / (2 * orbitRadius));
      
      const star1 = new Body(cx - orbitRadius, cy, 0, -starV, starRadius, starMass, 'hsl(190, 95%, 65%)');
      const star2 = new Body(cx + orbitRadius, cy, 0, starV, starRadius, starMass, 'hsl(340, 95%, 65%)');
      bodies.push(star1, star2);

      // Dust clouds around binary stars
      const count = state.particleCount;
      for (let i = 0; i < count; i++) {
        const r = 160 + Math.random() * (Math.min(width, height) / 2 - 180);
        const theta = Math.random() * Math.PI * 2;
        const px = cx + r * Math.cos(theta);
        const py = cy + r * Math.sin(theta);

        // Approximation of gravity center velocity
        const vMag = Math.sqrt((state.gravityConstant * (starMass * 2)) / r) * (0.8 + Math.random() * 0.4);
        const vx = -vMag * Math.sin(theta);
        const vy = vMag * Math.cos(theta);

        const radius = 1.5 + Math.random() * 4;
        const mass = radius * radius;
        const color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];

        bodies.push(new Body(px, py, vx, vy, radius, mass, color));
      }
      break;
    }
    case 'chaos': {
      // Dynamic chaotic cloud without center mass
      const count = state.particleCount;
      for (let i = 0; i < count; i++) {
        const px = Math.random() * width;
        const py = Math.random() * height;
        // Random velocity vectors
        const vx = (Math.random() - 0.5) * 4;
        const vy = (Math.random() - 0.5) * 4;

        const radius = 3 + Math.random() * 8;
        const mass = radius * radius * 1.5;
        const color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];

        bodies.push(new Body(px, py, vx, vy, radius, mass, color));
      }
      break;
    }
    case 'grid': {
      // Grid pattern responding to forces
      const count = state.particleCount;
      const side = Math.ceil(Math.sqrt(count));
      const spacingX = (width - 200) / side;
      const spacingY = (height - 200) / side;
      
      for (let i = 0; i < side; i++) {
        for (let j = 0; j < side; j++) {
          if (bodies.length >= count) break;
          const px = 100 + i * spacingX + (Math.random() - 0.5) * 5;
          const py = 100 + j * spacingY + (Math.random() - 0.5) * 5;
          
          const radius = 2.5;
          const mass = 10;
          const color = currentTheme.particleColors[(i + j) % currentTheme.particleColors.length];
          
          // Stationary at start
          bodies.push(new Body(px, py, 0, 0, radius, mass, color));
        }
      }
      break;
    }
  }
  
  updateUI();
}

// Spawns a custom body on mouse click
function spawnBodyAt(x, y) {
  const currentTheme = themes[state.theme];
  // Calculate relative orbital velocity around center mass or sun if exists
  const sun = bodies.find(b => b.isStatic);
  let vx = (Math.random() - 0.5) * 2;
  let vy = (Math.random() - 0.5) * 2;

  if (sun) {
    const dx = x - sun.x;
    const dy = y - sun.y;
    const r = Math.sqrt(dx * dx + dy * dy);
    if (r > 10) {
      const vMag = Math.sqrt((state.gravityConstant * sun.mass) / r);
      // Direction perpendicular (clock-wise orbit)
      vx = -vMag * (dy / r);
      vy = vMag * (dx / r);
    }
  } else if (bodies.length > 0) {
    // Average centers
    let avgX = 0, avgY = 0;
    bodies.forEach(b => { avgX += b.x; avgY += b.y; });
    avgX /= bodies.length;
    avgY /= bodies.length;
    
    const dx = x - avgX;
    const dy = y - avgY;
    const r = Math.sqrt(dx * dx + dy * dy);
    if (r > 10) {
      const vMag = Math.sqrt((state.gravityConstant * 2500) / r);
      vx = -vMag * (dy / r);
      vy = vMag * (dx / r);
    }
  }

  const radius = 3 + Math.random() * 6;
  const mass = radius * radius;
  const color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];

  bodies.push(new Body(x, y, vx, vy, radius, mass, color));
  state.particleCount = bodies.filter(b => !b.isStatic).length;
  document.getElementById('particleCount').value = state.particleCount;
  document.getElementById('particleCountVal').textContent = state.particleCount;
  updateUI();
}

// UI Elements & Binding
const minimizeBtn = document.getElementById('minimizeBtn');
const dashboard = document.getElementById('dashboard');
const clearBtn = document.getElementById('clearBtn');
const resetBtn = document.getElementById('resetBtn');
const antigravityToggle = document.getElementById('antigravityToggle');
const antigravityStatus = document.getElementById('antigravityStatus');
const showOrbitsCheck = document.getElementById('showOrbits');
const showVectorsCheck = document.getElementById('showVectors');
const collisionsCheck = document.getElementById('enableCollisions');

const particleCountSlider = document.getElementById('particleCount');
const particleCountVal = document.getElementById('particleCountVal');
const gravitySlider = document.getElementById('gravityConstant');
const gravityVal = document.getElementById('gravityVal');
const timeSpeedSlider = document.getElementById('timeSpeed');
const timeSpeedVal = document.getElementById('timeSpeedVal');
const themeSelect = document.getElementById('themeSelect');

const fpsVal = document.getElementById('fpsVal');
const msVal = document.getElementById('msVal');
const bodiesVal = document.getElementById('bodiesVal');
const capacityVal = document.getElementById('capacityVal');

const guideToast = document.getElementById('guideToast');
const toastCloseBtn = document.getElementById('toastCloseBtn');

// Create Floating Trigger Button
const floatTrigger = document.createElement('div');
floatTrigger.className = 'float-trigger glass';
floatTrigger.innerHTML = '⚙️';
floatTrigger.title = 'Open Controls';
document.body.appendChild(floatTrigger);

// Toggle controls minimization
minimizeBtn.addEventListener('click', () => {
  dashboard.classList.add('minimized');
  floatTrigger.classList.add('visible');
});

floatTrigger.addEventListener('click', () => {
  dashboard.classList.remove('minimized');
  floatTrigger.classList.remove('visible');
});

// Toast closure
toastCloseBtn.addEventListener('click', () => {
  guideToast.classList.add('dismissed');
});
// Auto-dismiss guide toast after 10 seconds
setTimeout(() => {
  guideToast.classList.add('dismissed');
}, 12000);

// Presets grid bindings
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    applyPreset(e.target.dataset.preset);
  });
});

// Actions
clearBtn.addEventListener('click', () => {
  bodies = bodies.filter(b => b.isStatic); // Keep sun/static stars
  state.particleCount = 0;
  particleCountSlider.value = 0;
  particleCountVal.textContent = '0';
  updateUI();
});

resetBtn.addEventListener('click', () => {
  applyPreset(state.activePreset);
});

// Antigravity toggle
antigravityToggle.addEventListener('click', () => {
  state.isAntigravity = !state.isAntigravity;
  antigravityToggle.classList.toggle('active', state.isAntigravity);
  antigravityStatus.textContent = state.isAntigravity ? 'ACTIVE' : 'OFF';
  
  // Dynamic color shift on neon orbs in background
  const orb1 = document.getElementById('glowOrb1');
  const orb2 = document.getElementById('glowOrb2');
  if (state.isAntigravity) {
    orb1.style.background = `radial-gradient(circle, var(--accent-antigravity) 0%, transparent 70%)`;
    orb2.style.background = `radial-gradient(circle, hsl(290, 85%, 60%) 0%, transparent 70%)`;
  } else {
    // Reset to theme colors
    const currentTheme = themes[state.theme];
    orb1.style.background = `radial-gradient(circle, var(--primary) 0%, transparent 70%)`;
    orb2.style.background = `radial-gradient(circle, var(--secondary) 0%, transparent 70%)`;
  }
});

// Display adjustments
showOrbitsCheck.addEventListener('change', (e) => {
  state.showOrbits = e.target.checked;
  if (!state.showOrbits) {
    bodies.forEach(b => b.trail = []);
  }
});

showVectorsCheck.addEventListener('change', (e) => {
  state.showVectors = e.target.checked;
});

collisionsCheck.addEventListener('change', (e) => {
  state.enableCollisions = e.target.checked;
});

// Slider inputs
particleCountSlider.addEventListener('input', (e) => {
  const nextCount = parseInt(e.target.value);
  particleCountVal.textContent = nextCount;
  
  // Re-adjust particle count dynamically in real time
  const currentNonStatic = bodies.filter(b => !b.isStatic).length;
  if (nextCount > currentNonStatic) {
    // Spawn more particles
    const diff = nextCount - currentNonStatic;
    const currentTheme = themes[state.theme];
    const width = canvas.width;
    const height = canvas.height;
    const cx = width / 2;
    const cy = height / 2;
    const sun = bodies.find(b => b.isStatic);

    for (let i = 0; i < diff; i++) {
      let px, py, vx, vy;
      if (sun && state.activePreset === 'solar') {
        const r = 80 + Math.random() * (Math.min(width, height) / 2 - 100);
        const theta = Math.random() * Math.PI * 2;
        px = cx + r * Math.cos(theta);
        py = cy + r * Math.sin(theta);
        const vMag = Math.sqrt((state.gravityConstant * sun.mass) / r);
        vx = -vMag * Math.sin(theta);
        vy = vMag * Math.cos(theta);
      } else {
        px = Math.random() * width;
        py = Math.random() * height;
        vx = (Math.random() - 0.5) * 4;
        vy = (Math.random() - 0.5) * 4;
      }
      
      const radius = 2 + Math.random() * 5;
      const mass = radius * radius;
      const color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];
      bodies.push(new Body(px, py, vx, vy, radius, mass, color));
    }
  } else if (nextCount < currentNonStatic) {
    // Remove particles from the end
    const diff = currentNonStatic - nextCount;
    let removed = 0;
    for (let i = bodies.length - 1; i >= 0; i--) {
      if (!bodies[i].isStatic) {
        bodies.splice(i, 1);
        removed++;
        if (removed >= diff) break;
      }
    }
  }
  
  state.particleCount = nextCount;
  updateUI();
});

gravitySlider.addEventListener('input', (e) => {
  state.gravityConstant = parseFloat(e.target.value);
  gravityVal.textContent = state.gravityConstant.toFixed(2);
});

timeSpeedSlider.addEventListener('input', (e) => {
  state.timeSpeed = parseFloat(e.target.value);
  timeSpeedVal.textContent = state.timeSpeed.toFixed(1) + 'x';
});

// Theme Select Handler
themeSelect.addEventListener('change', (e) => {
  state.theme = e.target.value;
  canvas.style.backgroundColor = themes[state.theme].bg;
  
  // Re-map colors of existing bodies
  const currentTheme = themes[state.theme];
  
  // Orbs shift color
  const orb1 = document.getElementById('glowOrb1');
  const orb2 = document.getElementById('glowOrb2');
  if (!state.isAntigravity) {
    orb1.style.background = `radial-gradient(circle, ${currentTheme.particleColors[1] || 'var(--primary)'} 0%, transparent 70%)`;
    orb2.style.background = `radial-gradient(circle, ${currentTheme.particleColors[0] || 'var(--secondary)'} 0%, transparent 70%)`;
  }
  
  bodies.forEach(b => {
    if (b.isStatic) {
      b.color = currentTheme.centerColor;
    } else {
      b.color = currentTheme.particleColors[Math.floor(Math.random() * currentTheme.particleColors.length)];
    }
  });
});

// Mouse listeners for gravity wells
canvas.addEventListener('mousedown', (e) => {
  if (e.button === 0) { // Left click
    // Get mouse coordinate relative to canvas bounds
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    // Check if clicking dashboard or UI overlay (handled via CSS pointer-events but added safety)
    if (mx < 410 && my < dashboard.offsetHeight + 24 && !dashboard.classList.contains('minimized')) return;
    if (mx < 410 && my > canvas.height - 120) return;
    if (mx > canvas.width - 340 && my < 120 && !guideToast.classList.contains('dismissed')) return;

    state.isDragging = true;
    state.mousePos.x = mx;
    state.mousePos.y = my;
  }
});

canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  state.mousePos.x = e.clientX - rect.left;
  state.mousePos.y = e.clientY - rect.top;
});

window.addEventListener('mouseup', (e) => {
  if (state.isDragging) {
    state.isDragging = false;
    
    // If it was just a quick click without dragging far, spawn a body
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    
    // Safety boundaries
    if (mx < 410 && my < dashboard.offsetHeight + 24 && !dashboard.classList.contains('minimized')) return;
    if (mx < 410 && my > canvas.height - 120) return;
    
    spawnBodyAt(mx, my);
  }
});

// Update UI panel values
function updateUI() {
  bodiesVal.textContent = bodies.length;
}

// Main Physics Loop
function loop(time) {
  // Delta time in seconds
  let dt = (time - state.lastTime) / 16.666; // Normalized to 60 FPS
  state.lastTime = time;
  
  if (dt > 3) dt = 3; // Prevent physics explosions on frame hitching

  const startPerf = performance.now();

  // 1. Calculate physics acceleration forces
  applyGravitationalForces();
  
  // 2. Resolve elastic collisions
  resolveCollisions();
  
  // 3. Update positions
  for (let i = 0; i < bodies.length; i++) {
    bodies[i].update(dt);
  }

  const physicsPerf = performance.now();

  // 4. Render
  // Fade draw for trails effect
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = themes[state.theme].trailColor;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Render bodies
  for (let i = 0; i < bodies.length; i++) {
    bodies[i].draw(ctx);
  }

  // Draw gravity well helper at cursor
  if (state.isDragging) {
    ctx.beginPath();
    ctx.arc(state.mousePos.x, state.mousePos.y, 8, 0, Math.PI * 2);
    ctx.strokeStyle = state.isAntigravity ? varValue('--accent-antigravity') : varValue('--secondary');
    ctx.lineWidth = 2;
    ctx.stroke();
    
    ctx.beginPath();
    ctx.arc(state.mousePos.x, state.mousePos.y, 25, 0, Math.PI * 2);
    ctx.strokeStyle = state.isAntigravity ? varValue('--accent-antigravity') : varValue('--secondary');
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.25;
    ctx.stroke();
    ctx.globalAlpha = 1.0;
  }

  const renderPerf = performance.now();
  state.msCost = (renderPerf - startPerf);

  // FPS Tracking
  state.framesThisSecond++;
  state.fpsTimer += (time - state.lastTime); // Add frame time difference
  
  if (time > state.fpsTimer + 1000) {
    state.fps = Math.round((state.framesThisSecond * 1000) / (time - state.lastTime));
    // Fallback simple calculation
    state.fps = state.framesThisSecond;
    state.framesThisSecond = 0;
    state.fpsTimer = time;
    
    // Update performance values on dashboard
    fpsVal.textContent = state.fps;
    msVal.textContent = state.msCost.toFixed(1) + ' ms';
    
    // Performance Capacity Index calculations
    if (state.fps >= 55) {
      capacityVal.textContent = 'Optimal';
      capacityVal.className = 'stat-value text-green';
      fpsVal.className = 'stat-value text-green';
    } else if (state.fps >= 35) {
      capacityVal.textContent = 'Strained';
      capacityVal.className = 'stat-value text-yellow';
      fpsVal.className = 'stat-value text-yellow';
    } else {
      capacityVal.textContent = 'Overload';
      capacityVal.className = 'stat-value text-red';
      fpsVal.className = 'stat-value text-red';
    }
  }

  requestAnimationFrame(loop);
}

// Utility to get CSS Variable value from root
function varValue(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// Run Initial Preset on Startup
applyPreset('solar');
requestAnimationFrame(loop);
