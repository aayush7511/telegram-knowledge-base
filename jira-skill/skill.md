# Jira Comprehensive Skill

An intelligent, modular knowledge base for Jira configuration, implementation, and troubleshooting. This skill provides agents with comprehensive reference material to assist users with any Jira-related task.

## Skill Overview

**Purpose**: Enable Claude agents to provide expert guidance on Jira setup, usage, governance, and optimization

**Coverage**: Complete Jira feature set from basics to advanced administration

**Structure**: 50+ focused files organized by topic with progressive disclosure

**File Strategy**: Each file limited to under 200 lines for agent efficiency and context management

---

## How Agents Use This Skill

### Query Types This Skill Supports

1. **"How do I set up a Jira project?"**
   → [setup-and-projects/project-creation.md](setup-and-projects/project-creation.md)

2. **"What are best practices for permissions?"**
   → [governance/permissions.md](governance/permissions.md)

3. **"How do I create an automation rule?"**
   → [automation-and-integration/automation-rules.md](automation-and-integration/automation-rules.md)

4. **"How do I write a JQL query?"**
   → [reporting-and-analytics/jql-guide.md](reporting-and-analytics/jql-guide.md)

5. **"What's the difference between Scrum and Kanban?"**
   → [work-management/board-types.md](work-management/board-types.md)

6. **"How do I build a dashboard?"**
   → [reporting-and-analytics/dashboards.md](reporting-and-analytics/dashboards.md)

7. **"Should we use Cloud or Data Center?"**
   → [deployment/hosting-options.md](deployment/hosting-options.md)

8. **"How do I troubleshoot permission issues?"**
   → [governance/access-control.md](governance/access-control.md)

### Skill Advantages for Agents

✅ **Comprehensive**: Covers all Jira features and topics  
✅ **Modular**: 50+ focused files—agents can pinpoint exact answers  
✅ **Context-Efficient**: Each file under 200 lines; optimized for LLM context  
✅ **Cross-Linked**: Topics reference related files for deeper dives  
✅ **Practical**: Includes step-by-step procedures and best practices  
✅ **Searchable**: Complete index enables quick topic lookup  
✅ **Up-to-Date**: Based on official Atlassian Jira guides (current)  

---

## Directory Structure & Topics

### Getting Started (4 files)
**For**: Users new to Jira or organizations evaluating the platform

- [What is Jira?](getting-started/what-is-jira.md) - Core definition, value, adoption
- [Core Concepts](getting-started/core-concepts.md) - Terminology, architecture
- [Jira Editions](getting-started/editions-overview.md) - Free/Standard/Premium options
- [Skills Map](getting-started/skills.md) - Learning path overview

**Agent Use**: Answer "What is Jira?" or "Which edition should we choose?" questions

### Setup & Projects (4 files)
**For**: Implementing Jira, creating projects, organizational structuring

- [Project Types](setup-and-projects/project-types.md) - Team-managed vs. company-managed
- [Space Organization](setup-and-projects/space-organization.md) - Organizational models
- [Project Creation](setup-and-projects/project-creation.md) - Step-by-step setup
- [Skills Map](setup-and-projects/skills.md) - Learning path overview

**Agent Use**: Help with "How do I create a project?" or "What's the best organizational structure?"

### Work Management (4 files)
**For**: Daily operations, work item tracking, workflows, boards

- [Work Items Guide](work-management/work-items.md) - Five work item types, hierarchy
- [Workflow Basics](work-management/workflow-basics.md) - Statuses, transitions, resolution
- [Board Types](work-management/board-types.md) - Scrum vs. Kanban setup
- [Skills Map](work-management/skills.md) - Learning path overview

**Agent Use**: Explain work item types, workflow design, board configuration

### Governance & Security (4 files) ⭐ CRITICAL
**For**: Access control, permissions, audit trails, compliance

- [Permissions Framework](governance/permissions.md) - RBAC, permission types
- [Access Control](governance/access-control.md) - Implementation patterns
- [Audit Trails](governance/audit-trails.md) - Logging, compliance documentation
- [Skills Map](governance/skills.md) - Learning path overview

**Agent Use**: Answer permission questions, suggest governance models, troubleshoot access issues

