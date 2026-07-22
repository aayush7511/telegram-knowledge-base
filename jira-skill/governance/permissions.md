# Permissions Framework

## Critical Foundation

Permissions form the foundation of Jira governance. Incorrect configuration is the #1 source of compliance violations in Jira deployments.

## Three Permission Levels

### Level 1: Global Permissions (System-Wide)

**Scope**: Applied across entire Jira instance

**Key Examples**:
- Log in to Jira
- View user lists
- Administer Jira system
- System configuration access
- Manage global automations

**Audit Significance**: Instance-level access controls; affects all projects

**Management**: Jira System Administrators only

**Principle**: Minimize global permission grants

### Level 2: Space Permissions (Project-Level)

**Scope**: Applied to individual projects/spaces

**Key Examples**:
- Browse space (view issues)
- Create work items
- Edit work items
- Transition items (move between statuses)
- Manage sprints
- Manage space settings

**Audit Significance**: Project-level boundaries

**Management**: Space administrators and Jira System Administrators

**Principle**: Base most access at space level

### Level 3: Work Item Permissions (Granular)

**Scope**: Applied at individual issue level

**Key Examples**:
- Assign work items
- Create work items
- Edit work items
- Transition work items
- Delete work items
- Manage attachments

**Audit Significance**: Item-level authorization

**Management**: Controlled via permission schemes

**Principle**: Enforced through workflows and automation

## Role-Based Access Control (RBAC)

### Three Default Space Roles

**1. Administrators**
- **Permissions**: Manage space settings, user assignments, permissions
- **Responsibilities**: Configure workflows, boards, permissions
- **Typical Users**: Project managers, team leads
- **Audit Significance**: High-level accountability

**2. Developers**
- **Permissions**: Create issues, edit issues, transition items, assign
- **Responsibilities**: Execute work, update status, collaborate
- **Typical Users**: Team members, contributors
- **Audit Significance**: Work execution accountability

**3. Users**
- **Permissions**: Create and comment on items (limited edit)
- **Responsibilities**: Report issues, view boards, comment
- **Typical Users**: Stakeholders, reporters
- **Audit Significance**: Limited actions reduce risk

### Default System Groups

- **jira-administrators**: System-level administrative permissions
- **jira-users**: General user access

## Permission Schemes

**Definition**: "Associations between workflows and work types" that enable consistent permission application

**Key Features**:
- Centralized policy application
- Per-space customization
- Group, role, and user-based assignment
- Consistent enforcement across projects

**Important Limitation**: Space administrators CANNOT customize permission schemes (requires Jira System Administrator)

## Permission Best Practices

### Principle of Least Privilege
Grant only permissions necessary for job function:
- Don't grant admin to everyone
- Distinguish read vs. write permissions
- Limit delete permissions strictly

### Documentation
- Document permission scheme purposes
- Record rationale for each role
- Maintain permission change logs
- Update documentation quarterly

### Regular Audits
- Review permissions monthly
- Identify unused permissions
- Remove access when roles change
- Document audit findings

### Segregation of Duties
- Different users for different functions
- Admin ≠ Approver ≠ Executor
- Document segregation rationale
- Enforce through permissions

## Common Permission Mistakes

❌ **Mistake 1**: Everyone is "Administrator"  
**Impact**: No audit trail, anyone can change anything  
**Fix**: Create specific roles; use only for admins

❌ **Mistake 2**: No permission documentation  
**Impact**: Compliance review failures, audit gaps  
**Fix**: Document every permission scheme

❌ **Mistake 3**: Shared accounts (multiple users)  
**Impact**: Broken audit trail accountability  
**Fix**: Enforce individual user accounts

❌ **Mistake 4**: Static permissions (never reviewed)  
**Impact**: Accumulation of unnecessary access  
**Fix**: Quarterly permission audits

❌ **Mistake 5**: Over-permissioning for convenience  
**Impact**: Security exposure, compliance violations  
**Fix**: Apply least privilege principle

## Permission Audit Procedure

**Monthly Audit**:
1. List all users and their assigned permissions
2. For each user, verify role matches current job
3. Remove access for changed roles
4. Document audit findings
5. Update permission documentation

**Quarterly Review**:
1. Review permission scheme purposes
2. Assess if current roles adequate
3. Identify unused permissions
4. Plan any role additions/removals
5. Document review findings

## Compliance Checkpoint

✅ All permissions documented?  
✅ Principle of least privilege applied?  
✅ Monthly audit process established?  
✅ Change log maintained?  
✅ Segregation of duties enforced?  

## Next Steps

- [Access Control Model](./access-control.md) - Implementation patterns
- [Audit Trails](./audit-trails.md) - Logging and compliance
- [Permission Management Procedures](../procedures/permission-management.md) - Step-by-step setup

---

**Estimated Reading Time**: 12 minutes  
**Criticality**: ⭐⭐⭐⭐⭐ (ESSENTIAL)
