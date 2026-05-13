/**
 * Shared animation timing constants. Centralizing the magic numbers makes
 * cadence tweaks a one-file change and keeps the cascades visually coherent
 * across pages.
 *
 * All values are in milliseconds. The whole system is gated by the global
 * `prefers-reduced-motion: reduce` rule in index.css — adjusting these
 * numbers will not affect users who opt out.
 */

/** Per-item delay for staggered reveals (chapters, fix items, breakdown rows). */
export const STAGGER_STEP_MS = 70;

/** Cap on stagger index — keeps long lists from waiting too long for the tail. */
export const STAGGER_CAP = 8;

/** Within a chapter section, gap between the rule drawing and the heading. */
export const CHAPTER_HEADING_DELAY_MS = 120;

/** Within a chapter section, gap between the rule drawing and the body. */
export const CHAPTER_BODY_DELAY_MS = 220;

/** Returns the animation-delay (in ms) for the i-th item in a staggered list. */
export function staggerDelay(index: number, step: number = STAGGER_STEP_MS): number {
  return Math.min(index, STAGGER_CAP) * step;
}