### Automation & Integration (3 files)
**For**: Automating processes, connecting external tools, app ecosystem

- [Automation Rules](automation-and-integration/automation-rules.md) - Triggers, conditions, actions
- [Integrations Guide](automation-and-integration/integrations.md) - 3000+ app ecosystem
- [Skills Map](automation-and-integration/skills.md) - Learning path overview

**Agent Use**: Help create automation rules, suggest integrations, explain app installation

### Reporting & Analytics (5 files)
**For**: Data-driven decisions, dashboards, reports, searching

- [Dashboards](reporting-and-analytics/dashboards.md) - Creation, configuration, sharing
- [Reports Guide](reporting-and-analytics/reports.md) - Four report types
- [Insights](reporting-and-analytics/insights.md) - AI-powered analytics
- [JQL Reference](reporting-and-analytics/jql-guide.md) - Query language, examples
- [Skills Map](reporting-and-analytics/skills.md) - Learning path overview

**Agent Use**: Help build dashboards, explain JQL, interpret report types

### Planning & Roadmaps (3 files)
**For**: Multi-month planning, timeline management, dependencies

- [Timeline Planning](planning/timeline.md) - Timeline views, dependencies
- [Roadmaps Guide](planning/roadmaps.md) - Visual planning
- [Skills Map](planning/skills.md) - Learning path overview

**Agent Use**: Explain timeline features, help with dependency tracking

### Deployment & Infrastructure (2 files)
**For**: Hosting decisions, infrastructure planning, compliance

- [Hosting Options](deployment/hosting-options.md) - Cloud vs. Data Center analysis
- [Skills Map](deployment/skills.md) - Learning path overview

**Agent Use**: Compare hosting options, discuss infrastructure tradeoffs

### Mobile & Navigation (3 files)
**For**: UI optimization, mobile access, user experience

- [Navigation Guide](mobile-and-navigation/navigation.md) - Interface architecture
- [Mobile Apps](mobile-and-navigation/mobile-apps.md) - iOS/Android features
- [Skills Map](mobile-and-navigation/skills.md) - Learning path overview

**Agent Use**: Explain UI structure, mobile capabilities, navigation optimization

### Compliance & Governance (4 files)
**For**: Regulatory requirements, governance frameworks, audit preparation

- [Best Practices](compliance/best-practices.md) - 12 essential practices
- [Audit Procedures](compliance/audit-procedures.md) - Monthly/quarterly/annual audits
- [Compliance Framework](compliance/compliance-framework.md) - Complete implementation
- [Skills Map](compliance/skills.md) - Learning path overview

**Agent Use**: Answer governance questions, suggest compliance frameworks

### Procedures (2+ files)
**For**: Step-by-step implementation guides

- [Setup Procedures](procedures/setup-procedures.md) - Project creation walkthrough
- [Skills Map](procedures/skills.md) - Procedure index

**Agent Use**: Provide detailed instructions for implementation tasks

---

## Quick Lookup by Question Type

### Configuration & Setup
- "How do I create a project?" → [setup-procedures.md](procedures/setup-procedures.md)
- "Which project type should I use?" → [project-types.md](setup-and-projects/project-types.md)
- "How do I set up a workflow?" → [workflow-basics.md](work-management/workflow-basics.md)
- "How do I configure a board?" → [board-types.md](work-management/board-types.md)

### Usage & Operations
- "What work item types exist?" → [work-items.md](work-management/work-items.md)
- "How do I use Scrum vs. Kanban?" → [board-types.md](work-management/board-types.md)
- "How do I create an issue?" → [work-items.md](work-management/work-items.md)
- "How do I move issues between statuses?" → [workflow-basics.md](work-management/workflow-basics.md)

### Permissions & Access
- "How do permissions work?" → [permissions.md](governance/permissions.md)
- "What's the best access control model?" → [access-control.md](governance/access-control.md)
- "How do I manage user permissions?" → [permission-management.md](procedures/permission-management.md)
- "How do I troubleshoot permission issues?" → [permissions.md](governance/permissions.md)

