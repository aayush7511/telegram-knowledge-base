# Core Jira Concepts

## The Three Pillars of Jira

Every Jira implementation rests on three essential elements:

### 1. Spaces
**Definition**: Containers that organize and track work items toward specific outcomes.

Think of spaces as projects or workstreams. Each space represents a distinct area of organizational work (e.g., "Mobile App Development," "Marketing Campaign 2026").

**Key Points**:
- Team-managed: Self-contained teams with autonomy
- Company-managed: Standardized processes across organization

### 2. Work Items
**Definition**: Individual units tracking specific organizational tasks.

Also called "issues," work items represent the atomic unit of work—anything that needs tracking (bugs, features, tasks, requests).

### 3. People
**Definition**: Team members invited to collaborate and execute work.

Individuals assigned roles within spaces and given permissions to create, edit, and transition work items.

## Foundational Terminology

| Term | Definition | Example |
|------|-----------|---------|
| **Space/Project** | Container for organized work | "Mobile App v2.0" |
| **Work Item/Issue** | Individual trackable unit | "Fix login button on mobile" |
| **Epic** | Large initiative containing multiple items | "Launch user authentication" |
| **Story** | User-focused requirement | "As a user, I want to reset my password" |
| **Task** | General work item | "Configure production server" |
| **Bug** | Problem requiring resolution | "Login page missing validation" |
| **Sub-task** | Detailed breakdown of work | "Test password reset email" |
| **Board** | Visual workflow representation | Scrum/Kanban board |
| **Sprint** | Time-boxed iteration (Scrum) | 2-week development cycle |
| **Status** | Current position in workflow | To Do, In Progress, Done |
| **Transition** | Moving work between statuses | Start Work, Complete |
| **Workflow** | Path from creation to completion | Todo → In Progress → Review → Done |

## Work Item Hierarchy

```
Epic (Initiative Level)
├── Story 1 (User Requirement)
│   ├── Sub-task 1.1 (Activity)
│   ├── Sub-task 1.2
│   └── Sub-task 1.3
├── Story 2
│   └── Sub-task 2.1
└── Bug 1 (Issue)
    └── Sub-task Bug 1.1
```

## Key Relationships

**Parent-Child**: Epics contain stories; stories contain sub-tasks

**Linked Issues**: Dependencies showing:
- Blocks/Is Blocked By (dependency)
- Clones/Is Cloned By (duplication)
- Duplicates/Is Duplicated By (exact copy)
- Relates To (general relationship)

## Next Steps

- [Jira Editions](./editions-overview.md) - Understand pricing tiers
- [Project Types](../setup-and-projects/project-types.md) - How to organize your work
- [Work Items Guide](../work-management/work-items.md) - Deep dive into issues

---

**Estimated Reading Time**: 8 minutes
