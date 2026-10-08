# UIC Editorial Assistant - Master Task Checklist

**Project**: UIC Editorial Assistant - AI Hackathon  
**Last Updated**: 2026-10-08 (WS4 + docs pass)

---

## ✅ How to Use This Checklist

- Check off tasks as you complete them using - [x]
- Tasks are organized by workstream and integration phases
- Dependencies are noted - complete prerequisite tasks first
- Update this file and commit to Git regularly so team stays in sync

---

## 📋 Pre-Development (All Teams)

### API Contracts & Mocks
- [x] **Task I.1**: Define shared API contracts in /docs/API_CONTRACT.md _(partial: WS1 section + frontend types in frontend/src/types/api.ts; WS2 shapes adapted by ws2Adapter.ts)_
- [x] **Task I.2**: Create mock data files in /tests/mocks/ for each service
- [ ] Review and approve API contracts (all team members sign off)

---

## 🔵 Workstream 1: RAG & Knowledge Infrastructure (Team Member 1)

### AWS Setup
- [x] **Task 1.1**: Configure AWS CLI and verify credentials
- [x] **Task 1.1**: Create IAM roles with required policies
- [x] **Task 1.1**: Set up Parameter Store namespace /uic-editorial/
- [x] **Task 1.1**: Create CloudWatch log group

### Guideline Processing
- [x] **Task 1.2**: Create scripts/scrape_guidelines.py
- [x] **Task 1.2**: Scrape all 4 UIC brand guideline URLs
- [x] **Task 1.2**: Convert to markdown and chunk content
- [x] **Task 1.2**: Create guidelines_manifest.json

### S3 Storage
- [x] **Task 1.3**: Create S3 bucket with versioning
- [x] **Task 1.3**: Upload guidelines to S3
- [x] **Task 1.3**: Store bucket name in Parameter Store

### Knowledge Base
- [x] **Task 1.4**: Create Knowledge Base in Bedrock console
- [x] **Task 1.4**: Configure data source from S3
- [x] **Task 1.4**: Sync data and verify ingestion
- [x] **Task 1.4**: Store Knowledge Base ID in Parameter Store
- [x] **Task 1.4**: Test retrieval with sample query

### RAG Service
- [x] **Task 1.5**: Create /backend/services/rag_service.py
- [x] **Task 1.5**: Implement RAGService class with retrieval methods
- [x] **Task 1.5**: Add error handling and retry logic
- [x] **Task 1.5**: Add CloudWatch logging
- [x] **Task 1.5**: Write unit tests

### API & Documentation
- [x] **Task 1.6**: Create /backend/api/rag_routes.py
- [x] **Task 1.6**: Implement test endpoints
- [x] **Task 1.6**: Add OpenAPI documentation
- [x] **Task 1.7**: Create /docs/RAG_SETUP.md
- [x] **Task 1.7**: Create /docs/RAG_API.md
- [x] **Task 1.7**: Provide mock data for other teams

---

## 🟢 Workstream 2: Rule Engine & Scoring (Team Member 2)

### Rule Schema
- [ ] **Task 2.1**: Define JSON schema for rules
- [ ] **Task 2.1**: Create 5 ruleset JSON files in /rulesets/
- [ ] **Task 2.1**: Add 3-5 starter rules per ruleset

### Core Engine
- [ ] **Task 2.2**: Create /backend/services/rule_engine.py
- [ ] **Task 2.2**: Implement RuleEngine class
- [ ] **Task 2.2**: Support regex, keyword, and function patterns
- [ ] **Task 2.2**: Implement issue detection with context
- [ ] **Task 2.2**: Write unit tests

### Reading Level
- [ ] **Task 2.3**: Implement Flesch-Kincaid calculator
- [ ] **Task 2.3**: Add syllable counting logic
- [ ] **Task 2.3**: Set audience-specific thresholds
- [ ] **Task 2.3**: Test with known grade-level texts

### Ruleset Implementation
- [ ] **Task 2.4**: Populate rand.json with 10-15 rules
- [ ] **Task 2.5**: Populate ccessibility.json with 8-10 rules
- [ ] **Task 2.6**: Populate content.json with 8-10 rules

### Scoring Service
- [ ] **Task 2.7**: Create /backend/services/scoring_service.py
- [ ] **Task 2.7**: Implement score calculation logic
- [ ] **Task 2.7**: Implement status classification
- [ ] **Task 2.7**: Test scoring with various issue combinations

