# Access Control Model

## Designing Your Access Model

An effective access control model balances security, usability, and auditability. Design before implementation.

## Three-Tier Access Model (Recommended)

### Tier 1: Administrators (5-10% of users)

**Who**: IT staff, Jira administrators, governance team

**Permissions**:
- Project/space configuration
- Permission scheme management
- User access provisioning
- System settings
- Workflow customization
- Automation rule management

**Responsibilities**:
- Maintain system integrity
- Manage users and permissions
- Enforce governance policies
- Audit system activity

**Audit Significance**: Direct accountability for all system configuration

### Tier 2: Contributors (60-80% of users)

**Who**: Project team members, subject matter experts

**Permissions**:
- Browse/view project items
- Create issues in assigned projects
- Edit assigned issues
- Transition issues through workflow
- Comment on issues
- View reports and dashboards

**Restrictions**:
- Cannot modify workflows
- Cannot change permissions
- Cannot delete issues (typically)
- Cannot create projects

**Audit Significance**: Execute actual work; audit trail tracks their actions

### Tier 3: Viewers (10-30% of users)

**Who**: Stakeholders, executives, reporting teams

**Permissions**:
- View items in assigned projects
- View dashboards and reports
- Comment on items (limited)
- Create read-only filters

**Restrictions**:
- Cannot create issues
- Cannot edit issues
- Cannot transition statuses
- Cannot access admin functions

**Audit Significance**: Read-only access reduces compliance risk

## Project-Specific Access Patterns

### Pattern 1: Open Project (Everyone can contribute)

**Use When**: Internal projects, innovation initiatives, cross-functional teams

**Configuration**:
- Everyone in organization gets "Contributor" role
- Clear escalation path for issues
- Public dashboards and reporting

**Audit Implications**: Requires robust audit logging

### Pattern 2: Team-Specific Project (Controlled access)

**Use When**: Departmental projects, sensitive work, government projects

**Configuration**:
- Only team members get access
- Explicit permission grants
- View-only for stakeholders

**Audit Implications**: Clear accountability boundaries

### Pattern 3: Classified Project (Restricted access)

**Use When**: Compliance, security, sensitive government work

**Configuration**:
- Minimal access (need-to-know only)
- Individual user permissions (not groups)
- Separate audit trail review
- Executive approvals for access

**Audit Implications**: Highly auditable; clear access justification needed

## Permission Decision Tree

**Q1: Is person a Jira administrator?**
→ YES: Grant admin permissions, document role  
→ NO: Go to Q2

**Q2: Is person on project team?**
→ YES: Grant contributor permissions for project  
→ NO: Go to Q3

**Q3: Does person need visibility (reports/dashboards)?**
→ YES: Grant viewer permissions  
→ NO: No access; document decision

## Access Change Procedures

### New User Access

1. **Request**: Manager submits access request
2. **Approval**: Jira admin reviews and approves
3. **Provision**: Add user to appropriate project/role
4. **Verify**: User confirms access working
5. **Document**: Record date, role, approver

### Access Removal

1. **Notification**: Employee departing or role changing
2. **Deprovisioning**: Remove project access within 1 business day
3. **Verification**: Confirm access removed
4. **Archival**: Document user permissions at departure
5. **Retention**: Keep records for compliance period

### Access Change

1. **Request**: Manager submits role change request
2. **Approval**: Jira admin approves change
3. **Update**: Modify permissions to new role
4. **Verification**: User confirms new access correct
5. **Document**: Record change, date, approver

## Segregation of Duties Example

```
Project Manager (Admin)
├── Can: Configure workflows, manage permissions
└── Cannot: Execute work directly

Developer (Contributor)
├── Can: Create and edit issues, transition work
└── Cannot: Change workflows or permissions

Reviewer (Contributor)
├── Can: Review and approve specific issues
└── Cannot: Create initial work items

Auditor (Viewer)
├── Can: View all items and reports
└── Cannot: Edit or create items
```

## Access Audit Checklist

**Monthly Review**:
✅ List all active users  
✅ Verify each user's role matches job function  
✅ Identify orphaned or unused accounts  
✅ Document any permission mismatches  
✅ Remove access for changed roles  
✅ Record audit findings  

**Quarterly Review**:
✅ Review overall access model effectiveness  
✅ Assess if tiers adequate  
✅ Identify access pattern improvements  
✅ Plan any organizational changes  

## Common Access Control Problems

❌ **Problem**: Everyone is Contributor (no Viewer tier)  
✅ **Solution**: Create Viewer role; assign non-contributors

❌ **Problem**: No documentation of why users have access  
✅ **Solution**: Maintain access justification log

❌ **Problem**: Access never removed when role changes  
✅ **Solution**: Enforce quarterly reviews; audit departures

❌ **Problem**: No distinction between project admin and system admin  
✅ **Solution**: Create project-level admin role; limit system admins

## Next Steps

- [Audit Trails & Logging](./audit-trails.md) - Track access changes
- [Permission Management Procedures](../procedures/permission-management.md) - Implementation
- [Compliance Framework](../compliance/compliance-framework.md) - Full compliance model

---

**Estimated Reading Time**: 12 minutes  
**Criticality**: ⭐⭐⭐⭐⭐ (ESSENTIAL)
