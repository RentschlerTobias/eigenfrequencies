# Quarto revealjs deck — Broadsheet theme

Quarto reveal.js port of the standalone HTML deck
(`../Eigenfrequency_Aware_Optimization.html`). The look is reproduced by the
`broadsheet.scss` theme; the source markdown stays plain so the Quarto/reveal.js
features (chalkboard, menu, overview, navigation) all work.

## Build

```
quarto render slides.qmd     # → slides.html
quarto preview slides.qmd    # live preview
```

Requires the [Quarto CLI](https://quarto.org/docs/get-started/).

## Files

- `slides.qmd` — content. One `##` heading per slide; `::: {.columns}` for
  two-column layouts; nested `-` lists get turbine sub-bullets automatically.
- `broadsheet.scss` — the design system (Broadsheet): cream press-sheet ground,
  Source Serif 4 reading voice + IBM Plex Mono instrument print, IHS-logo main
  bullets, turbine-rotor sub-bullets, corner registration marks, CMYK press bar,
  U-Stuttgart wordmark (top-right) and IHS mark (bottom-left) on every content
  slide. Retune the tokens at the top of the file. The two brand marks are
  embedded as data URIs so they travel with the stylesheet (a relative `url()`
  would 404 from the compiled theme's location deep inside `slides_files/`).
- `_quarto.yml` — format config: 1920×1080 stage (so the design px map 1:1),
  theme, and the reveal features.
- `images/` — figures + `ihs_bullet.svg` / `ustutt_mark.png` (also the data-URI
  source). `embeds/` — the three interactive 3D/animation views as local HTML,
  included via raw `<iframe>` blocks.

## reveal.js features (enabled in `_quarto.yml`)

- **Chalkboard / annotations** — press `B` (chalkboard) or `C` (pen), or the
  toolbar buttons bottom-left.
- **Menu** — press `M` for the slide list (left drawer).
- **Overview grid** — press `O` (or `Esc`).
- **Slide number** `c/t`, **footer**, **progress bar**, URL `#/` hashes.
- **Navigation** — `navigation-mode: linear` (← → between slides). To stack
  slides vertically (↑ ↓), set `navigation-mode: vertical` and group them under
  a `#` section divider; reveal then arranges each section's `##` slides as a
  vertical stack.

## Bullets

Plain markdown lists render with the deck's marks automatically:

```markdown
- top-level item        ← IHS institute spiral
  - nested item         ← turbine rotor
```

No classes or raw HTML needed.
