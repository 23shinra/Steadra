const vertexShader = `
attribute vec2 uv;
attribute vec2 position;

varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}
`;

const fragmentShader = `
precision highp float;

uniform float uTime;
uniform vec3 uColor;
uniform vec3 uResolution;
uniform vec2 uMouse;
uniform float uAmplitude;
uniform float uSpeed;

varying vec2 vUv;

void main() {
  float mr = min(uResolution.x, uResolution.y);
  vec2 uv = (vUv.xy * 2.0 - 1.0) * uResolution.xy / mr;

  uv += (uMouse - vec2(0.5)) * uAmplitude;

  float d = -uTime * 0.5 * uSpeed;
  float a = 0.0;
  for (float i = 0.0; i < 8.0; ++i) {
    a += cos(i - d - a * uv.x);
    d += sin(uv.y * i + a);
  }
  d += uTime * 0.5 * uSpeed;
  vec3 col = vec3(cos(uv * vec2(d, a)) * 0.6 + 0.4, cos(a + d) * 0.5 + 0.5);
  col = cos(col * cos(vec3(d, a, 2.5)) * 0.5 + 0.5) * uColor;
  gl_FragColor = vec4(col, 1.0);
}
`;

function parseBool(v, fallback) {
  if (v == null) return fallback;
  const s = String(v).trim().toLowerCase();
  if (s === "1" || s === "true" || s === "yes") return true;
  if (s === "0" || s === "false" || s === "no") return false;
  return fallback;
}

function parseNum(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function parseColor(v, fallback) {
  if (!v) return fallback;
  const parts = String(v)
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((x) => Number.isFinite(x));
  if (parts.length !== 3) return fallback;
  return parts.map((x) => Math.max(0, Math.min(1, x)));
}

function init() {
  const ctn = document.getElementById("iridescence-bg");
  if (!ctn || ctn.dataset.bound === "1") return;
  ctn.dataset.bound = "1";

  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  if (reduceMotion) return;

  const OGL = window.OGL;
  if (!OGL) return;
  const { Renderer, Program, Mesh, Color, Triangle } = OGL;

  const color = parseColor(ctn.dataset.color, [0.3, 0.2, 0.5]);
  const speed = parseNum(ctn.dataset.speed, 1.0);
  const amplitude = parseNum(ctn.dataset.amplitude, 0.1);
  const mouseReact = parseBool(ctn.dataset.mouseReact, false);

  const renderer = new Renderer({ dpr: Math.min(2, window.devicePixelRatio || 1), alpha: true });
  const gl = renderer.gl;
  gl.clearColor(0, 0, 0, 0);

  let program;
  const mouse = new Float32Array([0.5, 0.5]);

  const resize = () => {
    const w = Math.max(1, ctn.clientWidth);
    const h = Math.max(1, ctn.clientHeight);
    renderer.setSize(w, h);
    if (program) {
      program.uniforms.uResolution.value = new Color(gl.canvas.width, gl.canvas.height, gl.canvas.width / gl.canvas.height);
    }
  };

  const geometry = new Triangle(gl);
  program = new Program(gl, {
    vertex: vertexShader,
    fragment: fragmentShader,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new Color(color[0], color[1], color[2]) },
      uResolution: { value: new Color(1, 1, 1) },
      uMouse: { value: mouse },
      uAmplitude: { value: amplitude },
      uSpeed: { value: speed },
    },
    transparent: true,
  });

  const mesh = new Mesh(gl, { geometry, program });
  ctn.appendChild(gl.canvas);

  let raf = 0;
  const update = (t) => {
    raf = requestAnimationFrame(update);
    program.uniforms.uTime.value = t * 0.001;
    renderer.render({ scene: mesh });
  };
  raf = requestAnimationFrame(update);

  const onMouse = (clientX, clientY) => {
    const rect = ctn.getBoundingClientRect();
    const x = rect.width ? (clientX - rect.left) / rect.width : 0.5;
    const y = rect.height ? 1.0 - (clientY - rect.top) / rect.height : 0.5;
    mouse[0] = Math.max(0, Math.min(1, x));
    mouse[1] = Math.max(0, Math.min(1, y));
  };

  const onPointerMove = (e) => onMouse(e.clientX, e.clientY);
  const onTouchMove = (e) => {
    const t = e.touches?.[0];
    if (!t) return;
    onMouse(t.clientX, t.clientY);
  };

  if (mouseReact) {
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
  }

  const onResize = () => resize();
  window.addEventListener("resize", onResize, { passive: true });
  window.addEventListener("orientationchange", onResize, { passive: true });
  resize();

  window.addEventListener("beforeunload", () => {
    try {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
      if (mouseReact) {
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("touchmove", onTouchMove);
      }
      ctn.removeChild(gl.canvas);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {}
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}

