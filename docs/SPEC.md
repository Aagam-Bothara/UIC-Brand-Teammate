# UIC Editorial Assistant - Complete Specification

**Project**: UIC Editorial Assistant  
**Team**: Team 8 - UIC Enterprise AI Hackathon  
**Date**: October 8, 2026  
**Version**: 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Solution Overview](#solution-overview)
4. [Design Decisions Summary](#design-decisions-summary)
5. [System Architecture](#system-architecture)
6. [Requirements](#requirements)
7. [Technical Specifications](#technical-specifications)
8. [Team Structure](#team-structure)
9. [Timeline](#timeline)
10. [Success Criteria](#success-criteria)
11. [Phase 2 Roadmap](#phase-2-roadmap)

---

## Executive Summary

The UIC Editorial Assistant is an AI-powered web application that helps UIC faculty and staff create brand-compliant, accessible communications. The system combines deterministic rule checking with AI-powered text rewriting to ensure consistency with UIC brand guidelines, improve accessibility, and maintain content quality.

**Key Features:**
- Real-time analysis against UIC brand guidelines
- Progressive reveal of improvements across 5 ruleset categories
- Hybrid AI approach (deterministic rules + RAG-powered LLM)
- Audience-aware rewrites (Students, Faculty, Staff)
- Channel-specific validation (Email, Website, Social Media)
- Interactive explanations with links to UIC guidelines
- Comprehensive compliance scoring and reporting

**Technology Stack:**
- Frontend: React + TypeScript + Tailwind CSS
- Backend: FastAPI + AWS Lambda
- AI: AWS Bedrock (Claude Haiku & Sonnet)
- RAG: AWS Knowledge Bases for Bedrock
- Deployment: AWS Amplify + Lambda + API Gateway

---

## Problem Statement

Faculty and staff across UIC create communications independently, resulting in:
- **Inconsistent messaging** - Different departments use varying terminology and tone
- **Accessibility gaps** - Content often exceeds appropriate reading levels or lacks proper structure
- **Off-brand content** - Incorrect logo usage, missing taglines, wrong color schemes
- **Time-consuming reviews** - Manual editorial review takes ~32 minutes per communication vs. ~12 seconds with AI

### Target Users
- Faculty members creating course announcements
- Staff creating departmental communications
- Marketing coordinators drafting newsletters
- Administrators writing policy updates

---

## Solution Overview

A hybrid web application that:

1. **Ingests** user text with audience and channel selections
2. **Retrieves** relevant UIC brand guidelines via RAG
3. **Analyzes** text using JSON-configured deterministic rules
4. **Rewrites** text using Bedrock LLM with guidelines as context
5. **Tags** each change with applicable rulesets for progressive reveal
6. **Scores** compliance (brand + accessibility percentages)
7. **Presents** side-by-side comparison with toggleable highlights
8. **Allows** chat-based refinements and selective acceptance
9. **Exports** clean text or comprehensive PDF report

### Core Innovation

**Progressive Reveal**: Users enable/disable rulesets (Brand, Accessibility, Content, Reading Level, Audience Tone) and watch text improve incrementally. Each change is color-coded, allowing users to learn guidelines while using the tool.

**Hybrid Approach**: Combines deterministic rules (exact matching) with AI-powered rewrites (tone, style), balancing precision with flexibility.

---

## Design Decisions Summary

### Foundation (Round 1)
- **Architecture**: Hybrid web UI (structured controls + chat interface)
- **Content Types**: Text only for Phase 1
- **Audiences**: Students, Faculty, Staff (3 core segments)
- **Rules**: Hybrid (JSON config files + RAG for style/tone)
- **Output**: Progressive reveal with side-by-side comparison
- **Deployment**: AWS workshop account with Bedrock

### Ruleset Architecture (Round 2)
- **Granularity**: 5 primary rulesets (Brand, Accessibility, Content, Reading Level, Audience Tone)
- **Reading Level**: Audience-dependent (Students: Grade 8, Faculty/Staff: Grade 10)
- **Scoring**: Comprehensive (scores + status + detailed issues)
- **Chat**: Full flexibility (selection, refinement, explanations, questions)
- **RAG Scope**: All 4 UIC brand guideline pages
- **Channels**: Email, Website, Social Media (3 primary)

### Technical Architecture (Round 3)
- **Frontend**: React with TypeScript
- **Backend**: Hybrid (FastAPI + Lambda + Bedrock)
- **RAG**: AWS Knowledge Bases for Bedrock
- **Rules Storage**: JSON files per ruleset
- **Reveal Mechanics**: Layered edits (pre-generate, toggle visibility)
- **Highlights**: Toggleable view + sidebar annotations
- **Workflow**: Hybrid with smart defaults
- **Models**: Adaptive (Haiku for simple, Sonnet for complex)
- **Explanations**: Interactive with guideline links

### Data Flow & Edge Cases (Round 4)
- **Rule Order**: Parallel application with merged output
- **Conflicts**: Warn but allow unusual combinations
- **Acceptance**: Hybrid (ruleset-level + individual changes)
- **Export**: Report PDF + plain text copy
- **Errors**: Retry with exponential backoff
- **Limits**: 5,000 word practical maximum
- **Persistence**: Browser localStorage
- **Demo**: Progressive reveal showcase
- **Testing**: Comprehensive (manual + dataset + UAT)

### Deployment (Round 5)
- **AWS**: Amplify full-stack deployment
- **Config**: AWS Parameter Store
- **Git**: Feature branch workflow
- **Structure**: Simple monorepo
- **API**: RESTful design
- **State**: React Context API
- **Logging**: CloudWatch
- **Docs**: Comprehensive (README + API + user guide + architecture)
- **CI/CD**: Amplify auto-deploy
- **Backlog**: GitHub Issues for Phase 2

---

## System Architecture

### High-Level Components

\\\
USER INTERFACE (React + Amplify)
├── Text Input Component
├── Ruleset Panel Component  
├── Comparison View Component
├── Compliance Display Component
├── Chat Interface Component
└── Export Button Component
         ↓ HTTPS/REST
BACKEND ORCHESTRATOR (FastAPI + Lambda)
├── RAG Service → AWS Knowledge Base
├── Rule Engine → JSON Config Files
├── LLM Service → AWS Bedrock (Haiku + Sonnet)
└── Scoring Service
         ↓
AWS SERVICES
├── Knowledge Base (S3 + Vector Store)
├── Bedrock (Claude Models)
├── Parameter Store (Config)
└── CloudWatch (Logs + Metrics)
\\\

### Data Flow

1. User pastes text + selects audience/channel → POST /api/analyze
2. **Parallel execution**:
   - Rule Engine checks deterministic rules → issues list
   - RAG Service retrieves guidelines → relevant excerpts
3. LLM Service rewrites with issues + guidelines → tagged changes
4. Scoring Service calculates → brand score, accessibility score, status
5. Response → original, rewritten (HTML), issues, changes, scores
6. Frontend progressive reveal → toggle visibility by ruleset
7. User refinement via chat → re-analyze with constraints
8. Export → copy text or download PDF

---

## Requirements

### Functional Requirements (FR)

**FR-1**: Analyze text up to 5,000 words  
**FR-2**: Check against 5 rulesets (Brand, Accessibility, Content, Reading Level, Audience Tone)  
**FR-3**: Support 3 audiences with specific reading level thresholds  
**FR-4**: Support 3 channels with specific validation rules  
**FR-5**: Progressive reveal (toggle rulesets without re-generation)  
**FR-6**: Side-by-side comparison with color-coded highlights  
**FR-7**: Compliance scoring (brand + accessibility percentages, status classification)  
**FR-8**: Detailed issue reporting (severity, location, suggestions, links)  
**FR-9**: Interactive explanations (click changes for details)  
**FR-10**: Hybrid acceptance (ruleset-level + individual changes)  
**FR-11**: Chat interface (rule selection, refinements, explanations)  
**FR-12**: Export (copy clean text, download PDF report)

### Non-Functional Requirements (NFR)

**NFR-1 Performance**: Analysis <10 seconds for typical communications  
**NFR-2 Scalability**: Handle 10+ concurrent users  
**NFR-3 Reliability**: 3 retries with backoff, 99% uptime  
**NFR-4 Usability**: Intuitive interface, no training required  
**NFR-5 Accessibility**: WCAG 2.1 Level AA compliance  
**NFR-6 Extensibility**: Easy to add rulesets, audiences, channels via config  
**NFR-7 Security**: HTTPS, Parameter Store for secrets, no server-side persistence  
**NFR-8 Maintainability**: Clear code structure, comprehensive documentation

---

## Technical Specifications

### API Endpoints

**POST /api/analyze** - Main analysis endpoint  
**GET /api/rules** - Get available rulesets  
**GET /api/audiences** - Get audience definitions  
**POST /api/llm/refine** - Refine based on chat request  
**POST /api/export** - Generate PDF report

### Rule Schema

JSON structure for /rulesets/ files:
\\\json
{
  "ruleset_id": "brand",
  "ruleset_name": "Brand Compliance Rules",
  "enabled": true,
  "highlight_color": "#3B82F6",
  "rules": [
    {
      "rule_id": "brand-001",
      "name": "Official University Name",
      "severity": "high",
      "pattern_type": "regex",
      "pattern": "\\\\bUIC\\\\b(?! is|'s)",
      "suggestion": "University of Illinois Chicago",
      "guideline_url": "https://brand.uic.edu/...",
      "enabled": true
    }
  ]
}
\\\

### Scoring Algorithm

- Start at 100 points
- Deduct by severity: High (-10), Medium (-5), Low (-2)
- Calculate separately for brand and accessibility
- Status classification:
  - Approved: both scores ≥90 AND total_issues ≤2
  - Minor Revisions: scores 70-89 OR issues 3-5
  - Major Revisions: any score <70 OR issues >5

---

## Team Structure

### Workstream 1: RAG & Knowledge Infrastructure
**Owner**: Team Member 1  
**Tasks**: 1.1-1.7 (AWS setup, scraping, Knowledge Base, RAGService)  
**Interface**: \etrieve_guidelines(query, audience) -> List[Guideline]\

### Workstream 2: Rule Engine & Scoring
**Owner**: Team Member 2  
**Tasks**: 2.1-2.9 (Rule schema, JSON files, RuleEngine, scoring)  
**Interface**: \nalyze_text(text, rulesets, audience) -> AnalysisResult\

### Workstream 3: LLM Integration & Rewrite Logic
**Owner**: Team Member 3  
**Tasks**: 3.1-3.9 (Bedrock, prompts, LLMService, tagging)  
**Interface**: \ewrite_text(original, issues, guidelines, audience) -> RewriteResult\

### Workstream 4: Frontend & User Experience
**Owner**: Team Member 4  
**Tasks**: 4.1-4.13 (React app, components, state, integration)  
**Interface**: Complete UI consuming backend APIs

### Integration Tasks (All Teams)
**Tasks**: I.1-I.10 (Contracts, integration, deployment, validation, presentation)

---

## Timeline

### Day 1: Setup & Parallel Development
**Morning**: Define API contracts, create mocks, begin foundational setup  
**Afternoon**: Core workstream development (Tasks X.1-X.3)  
**Checkpoint**: All teams working with mocks

### Day 2: Core Feature Development
**Morning**: Continue workstream tasks (Tasks X.4-X.6)  
**Afternoon**: Complete workstreams (Tasks X.7-X.9)  
**Checkpoint**: All services working independently

### Day 3: Integration & Deployment
**Morning**: Backend integration, frontend-backend integration  
**Afternoon**: AWS deployment, begin dataset validation  
**Checkpoint**: Deployed application, 5+ examples validated

### Day 4: Validation & Polish
**Morning**: Complete dataset validation, bug fixes  
**Afternoon**: Presentation prep, practice demo  
**Checkpoint**: Demo polished, backup video recorded

### Day 5: Presentation Day
**Morning**: Final rehearsal  
**Presentation**: 10-minute demo (5 min live demo + 5 min context)  
**Post**: Create Phase 2 backlog, team retrospective

---

## Success Criteria

### Must-Have
✅ All 12 functional requirements implemented  
✅ Analysis completes in <10 seconds  
✅ 80%+ dataset validation pass rate  
✅ Deployed to AWS (Lambda + Amplify)  
✅ Smooth 10-minute presentation with live demo

### Documentation
✅ README enables new developer to run project  
✅ API documentation complete with examples  
✅ User guide for end users  
✅ Architecture docs with diagrams

### Demo Quality
✅ Progressive reveal showcases unique value  
✅ Before/after transformation clear  
✅ Business value quantified (time savings)

---

## Phase 2 Roadmap

### High Priority
- Image analysis & alt text generation
- Additional audiences (Prospective Students, Alumni, Donors, etc.)
- User authentication & cloud storage
- Batch processing multiple documents

### Medium Priority
- Additional channels (Print, Digital Signage, SMS, Video)
- Video script accessibility checking
- CMS integration (WordPress, Drupal plugins)
- Email system integration (MailChimp, Constant Contact)

### Low Priority
- Custom ruleset creation UI
- A/B testing tone variations  
- Compliance analytics dashboard
- Mobile app (iOS/Android)

---

## Risk Management

**Technical Risks**: Rate limits (use Haiku, caching), Knowledge Base failures (fallback to scraping), LLM format issues (text diffing fallback)

**Demo Risks**: Live demo failure (backup video), time overrun (practice with timer), poor dataset accuracy (iterate early)

**Team Risks**: Member unavailable (document everything), scope creep (strict Phase 1 adherence)

---

## References

**Dataset**: Team8Dataset.xlsx (300 sample communications, 27 fields)

**UIC Brand Guidelines**:
- https://brand.uic.edu/messaging/name-and-boilerplate/
- https://brand.uic.edu/messaging/brand-attributes-and-tone/
- https://brand.uic.edu/messaging/key-audience-and-messaging/
- https://brand.uic.edu/messaging/editorial-and-style-guide/

**Implementation Details**: See project-plans/MASTER_CHECKLIST.md for complete task list with checkboxes

---

**This specification represents the complete shared understanding developed through collaborative design sessions on October 8, 2026.**

