/** Official UIC marks in public/brand (see public/brand/README.md for usage rules). */
const base = import.meta.env.BASE_URL
export const BRAND_ASSETS = {
  logo: `${base}brand/uic-logo-primary.png`,
  circleMark: `${base}brand/uic-circle-mark.png`,
} as const
