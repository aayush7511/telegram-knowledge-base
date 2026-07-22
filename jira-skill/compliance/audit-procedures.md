# Audit Procedures

## Regular Audit Schedule

Establish recurring audit procedures to maintain continuous compliance.

## Monthly Permission Audit (30 minutes)

**When**: First Monday of each month

**Procedure**:
1. Generate active user list with assigned roles
2. For each user:
   - Verify role matches current job function
   - Check if access still needed
   - Identify any permission anomalies
3. Remove access for changed roles
4. Document audit findings
5. Report exceptions to manager

**Checklist**:
✅ All users reviewed  
✅ Excess permissions identified  
✅ Changes documented  
✅ Audit report filed  

## Quarterly Comprehensive Audit (2 hours)

**When**: End of each quarter (Mar 31, Jun 30, Sep 30, Dec 31)

**Audit Components**:

**1. Access Review**
- Complete permission audit
- Identify unused accounts
- Assess role appropriateness
- Recommend role adjustments

**2. Configuration Review**
- Current workflow diagram verification
- Permission scheme documentation
- Project structure alignment
- Automation rule review

**3. Change Log Review**
- All changes made in quarter
- Verify changes approved
- Check documentation
- Identify uncontrolled changes

**4. Automation Audit**
- All active rules reviewed
- Execution logs sampled
- Unexpected behaviors noted
- Unused rules disabled

**5. Incident Log Review**
- Any unauthorized access?
- Configuration breaches?
- Policy violations?
- Resolutions effective?

**Output**: Quarterly audit report documenting findings and remediation

## Annual Compliance Audit (4-8 hours)

**When**: End of calendar year (December)

**Comprehensive Review**:

1. **Access Control Audit**
   - Full year of access changes
   - Hiring/termination review
   - Role change verification
   - Access removal timeliness

2. **Change Management Audit**
   - All significant changes reviewed
   - Approval documentation
   - Testing procedures
   - Rollback capability

3. **Automation Audit**
   - Full year of automation changes
   - Rule execution analysis
   - Unexpected behavior review
   - Maintenance procedures

4. **Workflow Compliance**
   - Workflow adherence
   - Status transition control
   - Approval enforcement
   - Exception tracking

5. **Incident Analysis**
   - Security events reviewed
   - Response timeliness
   - Resolutions verified
   - Prevention effectiveness

6. **Evidence Package**
   - Sample work items (complete lifecycle)
   - User access evidence
   - Change control documentation
   - Automation audit trail
   - Incident responses

**Output**: Annual compliance audit report with remediation plan

## Access Audit Template

```
Monthly Audit - [Month] [Year]

Audit Date: [Date]
Auditor: [Name]

Users Reviewed: [Number]
Users with Appropriate Access: [Number]
Users with Excess Access: [Number]
Users Requiring Access Removal: [Number]

Actions Taken:
- [User]: Removed [Permission] (reason)
- [User]: Updated role from [Old] to [New]
- [User]: Access maintained (current role appropriate)

Exceptions:
- [User]: [Exception description]

Audit Sign-off:
Auditor: _________________ Date: _________
Manager: ________________ Date: _________
```

## Change Control Audit Procedure

**Monthly Review of All Changes**:

| Change | Date | Changed By | Approved By | Documented? | Tested? | Status |
|--------|------|-----------|------------|------------|---------|--------|
| Workflow added "Approved" status | 2026-07-15 | J. Smith | Admin | ✅ | ✅ | OK |
| User X removed from project | 2026-07-18 | Admin | - | ❌ | N/A | DOCUMENT |

**Finding**: If change not documented, add to documentation log immediately.

## Automation Rule Audit

**Quarterly Review**:

For each automation rule:
1. ✅ Rule purpose clear?
2. ✅ Conditions documented?
3. ✅ Actions appropriate?
4. ✅ Execution logs reviewed?
5. ✅ Unexpected behaviors? (none expected)
6. ✅ Rule enabled or disabled appropriately?
7. ✅ Still needed?

**Finding**: Unused rules → disable them

## Incident Tracking

**Maintain Log of All Incidents**:

| Date | Type | Description | Resolution | Prevention |
|------|------|-------------|-----------|-----------|
| 2026-07-20 | Unauthorized Access | User accessed project they shouldn't | Removed access; reviewed permissions | Quarterly audits; automation monitoring |
| 2026-07-22 | Configuration Change | Workflow changed without approval | Reverted change; documented in log | Enforce change control procedure |

## Evidence Package Assembly

**Prepare for External Audit**:

1. **Access Control Evidence**
   - 6+ months of access logs
   - Monthly audit reports
   - Proof of access removal
   - Role documentation

2. **Change Control Evidence**
   - Change log (all changes)
   - Approval documentation
   - Testing evidence
   - Implementation verification

3. **Automation Evidence**
   - All active rules documented
   - Sample execution logs
   - Audit trail review
   - Maintenance records

4. **Compliance Evidence**
   - Work item samples (10+)
   - Complete lifecycle view
   - Status transitions audited
   - Approval verification

5. **Incident Evidence**
   - Full incident log
   - Investigation documentation
   - Resolution records
   - Prevention measures

## Audit Schedule Calendar

```
MONTHLY (1st Monday)
- Permission Audit (30 min)

QUARTERLY (End of Quarter)
- Comprehensive Audit (2 hours)
- Audit Report Filed

ANNUALLY (December)
- Full Compliance Audit (4-8 hours)
- Annual Report & Remediation Plan
- Evidence Package Updated
```

## Audit Responsibility Matrix

| Task | Monthly | Quarterly | Annual |
|------|---------|-----------|--------|
| Permission Audit | Jira Admin | Jira Admin | Compliance Officer |
| Change Log Review | Project Lead | Jira Admin | Compliance Officer |
| Automation Audit | Automation Owner | Jira Admin | Compliance Officer |
| Incident Review | Security Team | Compliance Officer | Compliance Officer |
| Report Filing | Jira Admin | Compliance Officer | Compliance Officer |

## Next Steps

- [Compliance Framework](./compliance-framework.md) - Complete implementation
- [Best Practices](./best-practices.md) - Reference guide
- [Audit Trails](../governance/audit-trails.md) - What gets logged

---

**Estimated Reading Time**: 10 minutes
