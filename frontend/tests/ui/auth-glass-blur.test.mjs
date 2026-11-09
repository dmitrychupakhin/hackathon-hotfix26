import assert from "node:assert/strict";
import test from "node:test";
import { createGaussianKernel } from "../../src/shared/ui/auth-glass/auth-glass-blur.ts";
import {
  FIGURE_PADDING,
  FIGURES,
} from "../../src/shared/ui/auth-glass/auth-glass-geometry.ts";

test("the paired samples reproduce a normalized, smooth Gaussian blur", () => {
  const sigma = 22.79 / 4;
  const samples = createGaussianKernel(sigma);
  const radius = Math.ceil(sigma * 3);
  const weights = Array.from({ length: radius + 1 }, () => 0);

  for (const { offset, weight } of samples) {
    const index = Math.floor(offset);
    const fraction = offset - index;
    weights[index] += weight * (1 - fraction);
    if (fraction) weights[index + 1] += weight * fraction;
  }

  const total =
    weights[0] + 2 * weights.slice(1).reduce((sum, value) => sum + value, 0);
  assert.ok(Math.abs(total - 1) < 1e-12);
  assert.ok(weights[0] < 0.08);
  for (let index = 1; index <= radius; index++) {
    const expected = weights[0] * Math.exp(-0.5 * (index / sigma) ** 2);
    assert.ok(Math.abs(weights[index] - expected) < 1e-12);
    assert.ok(weights[index] < weights[index - 1]);
  }
});

test("invalid blur widths are rejected", () => {
  for (const sigma of [0, -1, NaN, Infinity]) {
    assert.throws(() => createGaussianKernel(sigma), RangeError);
  }
});

test("figure textures keep a margin for motion, displacement and blur", () => {
  const filterMargin = 80 / 2 + 22.79 * 3;
  for (const figure of FIGURES) {
    assert.ok(FIGURE_PADDING - Math.abs(figure.x) > filterMargin);
    assert.ok(FIGURE_PADDING - Math.abs(figure.y) > filterMargin);
  }
});
