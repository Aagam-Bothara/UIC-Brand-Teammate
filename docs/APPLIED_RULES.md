# Applied Rules

All 77 rules in `rulesets/*.json` are enabled. This is a quick-reference summary as of 2026-10-08. For full keyword lists, messages and source links, see [RULES_REVIEW.md](RULES_REVIEW.md), which is generated from the rule files.

**Applies to** shows when a rule runs. "all" means every audience (students, faculty, staff) and every channel (email, website, social media). **Severity** sets the score deduction: high −10, medium −5, low −2.

## Summary

| Ruleset | Rules | High | Medium | Low |
|---|---|---|---|---|
| Brand | 19 | 2 | 11 | 6 |
| Accessibility | 10 | 2 | 3 | 5 |
| Content & Style | 31 | 0 | 4 | 27 |
| Reading Level | 5 | 0 | 3 | 2 |
| Audience Tone | 12 | 1 | 3 | 8 |
| **Total** | **77** | **5** | **24** | **48** |

## Brand (19)

| ID | Rule | Severity | Example → fix | Applies to | Source |
|---|---|---|---|---|---|
| brand-001 | Official name has no "at" | high | University of Illinois at Chicago → University of Illinois Chicago | all | UIC Name & boilerplate |
| brand-002 | No hyphen/punctuation in the name | high | University of Illinois-Chicago → University of Illinois Chicago | all | UIC Name & boilerplate |
| brand-003 | No periods in UIC | medium | U.I.C. → UIC | all | Inferred from UIC naming |
| brand-004 | Unofficial abbreviation | medium | U of I Chicago, UI Chicago → UIC | all | Inferred from UIC naming |
| brand-005 | Abbreviated university name | medium | Univ. of Ill. → University of Illinois Chicago | all | Inferred from UIC naming |
| brand-006 | Full name on first reference | medium | First mention is "UIC" → University of Illinois Chicago | all (team decision) | UIC Name & boilerplate |
| brand-007 | UIC is always uppercase | medium | uic, Uic → UIC (URLs/emails ignored) | all | Inferred from UIC naming |
| brand-008 | Redundant "UIC University" | medium | UIC University → UIC | all | Inferred from UIC naming |
| brand-009 | Incomplete name | medium | Illinois-Chicago → UIC | all | Inferred from UIC naming |
| brand-010 | Former campus name | low | Chicago Circle, UICC → UIC | all | UIC Editorial guide |
| brand-011 | "University of Illinois" alone | low | University of Illinois → University of Illinois Chicago | all | UIC Editorial guide |
| brand-012 | "U of I" alone | low | U of I → UIC ("U of I System" is OK) | all | UIC Editorial guide |
| brand-013 | Lowercase standalone "university" | low | the University → the university | all | UIC Editorial guide |
| brand-014 | No "(UIC)" after the full name | medium | University of Illinois Chicago (UIC) → University of Illinois Chicago | all | UIC Name & boilerplate |
| brand-015 | The "C rule" | medium | UICampus → UIC campus | all | UIC Editorial guide |
| brand-016 | UI Health naming | medium | UIC Hospital, UIH, UIMC → UI Health; UI Cancer Center → University of Illinois Cancer Center | all | UIC Editorial guide |
| brand-017 | Former unit/building names | medium | Chicago Circle Center → UIC Student Center East; John Marshall Law School → UIC School of Law | all | UIC Editorial guide |
| brand-018 | UIC proper names | low | GCC → Great Cities Commitment; Jane Adams → Jane Addams; UIC Today → UIC today | all | UIC Editorial guide |
| brand-019 | Campus regions | low | east campus → the east side of campus | all | UIC Editorial guide |

## Accessibility (10)

| ID | Rule | Severity | Example → fix | Applies to | Source |
|---|---|---|---|---|---|
| access-001 | Non-descriptive link text | medium | click here, read more → describe the destination | all | WCAG 2.1 AA |
| access-002 | ALL CAPS text | medium | CLICK HERE → sentence case | all | WCAG + UIC Editorial guide |
| access-003 | Disability language | high | suffers from → has; wheelchair-bound → wheelchair user; hearing-impaired → hard of hearing | all | UIC Inclusive Language Guide |
| access-004 | Image without alt text | high | `![](photo.png)`, `<img>` with no alt → add alt text | all | UIC Social media + WCAG |
| access-005 | Raw URL as link text | low | https://… → descriptive link text | email, website | WCAG 2.1 AA |
| access-006 | Sensory/directional wording | low | see below, in red → name the item | all | WCAG 2.1 AA |
| access-007 | Unfamiliar acronym | low | OSA → use the full name | all | UIC Editorial guide |
| access-008 | Too many emojis | low | more than 3 emojis → remove extras | all | Team-defined |
| access-009 | Hashtag not CamelCase | low | #uicorientation → #UICOrientation | social | Team-defined |
| access-010 | Details only in a flyer/image | medium | see attached flyer → put details in text | all | WCAG 2.1 AA |

## Content & Style (31)