### API & Documentation
- [ ] **Task 2.8**: Create /backend/api/rules_routes.py
- [ ] **Task 2.8**: Implement /api/rules and /api/rules/check endpoints
- [ ] **Task 2.8**: Add OpenAPI documentation
- [ ] **Task 2.9**: Create /docs/RULE_ENGINE.md
- [ ] **Task 2.9**: Create /docs/RULESETS.md
- [ ] **Task 2.9**: Provide mock data for other teams

---

## 🟣 Workstream 3: LLM Integration & Rewrite Logic (Team Member 3)

### Bedrock Setup
- [ ] **Task 3.1**: Configure boto3 for bedrock-runtime
- [ ] **Task 3.1**: Request model access (Haiku & Sonnet)
- [ ] **Task 3.1**: Store model IDs in Parameter Store
- [ ] **Task 3.1**: Test connection with simple prompts

### Prompt Engineering
- [ ] **Task 3.2**: Create /backend/prompts/ directory
- [ ] **Task 3.2**: Create system_prompt.txt
- [ ] **Task 3.2**: Create 
ewrite_prompt_template.txt
- [ ] **Task 3.2**: Create detection_prompt_template.txt
- [ ] **Task 3.2**: Test prompts for proper output format

### LLM Service
- [ ] **Task 3.3**: Create /backend/services/llm_service.py
- [ ] **Task 3.3**: Implement LLMService class
- [ ] **Task 3.3**: Add retry logic with exponential backoff
- [ ] **Task 3.3**: Add error handling for all failure modes
- [ ] **Task 3.3**: Add CloudWatch logging

### Change Tagging
- [ ] **Task 3.4**: Implement change tag parsing
- [ ] **Task 3.4**: Create Change object structure
- [ ] **Task 3.4**: Generate HTML with proper styling
- [ ] **Task 3.4**: Add fallback for malformed tags

### Model Selection
- [ ] **Task 3.5**: Implement adaptive model selection logic
- [ ] **Task 3.5**: Calculate complexity scores
- [ ] **Task 3.5**: Log model selection decisions
- [ ] **Task 3.5**: Track cost savings

### Diff & Refinement
- [ ] **Task 3.6**: Implement text diffing with difflib
- [ ] **Task 3.6**: Generate change annotations from diffs
- [ ] **Task 3.7**: Implement refinement handling
- [ ] **Task 3.7**: Support common refinement patterns

### API & Documentation
- [ ] **Task 3.8**: Create /backend/api/llm_routes.py
- [ ] **Task 3.8**: Implement rewrite/refine/explain endpoints
- [ ] **Task 3.8**: Add OpenAPI documentation
- [ ] **Task 3.9**: Create /docs/LLM_SERVICE.md
- [ ] **Task 3.9**: Create /docs/PROMPTS.md
- [ ] **Task 3.9**: Provide mock data for other teams

---

## 🔴 Workstream 4: Frontend & User Experience (Team Member 4)

### React Setup
- [x] **Task 4.1**: Initialize React app with TypeScript
- [x] **Task 4.1**: Install dependencies (axios, tailwind, etc.)
- [x] **Task 4.1**: Configure Tailwind CSS
- [x] **Task 4.1**: Set up project structure
- [x] **Task 4.1**: Create environment variables

### Type Definitions
- [x] **Task 4.2**: Create /src/types/api.ts with interfaces
- [x] **Task 4.2**: Create /src/services/mockData.ts
- [x] **Task 4.2**: Create /src/services/api.ts client
- [x] **Task 4.2**: Verify TypeScript compiles

### State Management
- [x] **Task 4.3**: Create TextContext
- [x] **Task 4.3**: Create RulesetContext
- [x] **Task 4.3**: Create UIContext
- [x] **Task 4.3**: Wrap app in providers
- [x] **Task 4.3**: Add localStorage persistence

### Core Components
- [x] **Task 4.4**: Create TextInput component
- [x] **Task 4.4**: Add word count and character limit
- [x] **Task 4.5**: Create RulesetPanel component
- [x] **Task 4.5**: Add audience/channel selectors
- [x] **Task 4.5**: Add ruleset checkboxes
- [x] **Task 4.5**: Add Analyze button

### Comparison & Display
- [x] **Task 4.6**: Create ComparisonView component
- [x] **Task 4.6**: Implement side-by-side layout
- [x] **Task 4.6**: Add highlight rendering with colors
- [x] **Task 4.6**: Implement progressive reveal toggle
- [x] **Task 4.7**: Create ComplianceDisplay component
- [x] **Task 4.7**: Add status badge and score cards
- [x] **Task 4.7**: Add issues list with grouping

