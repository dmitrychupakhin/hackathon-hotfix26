import { createGaussianKernel } from "./auth-glass-blur";
import {
  FIGURE_PADDING,
  FIGURES,
  VIEWBOX_HEIGHT,
  VIEWBOX_WIDTH,
} from "./auth-glass-geometry";

const BLUR_STD_DEVIATION = 22.79;
const DISPLACEMENT_SCALE = 80;
const FILTER_SCALE = 0.25;
const FILTER_WIDTH = VIEWBOX_WIDTH * FILTER_SCALE;
const FILTER_HEIGHT = VIEWBOX_HEIGHT * FILTER_SCALE;

const BLUR_SAMPLES = createGaussianKernel(BLUR_STD_DEVIATION * FILTER_SCALE)
  .map(({ offset, weight }) => {
    const value = weight.toFixed(9);
    if (offset === 0)
      return `vec4 color = texture2D(u_texture, v_uv) * ${value};`;
    const distance = offset.toFixed(6);
    return `color += (texture2D(u_texture, v_uv + u_direction * ${distance}) + texture2D(u_texture, v_uv - u_direction * ${distance})) * ${value};`;
  })
  .join("\n");

const QUAD = new Float32Array([
  -1, -1, 0, 0, 1, -1, 1, 0, -1, 1, 0, 1, 1, 1, 1, 1,
]);

const VERTEX_SHADER = `
attribute vec2 a_position;
attribute vec2 a_uv;
uniform vec2 u_offset;
uniform vec2 u_scale;
varying vec2 v_uv;

void main() {
  gl_Position = vec4(a_position * u_scale + u_offset, 0.0, 1.0);
  v_uv = a_uv;
}
`;

const LAYER_FRAGMENT_SHADER = `
precision mediump float;
uniform sampler2D u_texture;
varying vec2 v_uv;

void main() {
  gl_FragColor = texture2D(u_texture, v_uv);
}
`;

const BLUR_FRAGMENT_SHADER = `
precision mediump float;
uniform sampler2D u_texture;
uniform vec2 u_direction;
varying vec2 v_uv;

void main() {
  ${BLUR_SAMPLES}
  gl_FragColor = color;
}
`;

const REFRACTION_FRAGMENT_SHADER = `
precision mediump float;
uniform sampler2D u_texture;
uniform sampler2D u_map;
varying vec2 v_uv;

void main() {
  vec2 mapValue = texture2D(u_map, v_uv).rg;
  vec2 displacement = (mapValue - vec2(0.5)) * vec2(${DISPLACEMENT_SCALE / VIEWBOX_WIDTH}, ${DISPLACEMENT_SCALE / VIEWBOX_HEIGHT});
  gl_FragColor = texture2D(u_texture, v_uv + vec2(displacement.x, -displacement.y));
}
`;

type ProgramInfo = {
  program: WebGLProgram;
  position: number;
  uv: number;
  texture: WebGLUniformLocation | null;
  offset: WebGLUniformLocation | null;
  scale: WebGLUniformLocation | null;
  direction: WebGLUniformLocation | null;
  map: WebGLUniformLocation | null;
};

type RenderTarget = {
  texture: WebGLTexture;
  framebuffer: WebGLFramebuffer;
};

function createFigureImage(path: string) {
  const width = VIEWBOX_WIDTH + FIGURE_PADDING * 2;
  const height = VIEWBOX_HEIGHT + FIGURE_PADDING * 2;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="-${FIGURE_PADDING} -${FIGURE_PADDING} ${width} ${height}"><defs><linearGradient id="figure" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#A4D36B"/><stop offset="1" stop-color="#D1E5B8"/></linearGradient></defs><path d="${path}" fill="url(#figure)"/></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () =>
      reject(new Error("Auth glass texture failed to load"));
    image.src = src;
  });
}

function createShader(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("Unable to create WebGL shader");

  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message =
      gl.getShaderInfoLog(shader) ?? "WebGL shader compilation failed";
    gl.deleteShader(shader);
    throw new Error(message);
  }

  return shader;
}

function createProgram(gl: WebGLRenderingContext, fragmentSource: string) {
  const vertexShader = createShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
  const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
  const program = gl.createProgram();
  if (!program) throw new Error("Unable to create WebGL program");

  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);
  gl.deleteShader(vertexShader);
  gl.deleteShader(fragmentShader);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message =
      gl.getProgramInfoLog(program) ?? "WebGL program linking failed";
    gl.deleteProgram(program);
    throw new Error(message);
  }

  return {
    program,
    position: gl.getAttribLocation(program, "a_position"),
    uv: gl.getAttribLocation(program, "a_uv"),
    texture: gl.getUniformLocation(program, "u_texture"),
    offset: gl.getUniformLocation(program, "u_offset"),
    scale: gl.getUniformLocation(program, "u_scale"),
    direction: gl.getUniformLocation(program, "u_direction"),
    map: gl.getUniformLocation(program, "u_map"),
  } satisfies ProgramInfo;
}

