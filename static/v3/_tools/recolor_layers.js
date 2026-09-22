const path = require("node:path");
const sharp = require("sharp");

const assetsDir = path.resolve(__dirname, "../assets");
const layers = [
  { name: "hero-gift", mobile: [900, 900], watermark: [0, 0.91, 0.14, 1] },
  { name: "mid-stage", mobile: [1024, 683], watermark: [0, 0.91, 0.10, 1] },
  { name: "fg-left", mobile: [683, 1024] },
  { name: "fg-right", mobile: [683, 1024], watermark: [0, 0.92, 0.14, 1] },
  { name: "confetti-fg", mobile: [1152, 768], watermark: [0, 0.91, 0.12, 1] },
];

function rgbToHsl(red, green, blue) {
  const r = red / 255;
  const g = green / 255;
  const b = blue / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const lightness = (max + min) / 2;
  const delta = max - min;
  if (delta === 0) return [0, 0, lightness];

  const saturation = delta / (1 - Math.abs(2 * lightness - 1));
  let hue;
  if (max === r) hue = 60 * (((g - b) / delta) % 6);
  else if (max === g) hue = 60 * ((b - r) / delta + 2);
  else hue = 60 * ((r - g) / delta + 4);
  return [(hue + 360) % 360, saturation, lightness];
}

function hslToRgb(hue, saturation, lightness) {
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const sector = hue / 60;
  const x = chroma * (1 - Math.abs((sector % 2) - 1));
  let red = 0;
  let green = 0;
  let blue = 0;

  if (sector < 1) [red, green] = [chroma, x];
  else if (sector < 2) [red, green] = [x, chroma];
  else if (sector < 3) [green, blue] = [chroma, x];
  else if (sector < 4) [green, blue] = [x, chroma];
  else if (sector < 5) [red, blue] = [x, chroma];
  else [red, blue] = [chroma, x];

  const match = lightness - chroma / 2;
  return [red, green, blue].map((channel) => Math.round((channel + match) * 255));
}

function recolor(data, width, height, watermark) {
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      const alpha = data[offset + 3];

      if (watermark) {
        const [left, top, right, bottom] = watermark;
        if (x >= left * width && x <= right * width && y >= top * height && y <= bottom * height) {
          data[offset] = 0;
          data[offset + 1] = 0;
          data[offset + 2] = 0;
          data[offset + 3] = 0;
          continue;
        }
      }

      if (alpha < 10) {
        data[offset] = 0;
        data[offset + 1] = 0;
        data[offset + 2] = 0;
        data[offset + 3] = 0;
        continue;
      }

      const [hue, saturation, lightness] = rgbToHsl(data[offset], data[offset + 1], data[offset + 2]);
      if (hue >= 130 && hue <= 215 && saturation >= 0.24) {
        const targetHue = lightness >= 0.58 ? 245 : 232;
        const targetSaturation = Math.max(0.56, Math.min(0.72, saturation * 0.88));
        const targetLightness = Math.max(0.26, Math.min(0.76, lightness * 1.03));
        const [red, green, blue] = hslToRgb(targetHue, targetSaturation, targetLightness);
        data[offset] = red;
        data[offset + 1] = green;
        data[offset + 2] = blue;
      }
    }
  }
}

async function processLayer(layer) {
  const source = path.join(assetsDir, `${layer.name}.png`);
  const { data, info } = await sharp(source)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  recolor(data, info.width, info.height, layer.watermark);

  const master = sharp(data, {
    raw: { width: info.width, height: info.height, channels: 4 },
  });
  const masterPath = path.join(assetsDir, `${layer.name}-v2.png`);
  await master.clone().png({ compressionLevel: 9, adaptiveFiltering: true }).toFile(masterPath);
  await master.clone().webp({ quality: 86, alphaQuality: 92, effort: 6 }).toFile(
    path.join(assetsDir, `${layer.name}-v2.webp`),
  );
  await master
    .clone()
    .resize(layer.mobile[0], layer.mobile[1], { fit: "inside", withoutEnlargement: true })
    .webp({ quality: 82, alphaQuality: 90, effort: 6 })
    .toFile(path.join(assetsDir, `${layer.name}-v2-mobile.webp`));
}

Promise.all(layers.map(processLayer)).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
