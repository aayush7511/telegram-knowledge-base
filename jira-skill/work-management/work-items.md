# Work Items Guide

## What Are Work Items?

Work items are "units used to track bugs and individual pieces of work that must be completed." They represent the atomic unit of organizational accountability in Jira.

## Five Work Item Types

### Epic (Initiative Level)
**Purpose**: Large initiatives broken into multiple items  
**Characteristics**: Long duration, multiple child items, strategic alignment  
**Example**: "Implement user authentication system"  
**Audit Value**: Strategic initiative tracking  
**Use When**: Planning major feature or program

### Story (Requirement Level)
**Purpose**: User-focused requirements expressed from end-user perspective  
**Format**: "As a [user], I want [capability]"  
**Example**: "As a user, I want to reset my forgotten password"  
**Acceptance Criteria**: Includes definition of done  
**Audit Value**: Requirement documentation  
**Use When**: Capturing user needs and features

### Task (General Work)
**Purpose**: General work needing completion; catch-all item type  
**Characteristics**: No specific user perspective required  
**Example**: "Update server dependencies," "Configure production environment"  
**Audit Value**: General work documentation  
**Use When**: Work not fitting story or bug categories

### Bug (Defect)
**Purpose**: Problems requiring resolution  
**Characteristics**: Unexpected behavior, quality issues  
**Example**: "Login page missing input validation," "Mobile button unresponsive"  
**Audit Value**: Defect tracking and resolution  
**Use When**: Discovering and tracking quality issues

### Sub-task (Activity Level)
**Purpose**: Granular breakdown of standard work items  
**Parent**: Always belongs to Epic, Story, Task, or Bug  
**Example**: Parent: "Reset password" → Sub-tasks: "Write email template," "Create database migration," "Write tests"  
**Audit Value**: Activity-level detail  
**Use When**: Breaking large work into smaller activities

## Work Item Hierarchy Example

```
Epic: "Launch Authentication System"
├── Story: "Implement login flow"
│   ├── Sub-task: "Design login UI"
│   ├── Sub-task: "Implement backend API"
│   └── Sub-task: "Write integration tests"
├── Story: "Implement password reset"
│   ├── Sub-task: "Email template"
│   └── Sub-task: "Reset token validation"
└── Bug: "OAuth token expiration"
    └── Sub-task: "Add token refresh logic"
```

## Work Item Fields & Metadata

**Core Fields**:
- **Summary/Title**: Brief description
- **Description**: Detailed requirements
- **Assignee**: Responsible team member
- **Due Date**: Expected completion
- **Status**: Current position (To Do, In Progress, Done)
- **Priority**: Importance (Low, Medium, High, Critical)

**Relationships**:
- **Parent**: Epic/Story containing this item
- **Linked Issues**: Dependencies, duplicates, blocking relationships
- **Custom Fields**: Organization-specific metadata (compliance category, cost center, etc.)

## Work Item Lifecycle

1. **Creation** - New item added to backlog/board
2. **Transition** - Moves through workflow statuses
3. **Progress** - Updates and comments added
4. **Resolution** - Final status and completion indication
5. **Closure** - Item archived or marked done

## Audit-Relevant Practices

✅ Use consistent naming conventions  
✅ Fill description with context  
✅ Document decisions in comments  
✅ Link related items  
✅ Assign clear owners  
✅ Use appropriate priorities  
✅ Track due dates  

## Next Steps

- [Workflow Basics](./workflow-basics.md) - Moving items through statuses
- [Board Types](./board-types.md) - Visual work management
- [Automation Rules](../automation-and-integration/automation-rules.md) - Automate status updates

---

**Estimated Reading Time**: 10 minutes