### Chat & Export
- [x] **Task 4.8**: Create ChatInterface component
- [x] **Task 4.8**: Add message history and input
- [x] **Task 4.8**: Add suggested prompts
- [x] **Task 4.9**: Create ExportButton component
- [x] **Task 4.9**: Implement copy to clipboard
- [x] **Task 4.9**: Implement PDF generation

### Layout & Integration
- [x] **Task 4.10**: Create main application layout
- [x] **Task 4.10**: Implement responsive breakpoints
- [x] **Task 4.10**: Add loading states and error boundaries
- [x] **Task 4.11**: Connect to real backend APIs _(client + ws2Adapter ready; live via `VITE_USE_MOCKS=false`; RAG API already live)_
- [x] **Task 4.11**: Add error handling for API failures
- [x] **Task 4.11**: Test all user flows end-to-end _(on mocks + live RAG; re-run against live /api/analyze after I.5)_

### Polish
- [x] **Task 4.12**: Apply UIC brand colors
- [x] **Task 4.12**: Add smooth transitions
- [x] **Task 4.12**: Ensure WCAG AA compliance
- [x] **Task 4.12**: Test keyboard navigation
- [ ] **Task 4.12**: Cross-browser testing _(Chrome verified; Safari/Firefox/Edge not yet)_
- [x] **Task 4.13**: Create /docs/FRONTEND.md
- [x] **Task 4.13**: Create /docs/USER_GUIDE.md

---

## 🔗 Integration & Deployment (All Teams)

### Backend Integration
- [x] **Task I.3**: Create /backend/api/main.py FastAPI app
- [x] **Task I.3**: Create /backend/services/orchestrator.py
- [ ] **Task I.3**: Integrate RAG + Rules + LLM services _(in progress: orchestrator + interim Bedrock rewrite_service.py)_
- [x] **Task I.3**: Implement /api/analyze endpoint _(plus /api/llm/refine; deploying)_
- [ ] **Task I.3**: Test end-to-end backend flow _(in progress)_

### Full Stack Integration
- [ ] **Task I.4**: Connect frontend to live backend
- [ ] **Task I.4**: Replace mock API calls with real axios calls
- [ ] **Task I.4**: Test all user flows
- [ ] **Task I.4**: Handle loading and error states

