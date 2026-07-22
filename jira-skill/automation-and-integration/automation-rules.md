# Automation Rules Guide

## What Is Automation?

Jira automation enables teams to "eliminate manual, repetitive tasks through a simple no-code rule builder."

## Three Core Components

### 1. Triggers
**Definition**: Events that initiate rule execution

**Examples**:
- Issue created
- Status changed
- Field value changed
- Comment added
- External event (GitHub, Bitbucket)
- Scheduled time

**Execution**: Manual, conditional, or scheduled

### 2. Conditions
**Definition**: Criteria determining if rule continues

**Types**:
- Field conditions (value equals something)
- Related issue conditions (parent has status X)
- User properties (assigned to current user)
- Expression conditions (custom logic)

**Logic**: If condition fails, rule stops; subsequent actions skipped

### 3. Actions
**Definition**: Work automation rule performs

**Examples**:
- Edit issues (update fields, change assignee)
- Send notifications (Slack, email, Teams)
- Create sub-tasks
- Transition issues (change status)
- Add comments
- Link issues
- Create child issues

## Common Automation Patterns

### Pattern 1: Auto-Transition on Completion
**Trigger**: All sub-tasks completed  
**Condition**: None  
**Action**: Transition parent to "Done"  
**Value**: Automatic parent status updates

### Pattern 2: Auto-Assign Load Balancing
**Trigger**: Issue created  
**Condition**: Issue type = Bug  
**Action**: Assign to user with fewest assigned items  
**Value**: Even workload distribution

### Pattern 3: Auto-Create Sub-Tasks
**Trigger**: Issue created  
**Condition**: Issue type = Epic  
**Action**: Create sub-tasks for: Design, Develop, Test  
**Value**: Consistent decomposition

### Pattern 4: Notify Stakeholders
**Trigger**: Status changed to "In Review"  
**Condition**: Issue type = Release  
**Action**: Send Slack notification to #releases channel  
**Value**: Real-time team notification

### Pattern 5: Escalation on Overdue
**Trigger**: Scheduled (daily)  
**Condition**: Due date < today AND status != Done  
**Action**: Add comment: "Overdue - please update status"  
**Value**: Compliance with deadlines

## Advanced Capabilities

### Branching
**Purpose**: Execute different actions for related items

**Examples**:
- Update all child issues when parent transitions
- Cascade field values to linked issues
- Perform different actions based on parent type

### Smart Values
**Purpose**: Dynamic data in automation rules

**Examples**:
- `{{now.plusDays(5)}}` - Calculate future dates
- `{{issue.summary}}` - Reference issue fields
- `{{issue.parent}}` - Access parent issue
- `{{assignee.displayName}}` - Get user name

## Governance Best Practices

### Documentation
- Document every rule's purpose
- Explain triggers, conditions, actions
- Record who created rule and when
- Note any special considerations

### Approval Process
- Review rule logic before enabling
- Test with sample data
- Get approval before production
- Document approval

### Monitoring
- Review rule execution logs monthly
- Identify any unexpected behaviors
- Disable unused rules
- Test rule modifications before enabling

### Compliance
**Critical**: Automation creates audit trail. All automated actions are logged.

**Audit Trail Includes**:
- When rule triggered
- What actions executed
- Success/failure status
- User/system executing rule

## Rule Actor (Who Executes)

**Default**: Automation app user (system account)

**Alternative**: Specify individual user

**Importance**: Actor must have permissions for all actions. If rule fails, check actor permissions.

## Common Rule Mistakes

❌ **Mistake**: Condition never met (rule never executes)  
✅ **Fix**: Test condition logic with sample data

❌ **Mistake**: Rule causes infinite loop (rule triggers itself)  
✅ **Fix**: Condition must prevent recursion

❌ **Mistake**: No one knows what rule does  
✅ **Fix**: Document purpose clearly

❌ **Mistake**: Rule fails because actor lacks permissions  
✅ **Fix**: Verify actor has necessary permissions

## Audit Trail Review

**Procedure**:
1. Settings → Automation → Audit
2. Select rule
3. Review execution history
4. Verify rule behaved as expected
5. Document any discrepancies

## Next Steps

- [Integrations Guide](./integrations.md) - Connect external tools
- [Setup Procedures](../procedures/automation-setup.md) - Create rules
- [Best Practices](../compliance/best-practices.md) - Governance

---

**Estimated Reading Time**: 10 minutes
