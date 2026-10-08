/**
 * Typed access to the synthetic demo drafts (generated from Team8Dataset.xlsx by
 * scripts/validate_demo_data.py — see data/demo/README.md). Featured drafts first.
 */
import type { Audience, Channel, ComplianceStatus } from '../types/api'
import { SAMPLE_TEXT } from '../services/mockData'
import raw from './demoSamples.json'

export interface DemoSample {
  id: string
  title: string
  communication_type: string
  department: string
  audience: Audience
  channel: Channel
  status_hint: ComplianceStatus
  featured: boolean
  text: string
}

const all = raw as DemoSample[]

/** Hand-written demo draft that triggers all 5 rulesets (incl. Audience Tone) even in mock mode. */
const CAREER_FAIR: DemoSample = {
  id: 'demo-career-fair',
  title: 'Fall Career Fair email — Career Services (all 5 rulesets)',
  communication_type: 'Event Announcement',
  department: 'Career Services',
  audience: 'Students',
  channel: 'Email',
  status_hint: 'Major Revisions Needed',
  featured: true,
  text: SAMPLE_TEXT,
}

export const DEMO_SAMPLES: DemoSample[] = [CAREER_FAIR, ...all.filter((s) => s.featured), ...all.filter((s) => !s.featured)]

/** The best live-demo draft (first featured). */
export const DEFAULT_DEMO_SAMPLE: DemoSample = DEMO_SAMPLES[0]
