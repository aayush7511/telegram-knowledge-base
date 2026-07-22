# Audit Trails & Logging

## Critical Compliance Component

Audit trails provide the evidence that your Jira implementation complies with government regulations. **Without audit trails, you cannot prove compliance.**

## What Jira Logs Automatically

### Work Item Audit Trails
- **Creation**: Date, time, creator recorded
- **Field Changes**: All modifications logged with before/after values
- **Status Transitions**: Workflow progression documented
- **Comments**: Discussion and decisions recorded
- **Attachments**: File additions tracked

**Access**: View issue history in each work item

### Automation Audit Logs
- **Rule Triggers**: When automation rules execute
- **Execution Results**: Success/failure documented
- **Actions Executed**: Changes automation made
- **Rule Actors**: User/system account executing rule

**Access Levels**:
- Individual rule audit log
- Project-wide automation audit
- Global automation audit

### Permission Audit Trail
- **Permission Helper Tool**: Diagnose user permissions
- **Role Assignment**: Document who has which role
- **Permission Changes**: Track modifications

**Access**: Settings → Permission Helper

## Critical Audit Trail Gaps

**⚠️ WARNING**: Official Jira documentation acknowledges these gaps:

- ❌ No board configuration change logs
- ❌ No workflow customization audit trail
- ❌ No project setting modification logs
- ❌ No user access pattern tracking
- ❌ No sensitive data access monitoring

## Supplemental Audit Documentation Needed

For government compliance, **you must document manually**:

### Configuration Documentation
Maintain separate log tracking:
- Project creation/deletion
- Workflow changes and dates
- Board configuration changes
- Permission scheme modifications
- Integration installations
- Automation rule changes

**Format**: Spreadsheet or documentation system
```
Date | Change Type | Description | Made By | Approved By | Reason
-----|-------------|-------------|---------|------------|-------
2026-07-22 | Workflow | Added "In Review" status | J.Smith | Admin | Approval requirement
```

### User Access Log
Track all access provisioning:
- User name
- Project/role granted
- Date granted
- Granting administrator
- Business justification
- Date removed (if applicable)

### Change Control Log
Document all significant changes:
- What changed
- When changed
- Who approved
- Why changed
- Impact assessment
- Rollback plan (if needed)

### Incident Log
Track access violations or audit findings:
- Incident date
- Incident type (unauthorized access, configuration change, permission override)
- Persons involved
- Resolution
- Prevention measures

## Using Permission Helper Tool

**Purpose**: Diagnose why user does/does not have permission

**Access**: System → Permission Helper

**Capability**: Trace permission inheritance and identify access reasons

**Audit Value**: Document permission troubleshooting and verification

**Procedure**:
1. Navigate to Permission Helper
2. Select user and project
3. Select specific permission
4. Tool shows permission status and reason
5. Document findings in compliance file

## Work Item Change Tracking

**Procedure for Audit Review**:

1. Open specific issue
2. Click "History" tab
3. Review all changes:
   - Status transitions
   - Field modifications
   - Comments
   - Attachments
4. Verify changes appropriate and authorized
5. Document discrepancies

## Automation Rule Audit

**Procedure**:

1. Settings → Automation → Audit
2. Select rule of interest
3. Review execution history:
   - When rule triggered
   - What actions executed
   - Success/failure status
4. Verify rule executed as intended
5. Document any unexpected executions

## Audit Trail Retention Requirements

**Government Standards** (varies by agency):
- Typical retention: 3-7 years
- Critical audit trails: 10+ years
- Financial/compliance: Per regulation

**Implementation**:
- Document retention policy
- Regular exports of audit trails
- Archive older logs
- Ensure searchability of historical data

## Creating an Audit Evidence Package

**For Government Review**:

1. **Configuration Documentation**
   - Current workflow diagram
   - Permission scheme description
   - Project structure documentation

2. **User Access Evidence**
   - Current user list with roles
   - Access provisioning log (6+ months)
   - Quarterly access audit reports

3. **Change Control Evidence**
   - All significant changes (6+ months)
   - Approval documentation
   - Rollback records

4. **Sample Work Item Audit**
   - 5-10 representative issues showing:
   - Creation to completion
   - All transitions and approvals
   - Comments and decisions

5. **Automation Documentation**
   - All active automation rules
   - Rule execution evidence
   - Audit logs sample

6. **Incident/Issue Log**
   - Any permission violations
   - Unauthorized access attempts
   - Access misconfiguration discoveries
   - Resolutions taken

## Audit Trail Best Practices

✅ Document configuration changes in real-time  
✅ Export automation audit logs monthly  
✅ Conduct quarterly permission reviews  
✅ Maintain change control approvals  
✅ Archive old logs securely  
✅ Test audit trail accessibility  
✅ Update documentation annually  

## Compliance Checklist

**Audit Trail Compliance**:
✅ Jira automatic logging enabled?  
✅ Manual configuration documentation in place?  
✅ User access log maintained?  
✅ Change control log documented?  
✅ Incident tracking system operational?  
✅ Retention policy defined?  
✅ Regular audit reviews scheduled?  
✅ Audit evidence package prepared?  

## Next Steps

- [Compliance Best Practices](../compliance/best-practices.md) - Full governance model
- [Audit Procedures](../compliance/audit-procedures.md) - Regular review cycles
- [Compliance Framework](../compliance/compliance-framework.md) - Implementation

---

**Estimated Reading Time**: 13 minutes  
**Criticality**: ⭐⭐⭐⭐⭐ (ESSENTIAL)
