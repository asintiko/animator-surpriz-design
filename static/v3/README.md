# Surpriz v3 cinematic microsite

`/v3/` is a dependency-free scroll-driven microsite built with the existing Flask/Jinja stack. It uses one long local scroll section and one sticky viewport stage; it is not a stack of unrelated screens and does not use a prerecorded video.

## Run locally

From the repository root:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/v3/`.

## Structure

- `templates/site/v3_cinematic.html` — semantic copy, header, scene layers, and final catalog.
- `static/v3/v3.css` — design tokens, depth bands, responsive composition, entry motion, and reduced-motion normal flow.
- `static/v3/v3.js` — local scroll measurement, deterministic timeline, image readiness, and rail interactions.
- `static/v3/assets/manifest.json` — layer roles, dimensions, anchors, depth, responsive exports, and production notes.
- `static/v3/_tools/recolor_layers.js` — reproducible palette and alpha cleanup for the versioned v2 art exports.

Z-index bands are fixed: `0–9` world, `10–19` tint, `20–29` narrative/catalog, `30–39` header, `40+` loader or modal overlays.

## Timeline map

All boundaries live in the `TIMELINE` object at the top of `v3.js`.

| Progress | Beat |
|---|---|
| `0.00–0.03` | Complete hero hold; the one-time gift entrance may play on the first visit in the tab. |
| `0.03–0.18` | Intro title exits. |
| `0.05–0.25` | Camera pushes in; foreground splits from `0.15`. |
| `0.24–0.44` | Narrative A enters, holds, and exits. |
| `0.35–0.48` | Foreground and confetti leave, revealing the panorama. |
| `0.48–0.74` | Narrative B and its three staggered steps enter, hold, and exit. |
| `0.64` | Late catalog images begin hydrating. |
| `0.75–0.88` | Catalog enters over the same world. |
| `0.84–1.00` | Catalog becomes interactive and settles into the final state. |

The visual playhead is reversible and approaches the local target only while the stage is in view. Mouse movement never changes the scene. On coarse pointers and low-power devices the expensive blur is removed. Under `prefers-reduced-motion`, sticky choreography becomes normal-flow content and every narrative beat remains available.

## Assets and production status

All served art uses optimized WebP with smaller mobile candidates. PNG masters are retained only for versioned source layers with alpha. The active palette is cream, yellow, tangerine, cobalt, lavender, and ink; the old teal exports are not referenced by the page.

There are no blocking placeholders. Ferris wheel and carousel motion is intentionally absent: they belong to one polished park plate. A future production-art pass can provide separate clean masters, but the rejected rough SVG/cropped-raster animation is not part of this build.

## Verification results

Final pass: **2026-07-21**, against the local Flask build.

| Check | Result |
|---|---|
| `1440×900`, `1280×720` | Pass — complete composition, desktop foreground depth, stable final catalog, no document overflow. |
| `1024×768`, `768×1024` | Pass — tablet landscape and portrait preserve the subject and copy; portrait switches to the open mobile composition. |
| `390×844`, `320×568`, `320×480` | Pass — no horizontal overflow, critical copy and controls remain clear, catalog is swipeable. |
| `640×360` reflow (the CSS-pixel equivalent of 200% zoom on a `1280×720` canvas) | Pass — no horizontal overflow and the compact-height rules keep the hero, navigation, and rail usable. |
| `p=0`, `.18`, `.27`, `.44`, `.58`, `.74`, `.90`, `1` | Pass — hero, both narratives, panorama, and catalog match the documented enter/hold/exit ranges without holes or text collisions. |
| Reverse scroll | Pass — after settling at `p=.27`, forward and reverse runs produce identical world, gift, intro, narrative, and rail values. |
| Mouse movement | Pass — world and gift transforms remain byte-for-byte unchanged after moving the pointer across the stage. |
| One-time entrance | Pass — the first visit runs `gift-base-enter`, `gift-burst-enter`, and `gift-shockwave-enter`; a same-tab reload runs none of them. |
| Catalog input | Pass — previous/next buttons, touch scrolling, Arrow keys, Home, and End work; the live status is throttled and focus is visible. |
| Reduced motion | Pass by branch and source verification — the media query removes sticky choreography and animation, while `renderReduced()` exposes every narrative and the catalog. The browser harness used for this pass cannot toggle the OS media preference live. |
| Loading and console | Pass — every critical layer, including confetti, decoded before reveal in the verified network profiles. A `12s` safety cap prevents a permanent inert loader after a stalled request. Cold CLS is `0.000` at `769/1024/1280px`; throttled desktop CLS is `0.00009`. No missing active assets or console errors. |

The active scene art weighs **329,694 bytes on mobile** and **766,708 bytes on desktop**, excluding fonts, logo, and late-loaded catalog photography. Desktop-only foreground images are never requested at `768px` and below.
