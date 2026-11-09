export function createGaussianKernel(sigma: number) {
  if (!Number.isFinite(sigma) || sigma <= 0) {
    throw new RangeError("Gaussian sigma must be positive");
  }

  const radius = Math.ceil(sigma * 3);
  const weights = Array.from({ length: radius + 1 }, (_, index) =>
    Math.exp(-0.5 * (index / sigma) ** 2),
  );
  const total =
    weights[0] + 2 * weights.slice(1).reduce((sum, weight) => sum + weight, 0);
  const samples = [{ offset: 0, weight: weights[0] / total }];

  for (let index = 1; index <= radius; index += 2) {
    const first = weights[index];
    const second = weights[index + 1] ?? 0;
    const weight = first + second;
    samples.push({
      offset: index + second / weight,
      weight: weight / total,
    });
  }

  return samples;
}
