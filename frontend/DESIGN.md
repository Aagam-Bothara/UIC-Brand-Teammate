# Frontend design brief (Workstream 4)

## Product name and minimalism (v2: overrides anything below)
- Product name: **UIC Brand Teammate**, always written in full (header: official UIC logo, divider, then "UIC Brand Teammate").
- **Minimal:** show only what the user needs for the next step. One short sentence max per card;
  no eyebrow labels, no marketing hero, no step-number headings, no explanatory paragraphs that
  repeat what the UI already says. Descriptions become tooltips (`title`) or disappear.
  Prefer whitespace over borders, one primary button per area, secondary actions as quiet icon/text
  buttons. Hide advanced detail behind disclosure (collapsed by default).
- Official logo: `public/brand/uic-logo-primary.png` (full color, white/light backgrounds only) and
  `public/brand/uic-circle-mark.png`. Never recolor, stretch, crop tighter or add effects; keep clear
  space (≥ the height of the "UIC" letters around it). See public/brand/README.md.

Goal: a calm, polished, friendly editorial tool that feels like a UIC product. Users are faculty and
staff, not designers — no training needed (SPEC NFR-4). Every screen should make the next step obvious.

## Visual language
- **Canvas:** `bg-uic-expo` (Expo White #F6F3EC). Content sits on white cards:
  `bg-white rounded-2xl border border-black/5 shadow-sm`, padding `p-5 sm:p-6`.
- **Brand:** Navy Pier Blue `uic-navy` for headings, primary buttons and focus; Flames Red `uic-red`
  only as an accent (brand bar, the "UIC" mark, destructive actions). Body text `text-uic-steel`;
  secondary text `text-uic-steel/70`.
- **Type:** Inter/system sans. Page title `text-2xl sm:text-3xl font-semibold tracking-tight text-uic-navy`;
  card titles `text-base font-semibold text-uic-navy`; body `text-sm sm:text-[15px] leading-relaxed`;
  labels/eyebrows `text-xs font-medium uppercase tracking-wide text-uic-steel/60`.
- **Buttons:** primary `bg-uic-navy text-white hover:bg-uic-navy/90 rounded-xl px-4 py-2.5 font-medium shadow-sm`;
  secondary `bg-white border border-black/10 hover:bg-black/[0.03] rounded-xl`; ghost for icon buttons.
  Disabled `opacity-50 cursor-not-allowed`. Min touch target 40px.
- **Pills/chips:** `rounded-full px-2.5 py-0.5 text-xs font-medium`.
- **Icons:** `lucide-react`, 16–18px, `aria-hidden` unless the icon is the only label.
- **Motion:** `transition` 150–200ms on hover/press/toggle; subtle fade/slide for reveals. Respect
  `prefers-reduced-motion` (already global in index.css).
- **Ruleset colors** come from `RULESETS[id].highlight_color` (src/config/rulesets.ts). Highlight =
  background tint at ~15% alpha (`${color}26`) + 2px bottom border in the full color. ALWAYS pair
  color with a text label/icon (WCAG 1.4.1).
- **Status colors:** Approved `#00966C`, Minor Revisions `#B45309`, Major Revisions `#D50032`.
- **Empty / loading / error states** are first-class: friendly copy, an icon, and one clear action.
  Use skeleton shimmer (`animate-pulse bg-black/5 rounded`) while analyzing.

## Accessibility (WCAG 2.1 AA, SPEC NFR-5)
Semantic HTML, labelled controls, visible focus (`:focus-visible` is global), keyboard operable
(toggles are real buttons/checkboxes, Esc closes popovers), `aria-live="polite"` for async results,
contrast ≥ 4.5:1 for text.

## Shared code — do NOT edit (owned by the lead; report needed changes instead)
`src/types/api.ts`, `src/config/rulesets.ts`, `src/lib/*`, `src/services/*`, `src/context/*`,
`src/index.css`. Components read state through `useText()`, `useRulesets()`, `useUI()`.
