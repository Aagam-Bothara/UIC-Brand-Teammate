# Rules Review

Every rule the engine checks, generated from `rulesets/*.json` by
`scripts/generate_rules_review.py`. Do not edit by hand.

**Source** says where each rule comes from:
- **UIC …**: stated on brand.uic.edu (Name and boilerplate, Editorial and Style Guide,
  Inclusive Language Guide, Voice and tone, Social media guidelines).
- **Inferred from UIC …**: follows from a UIC rule but isn't spelled out word for word.
- **WCAG 2.1 AA**: UIC's ADA compliance page requires WCAG 2.1 AA but gives no specific
  writing rules, so these checks come from WCAG.
- **Team-defined**: our own threshold or word list (from the SPEC), not from UIC.

Severity deducts from the score: high −10, medium −5, low −2.

## Summary

| Ruleset | Rules | From UIC site | Inferred | WCAG | Team-defined |
|---|---|---|---|---|---|
| Brand Compliance Rules | 19 | 13 | 6 | 0 | 0 |
| Accessibility Rules | 10 | 3 | 0 | 5 | 2 |
| Content & Style Rules | 31 | 31 | 0 | 0 | 0 |
| Reading Level Rules | 5 | 2 | 0 | 0 | 3 |
| Audience Tone Rules | 12 | 11 | 0 | 0 | 1 |

## Brand Compliance Rules (`brand`)

University naming and UIC-specific terminology from brand.uic.edu.

