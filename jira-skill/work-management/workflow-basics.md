# Workflow Basics

## What Is a Workflow?

A workflow is "the path your work items take from creation to completion." It represents your organizational process and enforces how work flows through stages.

## Three Core Workflow Elements

### 1. Status
**Definition**: Indicates a work item's position within the workflow

**Common Statuses**:
- Open, To Do (new items)
- In Progress (active work)
- In Review (awaiting approval)
- Testing (quality verification)
- Done, Closed (completed)

**Customizable**: Create statuses matching your process

**Audit Value**: Status clearly documents work state at any point

### 2. Transition
**Definition**: "The action being taken to move a work item from status to status"

**Characteristics**:
- Unidirectional (to go backwards, need separate transition)
- Named descriptively ("Start Work," "Submit for Review," "Complete")
- May have conditions or approval requirements

**Example Transitions**:
- To Do → In Progress ("Start Work")
- In Progress → In Review ("Request Review")
- In Review → Done ("Approve and Release")

**Audit Value**: Transitions document workflow execution

### 3. Resolution (Optional)
**Definition**: Final state applied when item completes

**Examples**: Fixed, Won't Fix, Duplicate, Deferred

**Availability**: Company-managed projects only

**Audit Value**: Resolution reason documents why item closed

## Typical Workflow Example: Software Development

```
To Do
   ↓ (Start Work)
In Progress
   ↓ (Submit for Review)
In Review
   ↓ (Needs Work / Approved)
   ├→ (Needs Work) → In Progress
   └→ (Approved) → Testing
                    ↓ (Testing Complete)
                    Done
```

## Team-Managed vs. Company-Managed Workflows

**Team-Managed**:
- Edit workflows directly in project
- Graphical Workflow Editor
- Self-contained changes

**Company-Managed**:
- Define workflow schemes (apply to multiple projects)
- Advanced configuration options
- Condition-based transitions
- Consistent workflows across organization

## Board-Workflow Alignment

**Critical**: Board columns should match workflow statuses

**Example Alignment**:
- Board Column "To Do" → Workflow Status "To Do"
- Board Column "In Progress" → Workflow Status "In Progress"
- Board Column "Done" → Workflow Status "Done"

**When Misaligned**: Workflow and board visualization conflict, confusing teams

## Workflow Customization Best Practices

1. **Match Your Process**: Design workflow reflecting actual work progression
2. **Clear Naming**: Use descriptive status and transition names
3. **Minimal Complexity**: Avoid excessive statuses (typically 3-6)
4. **Documentation**: Document workflow purpose and transitions
5. **Testing**: Test workflow with sample items before full deployment
6. **Regular Review**: Periodically evaluate workflow effectiveness

## When to Customize Workflows

**Customize When**:
- Workflow doesn't match your actual process
- Required approvals missing
- Status names are confusing
- Multiple team branches needed

**Don't Over-Customize**: Simpler workflows are easier to manage and audit

## Workflow Examples by Domain

**Software Development**: To Do → In Progress → In Review → Testing → Done

**Marketing Campaigns**: Concept → Planning → Execution → Review → Published

**Support/IT**: Reported → Assigned → In Progress → Resolved → Closed

**Government Compliance**: Submitted → Under Review → Approved → Implemented → Audited

## Audit-Relevant Workflow Considerations

✅ Document your workflow and rationale  
✅ Require approval transitions for critical items  
✅ Track status changes for compliance  
✅ Enforce transitions (don't allow jumping statuses)  
✅ Include resolution documentation  

## Next Steps

- [Board Types](./board-types.md) - Visualize your workflow
- [Automation Rules](../automation-and-integration/automation-rules.md) - Auto-transition items
- [Setup Procedures](../procedures/setup-procedures.md) - Custom workflow setup

---

**Estimated Reading Time**: 10 minutes