### AWS Deployment
- [ ] **Task I.5**: Create Lambda deployment package _(RAG API part done via scripts/aws/deploy_rag_api.py; redeploy with main.py after I.3)_
- [ ] **Task I.5**: Create Lambda function in AWS _(RAG API part done via scripts/aws/deploy_rag_api.py; redeploy with main.py after I.3)_
- [ ] **Task I.5**: Create API Gateway HTTP API _(RAG API part done via scripts/aws/deploy_rag_api.py; redeploy with main.py after I.3)_
- [ ] **Task I.5**: Test Lambda via API Gateway _(RAG API part done via scripts/aws/deploy_rag_api.py; redeploy with main.py after I.3)_
- [x] **Task I.6**: Connect GitHub to AWS Amplify _(manual zip deploy instead of GitHub: scripts/aws/deploy_frontend.sh)_
- [x] **Task I.6**: Configure build settings
- [x] **Task I.6**: Set environment variables
- [x] **Task I.6**: Deploy and test production URL _(https://main.d3ax0n8zonbnh0.amplifyapp.com)_

### Testing & Validation
- [x] **Task I.7**: Select 10-15 examples from Team8Dataset.xlsx _(24 synthetic drafts in data/demo/)_
- [x] **Task I.7**: Run analysis on each example _(rule engine only)_
- [x] **Task I.7**: Compare results to dataset expectations
- [x] **Task I.7**: Document validation results _(24 drafts validated, see data/demo/VALIDATION.md (75% status agreement))_
- [ ] **Task I.7**: Fix major discrepancies

### Presentation
- [x] **Task I.8**: Select demo scenario from dataset _(Career Fair email, first in "Try a sample ▾"; triggers all 5 rulesets)_
- [ ] **Task I.8**: Create presentation slides
- [ ] **Task I.8**: Practice demo flow (2-3 times)
- [ ] **Task I.8**: Record backup demo video
- [ ] **Task I.8**: Assign speaking roles

### Documentation
- [x] **Task I.9**: Update /README.md with overview
- [ ] **Task I.9**: Complete all /docs/ files
- [ ] **Task I.9**: Add inline code comments
- [ ] **Task I.9**: Create architecture diagrams
- [ ] **Task I.10**: Create Phase 2 GitHub Issues
- [ ] **Task I.10**: Organize issues with labels and priorities

---

## 📅 Timeline Checkpoints

### End of Day 1
- [ ] All API contracts defined and approved
- [ ] Mock data created for all services
- [ ] Each workstream has foundational setup complete
- [ ] All teams working with mocks successfully

### End of Day 2
- [x] RAG service retrieving guidelines from Knowledge Base
- [x] Rule engine detecting issues and calculating scores
- [ ] LLM service rewriting text with tagged changes
- [x] Frontend showing all components with mock data

### End of Day 3
- [ ] Backend fully integrated (RAG + Rules + LLM)
- [ ] Frontend connected to live backend
- [ ] Application deployed to AWS (Lambda + Amplify)
- [x] At least 5 dataset examples validated

### End of Day 4
- [x] All 10-15 dataset examples validated _(24)_
- [ ] Presentation materials complete
- [ ] Demo practiced and polished
- [ ] Backup video recorded

### Day 5 - Presentation Day
- [ ] Final rehearsal completed
- [ ] Presentation delivered successfully
- [ ] Phase 2 backlog created

---

## 🎯 Success Metrics

- [ ] **Functional**: All 12 functional requirements met
- [ ] **Technical**: All 10 technical requirements met
- [ ] **Performance**: Analysis completes in <10 seconds
- [ ] **Accuracy**: 80%+ dataset validation pass rate
- [ ] **Demo**: Smooth 8-10 minute presentation
- [ ] **Documentation**: Complete and usable by new developers

---

## 📝 Notes & Blockers

_Use this space to note blockers, decisions, or important updates:_

- **WS1 (2026-10-08):** Two SPEC 1 guideline URLs 404 (`brand-attributes-and-tone`, `key-audience-and-messaging`). Using the renamed live pages `/messaging/voice-and-tone/` and `/messaging/brand-strategy/`. See docs/API_CONTRACT.md.
- **WS1:** None of the 4 SPEC pages cover accessibility; the `accessibility` ruleset currently searches the editorial guide. Option: add https://brand.uic.edu/resources/ada-compliance/ as a 5th source.
- **WS1 AWS live (2026-10-08, workshop account 605134453119, us-east-1):** Knowledge Base `HFJFKHPXI0` (S3 Vectors, Titan V2), data source `VYU6OF5MX8`, 125/125 chunks ingested, 0 failed. Category filter verified. IDs in Parameter Store `/uic-editorial/*`. RAG API auto-uses Bedrock when creds are present, falls back to local search otherwise. RAG API deployed to Lambda + HTTP API: https://rtjsllveri.execute-api.us-east-1.amazonaws.com (`/docs`; URL in `/uic-editorial/rag_api_url`). Tear down: `scripts/aws/teardown.py --yes`.
- **Task I.1 / I.2:** WS1 section of docs/API_CONTRACT.md and RAG mocks in tests/mocks/ are ready for review by WS2–4.
- **WS4 (2026-10-08):** Frontend done (React 19 + TS + Vite + Tailwind v4, ~170 vitest tests, live scores mirror WS2 scoring with a parity test on all 24 demo drafts). Runs on mocks by default; set `VITE_USE_MOCKS=false` + `VITE_API_BASE_URL` once I.5 is live. See docs/FRONTEND.md, docs/USER_GUIDE.md.
- **Decision needed: compliance status thresholds.** SPEC thresholds reproduce the dataset's status on 79% of 300 rows. A data-fitted rule (average of brand + accessibility; Approved if avg ≥ 85 and ≤ 2 issues; Major if avg < 70 or > 5 issues; else Minor) gives 90%. Frontend `lib/scoring.ts` and WS2 `scoring_service.py` must change together (parity test).
- **WS2 rule-engine gaps:** visual/structural issues (logo, color contrast, fonts, captions, headings) have no rules, so only 21/85 planted dataset issues are detected (21/28 among types with a rule). See data/demo/VALIDATION.md.
- **Blocker – Task I.6:** Amplify frontend deploy not started; frontend is local only.
- **Blocker – AWS workshop credentials expire.** Refresh before deploys and the demo; RAG falls back to local search without creds, rewrite falls back to rules-only.
- **UIC logo trademark:** official marks in frontend/public/brand/ need confirmation from UIC SMC (smcs@uic.edu) before any public deploy.

---

**Team Members:**
- Workstream 1 (RAG): Aagam Bothara
- Workstream 2 (Rules): Juhi Anand
- Workstream 3 (LLM): Tomas M.
- Workstream 4 (Frontend): ________________