| ID | Rule | Severity | Example → fix | Applies to | Source |
|---|---|---|---|---|---|
| content-001 | "email" spelling | low | e-mail → email | all | UIC Editorial guide |
| content-002 | "website" spelling | low | web site → website | all | UIC Editorial guide |
| content-003 | Time format | low | 3:00 PM → 3 p.m.; 12 PM → noon | all | UIC Editorial guide |
| content-004 | No "12 noon" | low | 12 noon → noon | all | UIC Editorial guide |
| content-005 | No ordinals in dates | low | October 15th → October 15 | all | UIC Editorial guide |
| content-006 | Wordy phrase | low | in order to → to; prior to → before | all | UIC Voice & tone |
| content-007 | Repeated word | medium | the the → the | all | UIC Social media |
| content-008 | One space between sentences | low | double space → single | all | UIC Editorial guide |
| content-009 | Ampersand only in formal names | low | staff & students → staff and students | all | UIC Editorial guide |
| content-010 | Phone format (parentheses) | low | (312) 555-0100 → 312-555-0100 | all | UIC Editorial guide |
| content-011 | Social post too long | medium | over 500 characters | social | UIC Social media + team limit |
| content-012 | Email too long | low | over 200 words | email | UIC Voice & tone + team limit |
| content-013 | Phone format (periods) | low | 312.555.0100 → 312-555-0100 | all | UIC Editorial guide |
| content-014 | Month abbreviations | low | September 3 → Sept. 3; Mar. → March | all | UIC Editorial guide |
| content-015 | UIC preferred spellings | low | on-line → online; health care → healthcare; theater → theatre | all | UIC Editorial guide |
| content-016 | Preferred UIC terms | medium | freshman → first-year student; dorm → residence hall | all | UIC Editorial guide |
| content-017 | Degree style | low | Ph.D. → PhD; Bachelors degree → bachelor's degree | all | UIC Editorial guide |
| content-018 | Use the % sign | low | 5 percent → 5% | all | UIC Editorial guide |
| content-019 | Spell out street suffixes | low | Halsted St. → Halsted Street (numbered addresses OK) | all | UIC Editorial guide |
| content-020 | No state after Chicago | low | Chicago, Illinois → Chicago | all | UIC Editorial guide |
| content-021 | No multiple exclamation points | medium | !! → ! | all | UIC Editorial guide |
| content-022 | No serial comma | low | pen, paper, and laptop → pen, paper and laptop | all | UIC Editorial guide |
| content-023 | Spell out one through nine | low | 3 new advisers → three new advisers | all | UIC Editorial guide |
| content-024 | Avoid em dashes (electronic) | low | great—really → comma/colon/parentheses, or " — " | all (team decision) | UIC Editorial guide |
| content-025 | "No." for rankings | low | #1 → No. 1 | all | UIC Editorial guide |
| content-026 | Lowercase mid-sentence terms | low | the Fall semester → the fall semester | all | UIC Editorial guide |
| content-027 | Periods inside quotes | low | "historic". → "historic." | all | UIC Editorial guide |
| content-028 | e.g./i.e. periods | low | e.g → e.g. | all | UIC Editorial guide |
| content-029 | Mail code format | low | M/C 289 → MC 289 | all | UIC Editorial guide |
| content-030 | No hyphen after -ly adverbs | low | easily-remembered → easily remembered | all | UIC Editorial guide |
| content-031 | No "the" before CPS | low | the Chicago Public Schools → Chicago Public Schools | all | UIC Editorial guide |

## Reading Level (5)

| ID | Rule | Severity | Example → fix | Applies to | Source |
|---|---|---|---|---|---|
| reading-001 | Reading level above target | medium (high if 3+ grades over) | Above grade 8 (students) / 10 (faculty, staff) → simplify | all | Team-defined (SPEC) |
| reading-002 | Hard-to-read sentence | medium | One sentence 4+ grades over target → simplify | all | Team-defined (SPEC) |
| reading-003 | Long sentence | medium | Over 20 words (students) / 25 (faculty, staff) → split | all | UIC Voice & tone + team limit |
| reading-004 | Long paragraph | low | Over 100 words or 5 sentences → break up | all | Team-defined (SPEC) |
| reading-005 | Plain-language words | low | utilize → use; facilitate → help | all | UIC Voice & tone + team list |

## Audience Tone (12)

| ID | Rule | Severity | Example → fix | Applies to | Source |
|---|---|---|---|---|---|
| tone-001 | Overly casual language | medium | gonna, lol, btw → standard wording | faculty, staff | UIC Social media + team list |
| tone-002 | Gendered language | medium | hey guys → Hi everyone; chairman → chairperson; his or her → their | all | UIC Inclusive Language Guide |
| tone-003 | Academic/legal jargon | low | matriculate → enroll; pursuant to → under | students | Team-defined (SPEC) |
| tone-004 | Negative/threatening framing | low | failure to, strictly prohibited → reframe positively | all | UIC Inclusive Language Guide |
| tone-005 | Bureaucratic phrasing | low | it is requested that → please | all | UIC Voice & tone |
| tone-006 | Exclamation points rarely | low | more than 1 → use a period | email, website | UIC Editorial guide |
| tone-007 | Race and ethnicity terms | medium | minorities → name the groups; African-American → African American; BIPOC → people of color | all | UIC Inclusive Language Guide |
| tone-008 | Immigration terms | high | illegal immigrant → immigrant lacking permanent legal status | all | UIC Inclusive Language Guide |
| tone-009 | Deficit framing | low | disadvantaged → under-resourced; the homeless → people experiencing homelessness | all | UIC Inclusive Language Guide |
| tone-010 | Avoid "empower" | low | empower → name the tools/resources | all | UIC Inclusive Language Guide |
| tone-011 | You-centered invitations | low | Join us for → You're invited to | all | UIC Inclusive Language Guide |
| tone-012 | Gender-neutral alumni terms | low | alumni → alums; alumna → alum (Alumni Association OK) | all (team decision) | UIC Inclusive Language Guide |
