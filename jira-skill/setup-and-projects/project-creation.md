# Project Creation Steps

## Pre-Creation Checklist

Before creating a project, verify:

- ✅ You have project creation permissions (ask Jira admin if unsure)
- ✅ Chosen your project type (Team-managed or Company-managed)
- ✅ Selected template (Scrum, Kanban, or Bug Tracking)
- ✅ Documented project purpose and organizational alignment
- ✅ Identified initial team members

## Step-by-Step Project Creation

### Step 1: Navigate to Project Creation
1. Click "Projects" in top navigation
2. Select "Create project"
3. If you don't see this option, you lack project creation permissions

### Step 2: Choose Template

**Three Template Options**:

**Scrum Template**
- Purpose: Time-boxed sprints with planning and velocity tracking
- Best for: Development teams, iterative work
- Includes: Sprint management, backlog, velocity charts, burndown

**Kanban Template**
- Purpose: Continuous workflow without time-boxing
- Best for: Support, operations, continuous delivery
- Includes: Flow visualization, WIP limits, throughput metrics

**Bug Tracking Template**
- Purpose: List-focused issue tracking
- Best for: QA teams, support, defect management
- Includes: Issue-centric views, tracking-focused interface

### Step 3: Select Space Type

**Team-Managed**:
- Self-contained team control
- No IT approval required
- Simplified configuration
- Click if team wants autonomy

**Company-Managed**:
- Standardized across organization
- IT/Admin oversight
- Advanced features available
- Click if organization requires consistency

### Step 4: Configure Project Details

Fill in:
- **Project name**: Descriptive, unique (e.g., "Mobile App v2.0")
- **Project key**: Used in issue identifiers (e.g., MA2 = "MA2-123")
- **Project description**: Purpose and scope
- **Project category**: Optional organizational grouping

### Step 5: Initial Configuration (Post-Creation)

After creation, configure:

1. **Team Members** (Settings → People)
   - Add team members
   - Assign roles (Administrators, Developers, Users)

2. **Workflows** (Settings → Workflows)
   - Review default workflow
   - Customize statuses and transitions if needed

3. **Board Configuration** (Board → Board Settings)
   - Adjust columns to match workflow
   - Configure swimlanes if needed
   - Set WIP limits (Kanban only)

4. **Work Item Fields** (Settings → Fields)
   - Add custom fields for compliance tracking
   - Configure required fields

## Post-Creation Governance Steps

### For Company-Managed Projects

1. **Document Project Purpose**
   - Create governance documentation
   - Define workflow rationale
   - Establish permission policies

2. **Test Workflow**
   - Create sample issues
   - Test status transitions
   - Verify board representation

3. **Permission Audit**
   - Verify only appropriate users have access
   - Document permission rationale
   - Establish regular review cycle

### For Team-Managed Projects

1. **Establish Team Standards**
   - Document workflow expectations
   - Define "Definition of Done"
   - Set field completion standards

2. **Configure Notifications**
   - Set up email notifications
   - Configure Slack/Teams integration if applicable
   - Establish communication norms

## Common Configuration Issues

**Issue**: Board doesn't match workflow  
**Solution**: Configure board columns to reflect workflow statuses

**Issue**: Can't create issues  
**Solution**: Verify you're assigned to project with appropriate role

**Issue**: Missing fields**  
**Solution**: Add custom fields in project settings

## Next Steps

- [Work Items Guide](../work-management/work-items.md) - Start creating work
- [Board Types](../work-management/board-types.md) - Configure your board
- [Setup Procedures](../procedures/setup-procedures.md) - Detailed admin setup

## Checklist for Audit Readiness

- ✅ Project documented and named appropriately
- ✅ Team members assigned with clear roles
- ✅ Workflow established and tested
- ✅ Permissions configured and audited
- ✅ Initial configuration completed
- ✅ Governance documentation created

---

**Estimated Reading Time**: 8 minutes