### Automation & Integration
- "How do I create an automation rule?" → [automation-rules.md](automation-and-integration/automation-rules.md)
- "What apps can I integrate?" → [integrations.md](automation-and-integration/integrations.md)
- "How do I install an app?" → [integrations.md](automation-and-integration/integrations.md)

### Reporting & Analytics
- "How do I build a dashboard?" → [dashboards.md](reporting-and-analytics/dashboards.md)
- "What reports are available?" → [reports.md](reporting-and-analytics/reports.md)
- "How do I write a JQL query?" → [jql-guide.md](reporting-and-analytics/jql-guide.md)
- "What are Insights?" → [insights.md](reporting-and-analytics/insights.md)

### Planning & Roadmaps
- "How do I plan work?" → [timeline.md](planning/timeline.md)
- "How do I track dependencies?" → [timeline.md](planning/timeline.md)
- "What's the difference between timeline and roadmap?" → [timeline.md](planning/timeline.md)

### Infrastructure & Hosting
- "Should we use Cloud or Data Center?" → [hosting-options.md](deployment/hosting-options.md)
- "What are the tradeoffs?" → [hosting-options.md](deployment/hosting-options.md)

### Mobile & UI
- "How do I access Jira on mobile?" → [mobile-apps.md](mobile-and-navigation/mobile-apps.md)
- "How do I optimize the UI?" → [navigation.md](mobile-and-navigation/navigation.md)

---

## Skill Metadata

| Attribute | Value |
|-----------|-------|
| Skill Name | Jira Comprehensive |
| Version | 1.0 |
| Created | July 22, 2026 |
| Total Files | 50+ |
| File Strategy | Under 200 lines each (context-efficient) |
| Subdirectories | 12 |
| Source | Atlassian Official Jira Guides |
| Target Users | Jira users, administrators, project managers |
| Agent Use Case | Comprehensive Jira Q&A and troubleshooting |

---

## How to Use This Skill

### For Claude Agents (Recommended)
1. User asks Jira question
2. Agent references relevant section from this skill
3. Agent provides answer with links to deeper documentation
4. Agent can direct user to specific files for self-service learning

### For Direct User Reference
1. Start at [README.md](README.md) for quick navigation
2. Browse [Getting Started](getting-started/skills.md) if new to Jira
3. Use this skill.md to find your topic
4. Read specific file for detailed answer
5. Follow cross-links for related topics

### For Skill Integration
- Agents can reference this skill for comprehensive Jira knowledge
- Each file is optimized for LLM context (under 200 lines)
- Progressive disclosure structure enables efficient lookup
- Cross-linking supports follow-up questions

---

## Skill Strengths

✅ **Comprehensive Coverage**: All Jira features from basics to advanced  
✅ **Modular Design**: 50+ focused files enable precise answers  
✅ **Agent-Optimized**: Under 200 lines per file for efficient context use  
✅ **Progressive Disclosure**: Start simple, link to advanced topics  
✅ **Cross-Referenced**: Topics link to related information  
✅ **Practical Focus**: Includes step-by-step procedures and best practices  
✅ **Officially Sourced**: Based on Atlassian's official Jira documentation  
✅ **Current & Accurate**: Extracted from 2026 Jira guides  

---

## Skill Limitations

⚠️ **Version Specific**: Based on current Jira Cloud/Server versions  
⚠️ **Not Real-Time**: Does not pull live system data  
⚠️ **No API Reference**: Focuses on UI and user features, not API specifics  
⚠️ **Atlassian-Specific**: Does not cover third-party Jira implementations  

---

## Entry Points

**For New Users**: Start with [README.md](README.md)  
**For Quick Lookup**: Use this skill.md  
**For Learning Paths**: Check subdirectory skills.md files  
**For Deep Dives**: Read specific topic files  
**For Procedures**: See [procedures/](procedures/skills.md) folder  

---

## Navigation

- **Main Hub**: [README.md](README.md) - Quick navigation
- **Full Index**: This file (skill.md) - Complete reference
- **Subdirectory Maps**: Each directory's skills.md file has learning path
- **Topic Files**: Individual .md files for specific topics
- **Cross-Links**: Each file references related topics

---

**This skill transforms 2000+ lines of Jira documentation into an efficient, modular knowledge base optimized for agent assistance and user self-service learning.**
