# UIC Editorial Assistant - Master Task Checklist

**Project**: UIC Editorial Assistant - AI Hackathon  
**Last Updated**: 2026-10-08

---

## ✅ How to Use This Checklist

- Check off tasks as you complete them using - [x]
- Tasks are organized by workstream and integration phases
- Dependencies are noted - complete prerequisite tasks first
- Update this file and commit to Git regularly so team stays in sync

---

## 📋 Pre-Development (All Teams)

### API Contracts & Mocks
- [ ] **Task I.1**: Define shared API contracts in /docs/API_CONTRACT.md
- [ ] **Task I.2**: Create mock data files in /tests/mocks/ for each service
- [ ] Review and approve API contracts (all team members sign off)

---

## 🔵 Workstream 1: RAG & Knowledge Infrastructure (Team Member 1)

### AWS Setup
- [ ] **Task 1.1**: Configure AWS CLI and verify credentials
- [ ] **Task 1.1**: Create IAM roles with required policies
- [ ] **Task 1.1**: Set up Parameter Store namespace /uic-editorial/
- [ ] **Task 1.1**: Create CloudWatch log group

### Guideline Processing
- [ ] **Task 1.2**: Create scripts/scrape_guidelines.py
- [ ] **Task 1.2**: Scrape all 4 UIC brand guideline URLs
- [ ] **Task 1.2**: Convert to markdown and chunk content
- [ ] **Task 1.2**: Create guidelines_manifest.json

### S3 Storage
- [ ] **Task 1.3**: Create S3 bucket with versioning
- [ ] **Task 1.3**: Upload guidelines to S3
- [ ] **Task 1.3**: Store bucket name in Parameter Store

### Knowledge Base
- [ ] **Task 1.4**: Create Knowledge Base in Bedrock console
- [ ] **Task 1.4**: Configure data source from S3
- [ ] **Task 1.4**: Sync data and verify ingestion
- [ ] **Task 1.4**: Store Knowledge Base ID in Parameter Store
- [ ] **Task 1.4**: Test retrieval with sample query

### RAG Service
- [ ] **Task 1.5**: Create /backend/services/rag_service.py
- [ ] **Task 1.5**: Implement RAGService class with retrieval methods
- [ ] **Task 1.5**: Add error handling and retry logic
- [ ] **Task 1.5**: Add CloudWatch logging
- [ ] **Task 1.5**: Write unit tests

### API & Documentation
- [ ] **Task 1.6**: Create /backend/api/rag_routes.py
- [ ] **Task 1.6**: Implement test endpoints
- [ ] **Task 1.6**: Add OpenAPI documentation
- [ ] **Task 1.7**: Create /docs/RAG_SETUP.md
- [ ] **Task 1.7**: Create /docs/RAG_API.md
- [ ] **Task 1.7**: Provide mock data for other teams

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
- [x] **Task 3.1**: Configure boto3 for bedrock-runtime
- [x] **Task 3.1**: Request model access (Haiku & Sonnet)
- [x] **Task 3.1**: Store model IDs in Parameter Store
- [x] **Task 3.1**: Test connection with simple prompts

### Prompt Engineering
- [x] **Task 3.2**: Create /backend/prompts/ directory
- [x] **Task 3.2**: Create system_prompt.txt
- [x] **Task 3.2**: Create rewrite_prompt_template.txt
- [x] **Task 3.2**: Create detection_prompt_template.txt
- [x] **Task 3.2**: Test prompts for proper output format

### LLM Service
- [x] **Task 3.3**: Create /backend/services/llm_service.py
- [x] **Task 3.3**: Implement LLMService class
- [x] **Task 3.3**: Add retry logic with exponential backoff
- [x] **Task 3.3**: Add error handling for all failure modes
- [x] **Task 3.3**: Add CloudWatch logging

### Change Tagging
- [x] **Task 3.4**: Implement change tag parsing
- [x] **Task 3.4**: Create Change object structure
- [x] **Task 3.4**: Generate HTML with proper styling
- [x] **Task 3.4**: Add fallback for malformed tags

### Model Selection
- [x] **Task 3.5**: Implement adaptive model selection logic
- [x] **Task 3.5**: Calculate complexity scores
- [x] **Task 3.5**: Log model selection decisions
- [x] **Task 3.5**: Track cost savings

### Diff & Refinement
- [x] **Task 3.6**: Implement text diffing with difflib
- [x] **Task 3.6**: Generate change annotations from diffs
- [x] **Task 3.7**: Implement refinement handling
- [x] **Task 3.7**: Support common refinement patterns

### API & Documentation
- [x] **Task 3.8**: Create /backend/api/llm_routes.py
- [x] **Task 3.8**: Implement rewrite/refine/explain endpoints
- [x] **Task 3.8**: Add OpenAPI documentation
- [ ] **Task 3.9**: Create /docs/LLM_SERVICE.md
- [ ] **Task 3.9**: Create /docs/PROMPTS.md
- [ ] **Task 3.9**: Provide mock data for other teams

---

## 🔴 Workstream 4: Frontend & User Experience (Team Member 4)

### React Setup
- [ ] **Task 4.1**: Initialize React app with TypeScript
- [ ] **Task 4.1**: Install dependencies (axios, tailwind, etc.)
- [ ] **Task 4.1**: Configure Tailwind CSS
- [ ] **Task 4.1**: Set up project structure
- [ ] **Task 4.1**: Create environment variables

