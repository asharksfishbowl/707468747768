/**
 * Spacing/shape tokens — Design Spec "Visual Identity": base spacing unit 8px
 * (multiples of 8 for padding/margins), corner radius 8-12px on interactive
 * surfaces, 44x44pt minimum touch target on every platform.
 */
export const spacing = {
  unit: 8,
  xs: 8,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 48,
} as const;

export const radii = {
  sm: 8,
  lg: 12,
} as const;

export const MIN_TOUCH_TARGET = 44;

/** Viewport width at which the Builder layout (and nav shell) switches from
 * mobile (full-screen-grid + drawer/tab) to the fixed 3-column web/desktop
 * layout. Design spec's "Builder Layout — Web/Desktop vs. Mobile". */
export const WEB_LAYOUT_BREAKPOINT = 900;
