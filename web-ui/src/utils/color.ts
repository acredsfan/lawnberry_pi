/**
 * UI Color Utilities
 * Central helpers for dynamic palette-based coloring to avoid incorrect
 * usage of dotted palette keys (e.g. 'success.main') as raw color strings.
 */
import { Theme } from '@mui/material/styles';

/** Return battery color (full palette color value) based on level. */
export function batteryLevelColor(theme: Theme, level?: number) {
  if (typeof level !== 'number') return theme.palette.text.secondary;
  if (level > 60) return theme.palette.success.main;
  if (level > 30) return theme.palette.warning.main;
  return theme.palette.error.main;
}

/** Return signal strength color (palette value) */
export function signalStrengthColor(theme: Theme, strength: number) {
  if (strength > 50) return theme.palette.success.main;
  if (strength > 20) return theme.palette.warning.main;
  return theme.palette.error.main;
}

/**
 * Development guard: detects accidental dotted palette strings passed as color.
 * Call with any style object; it mutates nothing but logs a warning when misuse found.
 */
export function guardDottedPaletteMisuse(style: any, context: string) {
  // Only run in dev (Vite provides import.meta.env.PROD flag)
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if ((import.meta as any).env?.PROD) return; // only in development
  if (!style) return;
  try {
    const check = (obj: any) => {
      if (!obj || typeof obj !== 'object') return;
      for (const key of Object.keys(obj)) {
        const val = (obj as any)[key];
        if (typeof val === 'string' && /^(success|warning|error|info|primary|secondary)\.main$/.test(val)) {
          // eslint-disable-next-line no-console
          console.warn(`[palette-guard] Dotted palette token '${val}' detected in ${context}. Use theme.palette.*.main via function instead.`);
        } else if (val && typeof val === 'object') {
          check(val);
        }
      }
    };
    check(style);
  } catch {
    // swallow
  }
}