function configureTexture(gl: WebGLRenderingContext, texture: WebGLTexture) {
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
}

export function createAuthGlassRenderer(
  canvas: HTMLCanvasElement,
  mapSource: string,
  onAvailabilityChange: (available: boolean) => void,
) {
  const gl = canvas.getContext("webgl", {
    alpha: false,
    antialias: false,
    powerPreference: "high-performance",
  });
  if (!gl) return null;
  const selectProgram = gl.useProgram.bind(gl);

  let destroyed = false;
  let contextLost = false;
  let images: [HTMLImageElement, HTMLImageElement, HTMLImageElement] | null =
    null;
  let sourceProgram: ProgramInfo | null = null;
  let blurProgram: ProgramInfo | null = null;
  let refractionProgram: ProgramInfo | null = null;
  let quadBuffer: WebGLBuffer | null = null;
  let upperTexture: WebGLTexture | null = null;
  let lowerTexture: WebGLTexture | null = null;
  let mapTexture: WebGLTexture | null = null;
  let sourceTarget: RenderTarget | null = null;
  let blurTarget: RenderTarget | null = null;
  let frostTarget: RenderTarget | null = null;
  let pointerX = 0;
  let pointerY = 0;
  let renderRequest = 0;

  const deleteTarget = (target: RenderTarget | null) => {
    if (!target || contextLost) return;
    gl.deleteFramebuffer(target.framebuffer);
    gl.deleteTexture(target.texture);
  };

  const clearResources = () => {
    if (!contextLost) {
      if (sourceProgram) gl.deleteProgram(sourceProgram.program);
      if (blurProgram) gl.deleteProgram(blurProgram.program);
      if (refractionProgram) gl.deleteProgram(refractionProgram.program);
      if (quadBuffer) gl.deleteBuffer(quadBuffer);
      if (upperTexture) gl.deleteTexture(upperTexture);
      if (lowerTexture) gl.deleteTexture(lowerTexture);
      if (mapTexture) gl.deleteTexture(mapTexture);
    }
    deleteTarget(sourceTarget);
    deleteTarget(blurTarget);
    deleteTarget(frostTarget);
    sourceProgram = null;
    blurProgram = null;
    refractionProgram = null;
    quadBuffer = null;
    upperTexture = null;
    lowerTexture = null;
    mapTexture = null;
    sourceTarget = null;
    blurTarget = null;
    frostTarget = null;
  };

  const createImageTexture = (
    image: HTMLImageElement,
    premultiply: boolean,
  ) => {
    const texture = gl.createTexture();
    if (!texture) throw new Error("Unable to create WebGL texture");
    configureTexture(gl, texture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, 1);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, premultiply ? 1 : 0);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    return texture;
  };

  const createRenderTarget = (): RenderTarget => {
    const texture = gl.createTexture();
    const framebuffer = gl.createFramebuffer();
    if (!texture || !framebuffer) {
      if (texture) gl.deleteTexture(texture);
      if (framebuffer) gl.deleteFramebuffer(framebuffer);
      throw new Error("Unable to create WebGL framebuffer");
    }

    configureTexture(gl, texture);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA,
      FILTER_WIDTH,
      FILTER_HEIGHT,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      null,
    );
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(
      gl.FRAMEBUFFER,
      gl.COLOR_ATTACHMENT0,
      gl.TEXTURE_2D,
      texture,
      0,
    );
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
      gl.deleteFramebuffer(framebuffer);
      gl.deleteTexture(texture);
      throw new Error("WebGL framebuffer is incomplete");
    }

    return { texture, framebuffer };
  };

  const resize = () => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width * ratio));
    const height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width === width && canvas.height === height) return;

    canvas.width = width;
    canvas.height = height;
    render();
  };

  const bindQuad = (info: ProgramInfo) => {
    selectProgram(info.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    gl.enableVertexAttribArray(info.position);
    gl.vertexAttribPointer(info.position, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(info.uv);
    gl.vertexAttribPointer(info.uv, 2, gl.FLOAT, false, 16, 8);
    if (info.offset) gl.uniform2f(info.offset, 0, 0);
    if (info.scale) gl.uniform2f(info.scale, 1, 1);
  };

  const drawLayer = (
    info: ProgramInfo,
    texture: WebGLTexture,
    x: number,
    y: number,
  ) => {
    bindQuad(info);
    gl.uniform2f(
      info.offset,
      (x * 2) / VIEWBOX_WIDTH,
      (-y * 2) / VIEWBOX_HEIGHT,
    );
    gl.uniform2f(
      info.scale,
      (VIEWBOX_WIDTH + FIGURE_PADDING * 2) / VIEWBOX_WIDTH,
      (VIEWBOX_HEIGHT + FIGURE_PADDING * 2) / VIEWBOX_HEIGHT,
    );
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(info.texture, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };

  const render = () => {
    if (
      destroyed ||
      contextLost ||
      !images ||
      !sourceProgram ||
      !blurProgram ||
      !refractionProgram ||
      !quadBuffer ||
      !upperTexture ||
      !lowerTexture ||
      !mapTexture ||
      !sourceTarget ||
      !blurTarget ||
      !frostTarget
    ) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    gl.viewport(0, 0, FILTER_WIDTH, FILTER_HEIGHT);
    gl.bindFramebuffer(gl.FRAMEBUFFER, sourceTarget.framebuffer);
    gl.clearColor(1, 1, 1, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    drawLayer(
      sourceProgram,
      upperTexture,
      pointerX * FIGURES[0].x,
      pointerY * FIGURES[0].y,
    );
    drawLayer(
      sourceProgram,
      lowerTexture,
      pointerX * FIGURES[1].x,
      pointerY * FIGURES[1].y,
    );
    gl.disable(gl.BLEND);

    gl.bindFramebuffer(gl.FRAMEBUFFER, blurTarget.framebuffer);
    bindQuad(blurProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, sourceTarget.texture);
    gl.uniform1i(blurProgram.texture, 0);
    gl.uniform2f(blurProgram.direction, 1 / FILTER_WIDTH, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.bindFramebuffer(gl.FRAMEBUFFER, frostTarget.framebuffer);
    bindQuad(blurProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, blurTarget.texture);
    gl.uniform1i(blurProgram.texture, 0);
    gl.uniform2f(blurProgram.direction, 0, 1 / FILTER_HEIGHT);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    bindQuad(refractionProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, frostTarget.texture);
    gl.uniform1i(refractionProgram.texture, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, mapTexture);
    gl.uniform1i(refractionProgram.map, 1);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  };

  const scheduleRender = () => {
    if (renderRequest || destroyed) return;
    renderRequest = window.requestAnimationFrame(() => {
      renderRequest = 0;
      render();
    });
  };

  const initializeResources = () => {
    if (destroyed || contextLost || !images) return;
    try {
      clearResources();
      sourceProgram = createProgram(gl, LAYER_FRAGMENT_SHADER);
      blurProgram = createProgram(gl, BLUR_FRAGMENT_SHADER);
      refractionProgram = createProgram(gl, REFRACTION_FRAGMENT_SHADER);
      quadBuffer = gl.createBuffer();
      if (!quadBuffer) throw new Error("Unable to create WebGL vertex buffer");
      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, QUAD, gl.STATIC_DRAW);

      upperTexture = createImageTexture(images[0], true);
      lowerTexture = createImageTexture(images[1], true);
      mapTexture = createImageTexture(images[2], false);
      sourceTarget = createRenderTarget();
      blurTarget = createRenderTarget();
      frostTarget = createRenderTarget();
      resize();
      render();
      onAvailabilityChange(true);
    } catch {
      clearResources();
      onAvailabilityChange(false);
    }
  };

  const onContextLost = (event: Event) => {
    event.preventDefault();
    contextLost = true;
    clearResources();
    onAvailabilityChange(false);
  };
  const onContextRestored = () => {
    contextLost = false;
    initializeResources();
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas);
  canvas.addEventListener("webglcontextlost", onContextLost);
  canvas.addEventListener("webglcontextrestored", onContextRestored);

  Promise.all([
    loadImage(createFigureImage(FIGURES[0].path)),
    loadImage(createFigureImage(FIGURES[1].path)),
    loadImage(mapSource),
  ])
    .then((loadedImages) => {
      if (destroyed) return;
      images = loadedImages as [
        HTMLImageElement,
        HTMLImageElement,
        HTMLImageElement,
      ];
      initializeResources();
    })
    .catch(() => {
      if (!destroyed) onAvailabilityChange(false);
    });

  return {
    setPointer(x: number, y: number) {
      pointerX = x;
      pointerY = y;
      scheduleRender();
    },
    destroy() {
      destroyed = true;
      if (renderRequest) window.cancelAnimationFrame(renderRequest);
      resizeObserver.disconnect();
      canvas.removeEventListener("webglcontextlost", onContextLost);
      canvas.removeEventListener("webglcontextrestored", onContextRestored);
      clearResources();
    },
  };
}
