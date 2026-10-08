/**
 * Flesch–Kincaid grade level — a port of Workstream 2's backend/services/reading_level.py
 * (same word regex, syllable heuristic + overrides, and sentence splitting that ignores
 * abbreviation periods and treats line breaks as sentence ends), so client-side estimates and the
 * mock analyzer agree with the backend's authoritative grade.
 */

const WORD_RE = /[A-Za-z]+(?:['’][A-Za-z]+)*/g

/** Abbreviations whose trailing period should not end a sentence. */
const ABBREVIATIONS = [
  'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Sr.', 'Jr.', 'St.', 'vs.', 'etc.',
  'e.g.', 'i.e.', 'a.m.', 'p.m.', 'A.M.', 'P.M.', 'U.S.', 'Ph.D.', 'No.',
  'Jan.', 'Feb.', 'Aug.', 'Sept.', 'Oct.', 'Nov.', 'Dec.', 'Univ.', 'Dept.',
]
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const ABBREV_RE = new RegExp(
  `(?<![\\p{L}\\p{N}_])(${[...ABBREVIATIONS].sort((a, b) => b.length - a.length).map(escapeRe).join('|')})`,
  'gu',
)
/** Abbreviations that often end a sentence ("...at 3 p.m. Join us"). */
const TERMINAL_ABBREVIATIONS = new Set(['a.m.', 'p.m.', 'etc.'])
/** A sentence ends at . ! ? (optionally followed by closing quotes/brackets) or at a line break. */
const SENTENCE_END_RE = /[.!?]+["'’”)\]]*(?=\s|$)|\n+/g

/** Words the vowel-group heuristic gets wrong. */
const SYLLABLE_OVERRIDES: Record<string, number> = {
  the: 1, every: 3, people: 2, business: 2, area: 3, idea: 3,
  create: 2, created: 3, being: 2, science: 2, sciences: 3,
  university: 5, chicago: 3, illinois: 3, via: 2, quiet: 2,
  poem: 2, real: 1, really: 2, toward: 2, towards: 2,
  naive: 2, orientation: 5, evaluate: 4, academic: 4,
}

export function countSyllables(word: string): number {
  let w = word.toLowerCase().replace(/[^a-z]/g, '')
  if (!w) return 0
  if (w in SYLLABLE_OVERRIDES) return SYLLABLE_OVERRIDES[w]
  if (w.length <= 3) return 1
  // Drop silent endings: -es, -ed (but not -ted/-ded), trailing silent -e (but not -le).
  if (w.endsWith('es') && !/(?:ses|zes|ces|ges|xes|ches|shes)$/.test(w)) w = w.slice(0, -2)
  else if (w.endsWith('ed') && !/(?:ted|ded)$/.test(w)) w = w.slice(0, -2)
  else if (w.endsWith('e') && !/(?:le|ee|ye)$/.test(w)) w = w.slice(0, -1)
  let count = (w.match(/[aeiouy]+/g) ?? []).length
  // Vowel pairs that are usually two syllables: "ia" (media), "ua" (actual), "eo" (video).
  count += (w.match(/(?<![aeioucgst])ia|(?<![qg])ua|eo/g) ?? []).length
  return Math.max(1, count)
}

const trimSpan = (text: string, start: number, end: number): string => text.slice(start, end).trim()
const hasWord = (s: string) => /[A-Za-z]/.test(s)

/** Number of sentences, as backend split_sentences() counts them. */
export function countSentences(text: string): number {
  const masked = text.replace(ABBREV_RE, (abbr: string, _g: string, offset: number) => {
    if (TERMINAL_ABBREVIATIONS.has(abbr.toLowerCase()) && /^\s+[A-Z]/.test(text.slice(offset + abbr.length))) return abbr
    return abbr.replace(/\./g, '\u0000')
  })
  let n = 0
  let pos = 0
  for (const m of masked.matchAll(SENTENCE_END_RE)) {
    const end = m.index + m[0].length
    if (hasWord(trimSpan(text, pos, end))) n++
    pos = end
  }
  if (hasWord(trimSpan(text, pos, text.length))) n++
  return n
}

export function fleschKincaidGrade(text: string): number {
  const words = text.match(WORD_RE) ?? []
  if (words.length === 0) return 0
  const sentences = Math.max(1, countSentences(text))
  const syllables = words.reduce((n, w) => n + countSyllables(w), 0)
  const grade = 0.39 * (words.length / sentences) + 11.8 * (syllables / words.length) - 15.59
  return Math.round(Math.max(0, grade) * 10) / 10
}
