import { writeFile } from "node:fs/promises";
import sharp from "sharp";

// Design-space lens map. Keep every colour channel together in the SVG filter.
// The mirrored bevel profile leaves the centre calm and bends the outer part of
// each pane. At scale=80 its maximum offset is 28px, below the fold-over limit.
const paneWidth = 256;
const width = paneWidth * 7;
const height = 1016;
const pixels = Buffer.alloc(width * height * 4);
for (let x = 0; x < width; x++) {
  const position = ((x % paneWidth) / (paneWidth - 1)) * 2 - 1;
  const edge = Math.max(0, (Math.abs(position) - 0.25) / 0.75);
  const bevel = edge * edge * (3 - 2 * edge);
  const offset = -Math.sign(position) * bevel * 0.35;
  for (let y = 0; y < height; y++) {
    const index = (y * width + x) * 4;
    pixels[index] = Math.round(255 * (0.5 + offset));
    pixels[index + 1] = 128;
    pixels[index + 2] = 128;
    pixels[index + 3] = 255;
  }
}
const png = await sharp(pixels, { raw: { width, height, channels: 4 } })
  .png()
  .toBuffer();
await writeFile(
  new URL(
    "../../src/shared/ui/auth-glass/refraction-map.json",
    import.meta.url,
  ),
  `${JSON.stringify(`data:image/png;base64,${png.toString("base64")}`)}\n`,
);