### Type Definitions
- [ ] **Task 4.2**: Create /src/types/api.ts with interfaces
- [ ] **Task 4.2**: Create /src/services/mockData.ts
- [ ] **Task 4.2**: Create /src/services/api.ts client
- [ ] **Task 4.2**: Verify TypeScript compiles

### State Management
- [ ] **Task 4.3**: Create TextContext
- [ ] **Task 4.3**: Create RulesetContext
- [ ] **Task 4.3**: Create UIContext
- [ ] **Task 4.3**: Wrap app in providers
- [ ] **Task 4.3**: Add localStorage persistence

### Core Components
- [ ] **Task 4.4**: Create TextInput component
- [ ] **Task 4.4**: Add word count and character limit
- [ ] **Task 4.5**: Create RulesetPanel component
- [ ] **Task 4.5**: Add audience/channel selectors
- [ ] **Task 4.5**: Add ruleset checkboxes
- [ ] **Task 4.5**: Add Analyze button

### Comparison & Display
- [ ] **Task 4.6**: Create ComparisonView component
- [ ] **Task 4.6**: Implement side-by-side layout
- [ ] **Task 4.6**: Add highlight rendering with colors
- [ ] **Task 4.6**: Implement progressive reveal toggle
- [ ] **Task 4.7**: Create ComplianceDisplay component
- [ ] **Task 4.7**: Add status badge and score cards
- [ ] **Task 4.7**: Add issues list with grouping

### Chat & Export
- [ ] **Task 4.8**: Create ChatInterface component
- [ ] **Task 4.8**: Add message history and input
- [ ] **Task 4.8**: Add suggested prompts
- [ ] **Task 4.9**: Create ExportButton component
- [ ] **Task 4.9**: Implement copy to clipboard
- [ ] **Task 4.9**: Implement PDF generation

### Layout & Integration
- [ ] **Task 4.10**: Create main application layout
- [ ] **Task 4.10**: Implement responsive breakpoints
- [ ] **Task 4.10**: Add loading states and error boundaries
- [ ] **Task 4.11**: Connect to real backend APIs
- [ ] **Task 4.11**: Add error handling for API failures
- [ ] **Task 4.11**: Test all user flows end-to-end

### Polish
- [ ] **Task 4.12**: Apply UIC brand colors
- [ ] **Task 4.12**: Add smooth transitions
- [ ] **Task 4.12**: Ensure WCAG AA compliance
- [ ] **Task 4.12**: Test keyboard navigation
- [ ] **Task 4.12**: Cross-browser testing
- [ ] **Task 4.13**: Create /docs/FRONTEND.md
- [ ] **Task 4.13**: Create /docs/USER_GUIDE.md

---

## 🔗 Integration & Deployment (All Teams)

### Backend Integration
- [ ] **Task I.3**: Create /backend/api/main.py FastAPI app
- [ ] **Task I.3**: Create /backend/services/orchestrator.py
- [ ] **Task I.3**: Integrate RAG + Rules + LLM services
- [ ] **Task I.3**: Implement /api/analyze endpoint
- [ ] **Task I.3**: Test end-to-end backend flow

### Full Stack Integration
- [ ] **Task I.4**: Connect frontend to live backend
- [ ] **Task I.4**: Replace mock API calls with real axios calls
- [ ] **Task I.4**: Test all user flows
- [ ] **Task I.4**: Handle loading and error states

### AWS Deployment
- [ ] **Task I.5**: Create Lambda deployment package
- [ ] **Task I.5**: Create Lambda function in AWS
- [ ] **Task I.5**: Create API Gateway HTTP API
- [ ] **Task I.5**: Test Lambda via API Gateway
- [ ] **Task I.6**: Connect GitHub to AWS Amplify
- [ ] **Task I.6**: Configure build settings
- [ ] **Task I.6**: Set environment variables
- [ ] **Task I.6**: Deploy and test production URL

### Testing & Validation
- [ ] **Task I.7**: Select 10-15 examples from Team8Dataset.xlsx
- [ ] **Task I.7**: Run analysis on each example
- [ ] **Task I.7**: Compare results to dataset expectations
- [ ] **Task I.7**: Document validation results
- [ ] **Task I.7**: Fix major discrepancies

### Presentation
- [ ] **Task I.8**: Select demo scenario from dataset
- [ ] **Task I.8**: Create presentation slides
- [ ] **Task I.8**: Practice demo flow (2-3 times)
- [ ] **Task I.8**: Record backup demo video
- [ ] **Task I.8**: Assign speaking roles

### Documentation
- [ ] **Task I.9**: Update /README.md with overview
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
- [ ] RAG service retrieving guidelines from Knowledge Base
- [ ] Rule engine detecting issues and calculating scores
- [ ] LLM service rewriting text with tagged changes
- [ ] Frontend showing all components with mock data

### End of Day 3
- [ ] Backend fully integrated (RAG + Rules + LLM)
- [ ] Frontend connected to live backend
- [ ] Application deployed to AWS (Lambda + Amplify)
- [ ] At least 5 dataset examples validated

### End of Day 4
- [ ] All 10-15 dataset examples validated
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

- 
- 
- 

---

**Team Members:**
- Workstream 1 (RAG): ________________
- Workstream 2 (Rules): ________________
- Workstream 3 (LLM): ________________
- Workstream 4 (Frontend): ________________
