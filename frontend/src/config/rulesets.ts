import type { Audience, AudienceInfo, Channel, RulesetId, RulesetInfo } from '../types/api'

/** SPEC 1 order — also the progressive-reveal order. */
export const RULESET_ORDER: RulesetId[] = ['brand', 'accessibility', 'content', 'reading_level', 'audience_tone']

/**
 * Static ruleset metadata (fallback for GET /api/rules). Colors match Workstream 2's
 * rulesets/*.json `highlight_color` and stay legible as light highlight tints; every highlight also carries a text label, so color is
 * never the only signal (WCAG 1.4.1).
 */
export const RULESETS: Record<RulesetId, RulesetInfo> = {
  brand: {
    ruleset_id: 'brand',
    ruleset_name: 'Brand',
    description: 'Official names, UIC terminology and editorial style.',
    highlight_color: '#3B82F6',
    enabled: true,
    rule_count: 19,
  },
  accessibility: {
    ruleset_id: 'accessibility',
    ruleset_name: 'Accessibility',
    description: 'Descriptive links, alt text, structure and plain language.',
    highlight_color: '#10B981',
    enabled: true,
    rule_count: 10,
  },
  content: {
    ruleset_id: 'content',
    ruleset_name: 'Content',
    description: 'Clear calls to action, contact details, dates and times.',
    highlight_color: '#F59E0B',
    enabled: true,
    rule_count: 31,
  },
  reading_level: {
    ruleset_id: 'reading_level',
    ruleset_name: 'Reading Level',
    description: 'Shorter sentences and simpler words for the audience’s grade target.',
    highlight_color: '#8B5CF6',
    enabled: true,
    rule_count: 5,
  },
  audience_tone: {
    ruleset_id: 'audience_tone',
    ruleset_name: 'Audience Tone',
    description: 'UIC voice and tone, adjusted for the selected audience.',
    highlight_color: '#EC4899',
    enabled: true,
    rule_count: 12,
  },
}

export const AUDIENCES: AudienceInfo[] = [
  { id: 'Students', label: 'Students', description: 'Current and prospective students', reading_level_target: 8 },
  { id: 'Faculty', label: 'Faculty', description: 'Instructors and researchers', reading_level_target: 10 },
  { id: 'Staff', label: 'Staff', description: 'University staff and administrators', reading_level_target: 10 },
]

export const CHANNELS: { id: Channel; label: string; description: string }[] = [
  { id: 'Email', label: 'Email', description: 'Newsletters and announcements' },
  { id: 'Website', label: 'Website', description: 'Web pages and news posts' },
  { id: 'Social Media', label: 'Social Media', description: 'Short posts and captions' },
]

export const READING_LEVEL_TARGET: Record<Audience, number> = {
  Students: 8,
  Faculty: 10,
  Staff: 10,
}

/** SPEC FR-1: 5,000 word practical maximum. */
export const MAX_WORDS = 5000
/** Matches the backend text limit (~5,000 words). */
export const MAX_CHARS = 40000