| ID | Rule | Severity | What it flags | Fix | Source | Applies to |
|---|---|---|---|---|---|---|
| brand-001 | Official name has no "at" | high | Don't put "at" between Illinois and Chicago. The official name is University of Illinois Chicago. | University of Illinois Chicago | [UIC Name and boilerplate](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-002 | No hyphen or punctuation in the name | high | Don't put a hyphen (or other punctuation) between Illinois and Chicago. | University of Illinois Chicago | [UIC Name and boilerplate](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-003 | No periods in UIC | medium | The acronym is "UIC" with no periods. | UIC | [Inferred from UIC Name and boilerplate (official acronym "UIC")](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-004 | Unofficial abbreviation of the name | medium | The only approved short form is "UIC". | UIC | [Inferred from UIC Name and boilerplate (official acronym "UIC")](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-005 | Abbreviated university name | medium | Use the full name, University of Illinois Chicago, or "UIC". | University of Illinois Chicago | [Inferred from UIC Name and boilerplate (use the full name wherever possible)](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-006 | Full name on first reference | medium | Spell out University of Illinois Chicago on first reference; "UIC" is fine afterward. | University of Illinois Chicago | [UIC Name and boilerplate (use the full name wherever possible; applied to all audiences and channels by team decision)](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-007 | UIC is always uppercase | medium | Write "UIC" in capital letters (web and email addresses are fine). | UIC | [Inferred from UIC Name and boilerplate (official acronym "UIC")](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-008 | Redundant "UIC University" | medium | "UIC" already includes "University". | UIC | [Inferred from UIC Name and boilerplate](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-009 | Incomplete name "Illinois Chicago" | medium | Use the full name, University of Illinois Chicago, or "UIC". | UIC | [Inferred from UIC Name and boilerplate](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-010 | Former campus name (Chicago Circle) | low | Chicago Circle / UICC are former names. Use University of Illinois Chicago or UIC unless you are writing about history. | UIC | [UIC Editorial guide: UIC Student Center East (former names)](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-011 | "University of Illinois" alone is ambiguous | low | Use "University of Illinois" sparingly; the public usually takes it to mean Urbana-Champaign. Name the campus. | University of Illinois Chicago | [UIC Editorial guide: University of Illinois System](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-012 | "U of I" alone is ambiguous | low | "U of I" is approved only in "U of I System". Use "UIC" for this university. | UIC | [UIC Editorial guide: University of Illinois System](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-013 | Lowercase "university" when it stands alone | low | Capitalize "university" only in formal names; lowercase it when it stands alone. | university | [UIC Editorial guide: University, college](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-014 | No "(UIC)" after the full name | medium | Don't put "UIC" in parentheses after the full name. Just use "UIC" on later references. | University of Illinois Chicago | [UIC Name and boilerplate; Editorial guide: University of Illinois Chicago](https://brand.uic.edu/messaging/name-and-boilerplate/) | all |
| brand-015 | The "C rule": space after UIC | medium | Always put a space between UIC and the next word, and don't let the C in UIC start the next word (not "UICampus"). | UIC + space + full word (e.g. "UIC campus") | [UIC Editorial guide: C rule](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-016 | UI Health naming | medium | "University of Illinois Medical Center" → "UI Health"; "UIC Hospital" → "UI Health"; "UIH" → "UI Health"; "UIHHSS" → "UI Health"; "UIMC" → "UI Health"; "UI Cancer Center" → "University of Illinois Cancer Center"; "UI Health faculty" → "UIC faculty"; "UI Health College of" → "University of Illinois Chicago College of" | per match | [UIC Editorial guide: UI Health; University of Illinois Cancer Center](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-017 | Former names of UIC units and buildings | medium | "Chicago Circle Center" → "UIC Student Center East"; "Chicago Illini Union" → "UIC Student Center West"; "John Marshall Law School" → "University of Illinois Chicago School of Law"; "University Administration" → "System Offices" | per match | [UIC Editorial guide: Student Center East/West; School of Law; System Offices](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-018 | UIC proper names and spellings | low | "GCC" → "Great Cities Commitment"; "Jane Adams" → "Jane Addams"; "Hull House" → "Hull-House"; "UIC Today" → "UIC today"; "UIC's Department" → "the UIC Department"; "UI-Health" → "UI Health" | per match | [UIC Editorial guide: Great Cities Commitment; Jane Addams Hull-House Museum; UIC today; Department names](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| brand-019 | Campus regions | low | "east campus" → "the east side of campus"; "west campus" → "the west side of campus" | per match | [UIC Editorial guide: Campus regions](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |

## Accessibility Rules (`accessibility`)

Disability-inclusive language and WCAG 2.1 AA content checks (UIC requires WCAG 2.1 AA).

| ID | Rule | Severity | What it flags | Fix | Source | Applies to |
|---|---|---|---|---|---|---|
| access-001 | Non-descriptive link text | medium | "click here"; "click this link"; "this link"; "read more"; "learn more"; "more info"; "link here" | Describe where the link goes | [WCAG 2.1 AA (required by UIC ADA compliance page)](https://www.w3.org/WAI/WCAG21/Understanding/link-purpose-in-context.html) | all |
| access-002 | ALL CAPS text | medium | Avoid phrases in all capital letters; some screen readers spell them out. Use sentence case. | Use sentence case | [WCAG 2.1 AA (required by UIC ADA compliance page); UIC Editorial guide: Capitalization (avoid unnecessary capitals)](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| access-003 | Disability language | high | "suffers from" → "has"; "suffer from" → "have"; "suffering from" → "living with"; "a victim of" → "(state the facts neutrally)"; "handi-capable" → "disabled"; "differently abled" → "disabled"; "differently-abled" → "disabled"; "physically challenged" → "disabled"; +25 more | per match | [UIC Inclusive Language Guide: Disability](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| access-004 | Image without alt text | high | Every image needs alt text that describes it for blind users. | Add descriptive alt text | [UIC Social media guidelines (alt text on every photo); WCAG 2.1 AA (required by UIC ADA compliance page)](https://brand.uic.edu/resources/social-media-guidelines/) | all |
| access-005 | Raw URL as link text | low | Screen readers read raw URLs character by character. Link descriptive text instead. | Use descriptive link text | [WCAG 2.1 AA (required by UIC ADA compliance page)](https://www.w3.org/WAI/WCAG21/Understanding/link-purpose-in-context.html) | email, website |
| access-006 | Sensory or directional instructions | low | "see below"; "see above"; "shown below"; "shown above"; "the image above"; "the image below"; "in red"; "in green"; +4 more | Refer to the item by name | [WCAG 2.1 AA (required by UIC ADA compliance page)](https://www.w3.org/WAI/WCAG21/Understanding/sensory-characteristics.html) | all |
| access-007 | Unfamiliar acronym | low | Avoid acronyms except broadly understood ones like UIC. | computed per match | [UIC Editorial guide: Abbreviations; Acronyms](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| access-008 | Too many emojis | low | Limit emojis; screen readers announce each one by name. | Remove extra emojis | [Team-defined (accessibility best practice; not on the UIC site)](https://brand.uic.edu/resources/social-media-guidelines/) | all |
| access-009 | Hashtag not in CamelCase | low | Capitalize each word in multi-word hashtags (e.g. #UICFlamesForward) so screen readers pronounce them correctly. | Capitalize each word in the hashtag | [Team-defined (accessibility best practice; not on the UIC site)](https://brand.uic.edu/resources/social-media-guidelines/) | social |
| access-010 | Details only in an image or attachment | medium | "see attached flyer"; "see the attached flyer"; "see flyer"; "see image for details"; "see the image for details"; "details in the image"; "details in the flyer" | Include the details in the message text | [WCAG 2.1 AA (required by UIC ADA compliance page)](https://www.w3.org/WAI/WCAG21/Understanding/images-of-text.html) | all |

## Content & Style Rules (`content`)

UIC Editorial and Style Guide (AP-based, with UIC departures) and channel checks.

| ID | Rule | Severity | What it flags | Fix | Source | Applies to |
|---|---|---|---|---|---|---|
| content-001 | "email" spelling | low | Spell it "email" (no hyphen). | email\1 | [UIC Editorial guide: Email](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-002 | "website" spelling | low | Spell it "website", one word. | website\1 | [UIC Editorial guide: Web](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-003 | Time format | low | Lowercase a.m./p.m. with periods, omit ":00", and use noon/midnight ("4 p.m.", not "4:00 PM"). | computed per match | [UIC Editorial guide: a.m./p.m.; Time](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-004 | No "12 noon" | low | Write "noon" or "midnight" (never "12 noon"). | \1 | [UIC Editorial guide: Time](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-005 | No st/nd/rd/th in dates | low | Use numerals without -st, -nd, -rd or -th ("May 10"). | \1 | [UIC Editorial guide: Dates](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-006 | Wordy phrase | low | "in order to" → "to"; "due to the fact that" → "because"; "at this point in time" → "now"; "at this time" → "now"; "in the event that" → "if"; "for the purpose of" → "for"; "prior to" → "before"; "with regard to" → "about"; +4 more | per match | [UIC Voice and tone: "no fluff", no filler](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| content-007 | Repeated word | medium | This word is repeated. | \1 | [UIC Social media guidelines (posts must be grammatically correct)](https://brand.uic.edu/resources/social-media-guidelines/) | all |
| content-008 | One space between sentences | low | Use one space after a period and between words. |   | [UIC Editorial guide: Spacing](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-009 | Ampersand only in formal names | low | Use "&" only in formal names; otherwise spell out "and". | and | [UIC Editorial guide: Ampersand](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-010 | Phone number format (parentheses) | low | Include the area code, use hyphens, no parentheses. | \1-\2-\3 | [UIC Editorial guide: Phone numbers](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-011 | Social post too long | medium | Social posts should be brief and fit the platform. | Shorten the post | [UIC Social media guidelines ("typically brief"); 500-character limit is team-defined](https://brand.uic.edu/resources/social-media-guidelines/) | social |
| content-012 | Email too long | low | Lead with the key point and link to details. | Shorten the email or link to details | [UIC Voice and tone ("short, sharp and direct"); 200-word limit is team-defined](https://brand.uic.edu/messaging/voice-and-tone/) | email |
| content-013 | Phone number format (periods) | low | Use hyphens in phone numbers. | \1-\2-\3 | [UIC Editorial guide: Phone numbers](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-014 | Month abbreviations | low | Abbreviate Jan., Feb., Aug., Sept., Oct., Nov., Dec. only with a specific date; always spell out March-July. | computed per match | [UIC Editorial guide: Dates](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-015 | UIC preferred spellings | low | "on-line" → "online"; "web page" → "webpage"; "web pages" → "webpages"; "home page" → "homepage"; "web cam" → "webcam"; "voice mail" → "voicemail"; "fund raising" → "fundraising"; "fund-raising" → "fundraising"; +21 more | per match | [UIC Editorial guide: Online; Web; Homepage; Voicemail; Fundraise; Healthcare; Childcare; Textbook; Campuswide; Listserv; Fact sheet; Student-athlete; Alma mater; Vice; Theatre](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-016 | Preferred UIC terms | medium | "freshman" → "first-year student"; "freshmen" → "first-year students"; "dorm" → "residence hall"; "dorms" → "residence halls"; "dormitory" → "residence hall"; "dormitories" → "residence halls" | per match | [UIC Editorial guide: Class levels; Residence hall; Inclusive Language Guide](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-017 | Degree style | low | "Ph.D." → "PhD"; "Ph.D" → "PhD"; "M.D." → "MD"; "B.S." → "BS"; "B.A." → "BA"; "M.A." → "MA"; "M.S." → "MS"; "M.B.A." → "MBA"; +14 more | per match | [UIC Editorial guide: Degrees; GPA; PhD](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-018 | Use the % sign | low | Use the % symbol with numerals ("5%"). | \1% | [UIC Editorial guide: Percentage](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-019 | Spell out street suffixes | low | Spell out Street, Avenue, Road, etc. St., Ave. and Blvd. are acceptable only in numbered addresses. | computed per match | [UIC Editorial guide: Streets](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-020 | Don't add the state after Chicago | low | Don't add "Illinois" after "Chicago". | Chicago | [UIC Editorial guide: City of Chicago](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-021 | Never use multiple exclamation points | medium | Exclamation points are used rarely, and never two or more in a row. | ! | [UIC Editorial guide: Exclamation point](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-022 | No serial (Oxford) comma | low | No comma before the final "and"/"or" in a simple series ("red, white and blue"). Keep it only if an item contains its own conjunction. | (remove this comma) | [UIC Editorial guide: Commas in a series](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-023 | Spell out one through nine | low | Spell out numbers one through nine; use figures for 10 and above (dates, times, ages, addresses and percentages use numerals). | computed per match | [UIC Editorial guide: Numbers](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-024 | Avoid em dashes in electronic copy | low | Em dashes may turn into hyphens in electronic documents. Use a comma, colon or parentheses instead; if you keep the dash, put a space on both sides. | Use a comma, colon or parentheses (or " — ") | [UIC Editorial guide: Dash; Punctuation (avoid em dashes in documents transmitted electronically)](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-025 | Use "No." for rankings | low | Use "No." before rank numerals ("No. 1"). | No. \1 | [UIC Editorial guide: Rank](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-026 | Lowercase mid-sentence terms | low | Lowercase this word unless it starts a sentence or is part of a formal name. | computed per match | [UIC Editorial guide: Semester; Email; Internet; Homepage; Online; Dean's list; Capitalization](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-027 | Periods go inside quotation marks | low | Periods and commas always go inside the closing quotation mark. | \2\1 | [UIC Editorial guide: Quotation marks](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-028 | e.g. / i.e. need both periods | low | Write "e.g." and "i.e." with a period after each letter. | \1. | [UIC Editorial guide: e.g., i.e.](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-029 | Mail code format | low | Write the mail code as "MC" plus a space and the number ("MC 289"). | MC \1 | [UIC Editorial guide: Mail code](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-030 | No hyphen after -ly adverbs | low | Don't hyphenate -ly adverbs ("an easily remembered rule"). | \1 \2 | [UIC Editorial guide: Hyphen](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |
| content-031 | No "the" before Chicago Public Schools | low | "the Chicago Public Schools" → "Chicago Public Schools" | per match | [UIC Editorial guide: Chicago Public Schools](https://brand.uic.edu/messaging/editorial-and-style-guide/) | all |

## Reading Level Rules (`reading_level`)

Audience-dependent readability: Students grade 8, Faculty/Staff grade 10 (Flesch-Kincaid).

| ID | Rule | Severity | What it flags | Fix | Source | Applies to |
|---|---|---|---|---|---|---|
| reading-001 | Reading level above audience target | medium | The overall reading level is higher than recommended for this audience. | Use shorter sentences and simpler words | [Team-defined (SPEC): Students grade 8, Faculty/Staff grade 10](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| reading-002 | Hard-to-read sentence | medium | This sentence is much harder to read than the audience target. | Use simpler words or split the sentence | [Team-defined (SPEC)](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| reading-003 | Long sentence | medium | Long sentences are harder to follow. UIC voice favors short, punchy sentences. | Split into two or more sentences | [UIC Voice and tone (short, punchy sentences); limits (students 20, faculty/staff 25 words) are team-defined](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| reading-004 | Long paragraph | low | Long paragraphs are hard to scan. | Break into shorter paragraphs or a bulleted list | [Team-defined (SPEC)](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| reading-005 | Complex word with a plain alternative | low | "utilize" → "use"; "utilizes" → "uses"; "utilization" → "use"; "commence" → "start"; "facilitate" → "help"; "subsequently" → "later"; "endeavor" → "try"; "sufficient" → "enough"; +9 more | per match | [UIC Voice and tone ("no fluff"); word list is team-defined](https://brand.uic.edu/messaging/voice-and-tone/) | all |

## Audience Tone Rules (`audience_tone`)

UIC voice and tone plus the Inclusive Language Guide (gender, race, immigration, socioeconomic framing).

| ID | Rule | Severity | What it flags | Fix | Source | Applies to |
|---|---|---|---|---|---|---|
| tone-001 | Overly casual language | medium | "gonna"; "wanna"; "gotta"; "lol"; "omg"; "btw"; "thx"; "kinda"; +3 more | Use the full, standard wording | [UIC Social media guidelines ("conversational yet professional"); word list is team-defined](https://brand.uic.edu/resources/social-media-guidelines/) | faculty, staff |
| tone-002 | Gendered language | medium | "ladies and gentlemen" → "everyone"; "men and women" → "people / everyone"; "hey guys" → "Hi everyone"; "hi guys" → "Hi everyone"; "hello guys" → "Hello everyone"; "you guys" → "you all"; "chairman" → "chairperson"; "chairwoman" → "chairperson"; +8 more | per match | [UIC Inclusive Language Guide: Gender and sexual identity](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-003 | Academic or legal jargon | low | "matriculate" → "enroll"; "matriculation" → "enrollment"; "pursuant to" → "under"; "heretofore" → "until now"; "aforementioned" → "this"; "herein" → "here"; "henceforth" → "from now on"; "in accordance with" → "following"; +1 more | per match | [Team-defined (SPEC)](https://brand.uic.edu/messaging/voice-and-tone/) | students |
| tone-004 | Negative or threatening framing | low | "failure to"; "will result in"; "under no circumstances"; "strictly prohibited"; "will not be tolerated"; "no exceptions" | Reframe positively (e.g. "Submit by Friday to keep your spot") | [UIC Inclusive Language Guide: Asset-based framing; Voice and tone (Welcoming)](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-005 | Bureaucratic passive phrasing | low | "it is requested that" → "please"; "it has been decided that" → "we decided that"; "it should be noted that" → "note that"; "it is recommended that" → "we recommend that"; "please be advised that" → "(remove this phrase)"; "please be informed that" → "(remove this phrase)" | per match | [UIC Voice and tone (confident, direct, no filler)](https://brand.uic.edu/messaging/voice-and-tone/) | all |
| tone-006 | Exclamation points used rarely | low | Exclamation points are used rarely, if at all. | Replace with a period | [UIC Editorial guide: Exclamation point](https://brand.uic.edu/messaging/editorial-and-style-guide/) | email, website |
| tone-007 | Race and ethnicity terms | medium | "minorities" → "(name the specific groups) / historically overlooked"; "minority students" → "historically overlooked students (or name the groups)"; "minority groups" → "historically overlooked groups (or name the groups)"; "caucasian" → "white"; "mixed-race" → "multiracial / biracial"; "mixed race" → "multiracial / biracial"; "BIPOC" → "people of color (or be specific)"; "African-American" → "African American"; +4 more | per match | [UIC Inclusive Language Guide: Race and ethnicity](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-008 | Immigration terms | high | "illegal immigrant" → "immigrant lacking permanent legal status"; "illegal immigrants" → "immigrants lacking permanent legal status"; "illegal alien" → "immigrant lacking permanent legal status"; "illegal aliens" → "immigrants lacking permanent legal status"; "illegals" → "immigrants lacking permanent legal status" | per match | [UIC Inclusive Language Guide: Immigration](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-009 | Socioeconomic and deficit framing | low | "disadvantaged" → "under-resourced / underserved"; "underprivileged" → "people with low incomes"; "impoverished" → "people with low incomes"; "the homeless" → "people experiencing homelessness"; "homeless people" → "people experiencing homelessness"; "achievement gap" → "opportunity gap" | per match | [UIC Inclusive Language Guide: Socioeconomic status](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-010 | Avoid "empower" | low | "empower"; "empowers"; "empowered"; "empowering"; "empowerment" | Name the specific tools or resources | [UIC Inclusive Language Guide: Empower](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-011 | You-centered invitations | low | "join us for" → "You're invited to"; "join us at" → "You're invited to" | per match | [UIC Inclusive Language Guide: You-centered language](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |
| tone-012 | Gender-neutral alumni terms | low | Use the gender-neutral "alum" (singular) and "alums" (plural). Formal names such as University of Illinois Alumni Association are unchanged. | computed per match | [UIC Inclusive Language Guide: Gender (alum/alums); applied over the Editorial guide's alumnus/alumna by team decision](https://brand.uic.edu/messaging/inclusive-language-guide/) | all |

## UIC guidelines not implemented as rules

These need judgment or context that pattern matching can't supply. The RAG + LLM rewrite
(Workstreams 1 and 3) should cover them using the guideline text.

| Guideline | Why it isn't a rule |
|---|---|
| Titles: capitalize before a name, lowercase after ("Chancellor Marie Lynn Miranda" vs. "Mary Smith, dean,") | Needs to know which words are names and titles |
| Gov./Sen./Rep. before names; Dr. only for medical/dental degrees | Needs name detection |
| Department names: capitalize formal names, lowercase later references | Needs to know first vs. later reference to the same department |
| Class-year format (John Jones '87, MS '89) and alumni terms | Rare in this tool's content; risky to auto-detect |
| Possessives, colon capitalization, semicolons, hyphenated compound modifiers | Grammar that needs parsing |
| Faculty/staff verb agreement ("faculty take" vs. "the faculty takes") | Grammar that needs parsing |
| Academic/fiscal year format (2025-26; FY 2026) | Too many valid forms to flag reliably |
| Numbers: ordinals first through ninth spelled out | Partly covered (content-005, content-023); full ordinal check is noisy |
| Inclusive language: don't mention race, disability, immigration status, religion or sexual orientation unless relevant and approved | Needs judgment about relevance |
| Identity-first vs. person-first language; use the person's own terms (Latinx/Latino, Deaf/deaf, tribe names) | Depends on the person's preference |
| "Pacific Islander" is not "Asian"; capitalize Black and Indigenous; lowercase white | Capitalization rules: possible future rule, but high false-positive risk (e.g. "white paper") |
| Religion: avoid "extremist", "militant", "cult", "sect" | Common non-religious uses ("cult classic") cause false positives |
| Voice and tone: community-centered, resilient, innovative, welcoming, purposeful, bold; "Make It Known" | Qualitative; the LLM prompt should use these |
| Don't use the brand narrative or "Make It Known" verbatim as a tagline in external copy | Needs context about the piece |
| Brand strategy: frame outcomes around achievement, not debt ("what you will achieve," not "what you owe") | Qualitative |
| Social media: alt text on every photo, captions on video, approved logos and templates | Images and video are out of scope for Phase 1 (text only) |

## Conflicts between UIC pages (resolved 2026-10-08)

Team decision: apply the stricter guideline on every channel and for every audience.

| Topic | Conflict | Decision | Rule |
|---|---|---|---|
| Alumni terms | The Editorial guide allows alumnus/alumna/alumni/alumnae; the Inclusive Language Guide prefers "alum/alums" | Flag gendered terms and suggest alum/alums; formal names (Alumni Association, Alumni Weekend) are left alone | tone-012 |
| First reference to UIC | The Name and boilerplate page says to use the full name wherever possible; the Editorial guide allows "UIC" first for internal audiences | Require the full name first on all channels and audiences | brand-006 |
| Em dashes | The Editorial guide recommends spaced em dashes but also says to avoid them in documents sent or converted electronically | Flag every em dash (all our channels are electronic); suggest a comma, colon or parentheses, or a spaced dash | content-024 |

## Team-defined limits (set 2026-10-08)

| Limit | Value | Rule |
|---|---|---|
| Social media post length | 500 characters | content-011 |
| Email length | 200 words | content-012 |
| Sentence length | Students 20 words; faculty and staff 25 words | reading-003 (and reading-002 skips sentences over these limits) |
