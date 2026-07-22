# Setup Procedures

Complete step-by-step guide for initial Jira project setup.

## Pre-Setup Checklist

Before starting:
- ✅ Chosen project type (Team-managed or Company-managed)
- ✅ Selected template (Scrum, Kanban, or Bug Tracking)
- ✅ Identified team members
- ✅ Documented organizational purpose
- ✅ Reviewed [Project Types](../setup-and-projects/project-types.md)

## Step 1: Create Project

1. Click "Projects" in top navigation
2. Select "Create project"
3. Verify you have project creation permission (ask admin if needed)
4. Choose template:
   - **Scrum**: Time-boxed sprints with planning
   - **Kanban**: Continuous workflow
   - **Bug Tracking**: Issue-focused

5. Select project type:
   - **Team-Managed**: Self-contained team control
   - **Company-Managed**: Standardized across organization

6. Fill in project details:
   - Project name (descriptive, e.g., "Mobile App v2.0")
   - Project key (used in issue IDs, e.g., "MA2")
   - Description (purpose and scope)

7. Click "Create"

## Step 2: Configure Project Settings

After creation:

1. Click "Settings" (bottom of sidebar)
2. Review "General" section for accuracy
3. Document project purpose in description
4. Verify project visibility (who can browse)

## Step 3: Add Team Members

1. Settings → "People"
2. Click "Add people to project"
3. Search for team members
4. Assign roles:
   - **Administrators**: Project leads, managers
   - **Developers**: Team members executing work
   - **Users**: Stakeholders, reporters (limited access)

5. Click "Add"
6. Send notification to team

## Step 4: Configure Workflow (Team-Managed Only)

1. Settings → "Workflows"
2. Review default workflow
3. Customize if needed:
   - Click "Create workflow" to build custom workflow
   - Define statuses (To Do, In Progress, Done, etc.)
   - Create transitions between statuses
   - Test workflow

4. Map to board columns (see Step 5)

## Step 5: Configure Board

1. Navigate to board
2. Click "Board Settings" (top-right)
3. **Columns Tab**:
   - Verify columns match workflow statuses
   - Add/remove columns as needed
   - Reorder columns logically

4. **General Tab**:
   - Set any sprint settings (Scrum)
   - Configure WIP limits (Kanban)

5. Click "Save"

## Step 6: Create Sample Issues

Test your setup:

1. Click "Create" (top navigation)
2. Create sample issue:
   - Type: Story
   - Summary: "Test issue"
   - Assign to yourself
   - Add description
3. Click "Create"

## Step 7: Test Workflow

Verify workflow works:

1. Open created issue
2. Click "Transition" button
3. Move through statuses
4. Verify board updates
5. Add comments
6. Document any issues

## Step 8: Document Setup

Create governance documentation:

```
PROJECT SETUP DOCUMENTATION

Project Name: [Name]
Project Key: [Key]
Created: [Date]
Created By: [Person]
Project Type: [Team-Managed/Company-Managed]
Template: [Scrum/Kanban/Bug Tracking]

Purpose: [Description of project purpose]

Team Members:
- [Name]: [Role]
- [Name]: [Role]

Workflow: [Describe workflow and statuses]

Board Configuration: [Describe columns, swimlanes, WIP limits]

Governance Notes: [Any special configurations]
```

## Step 9: Establish Change Control

Document process going forward:

1. Create "Change Log" document
2. Record all future changes:
   - What changed (field, workflow, etc.)
   - When changed (date)
   - Who approved (if company-managed)
   - Reason for change

3. Store in accessible location

## Step 10: Schedule Review

1. Plan first review in 2 weeks
2. Verify team comfortable with process
3. Address any workflow issues
4. Document findings

## Troubleshooting

**Issue**: Can't create project  
**Solution**: Verify you have project creation permissions (ask admin)

**Issue**: Board columns don't match workflow  
**Solution**: Configure board columns to match workflow statuses in Board Settings

**Issue**: Team members can't create issues  
**Solution**: Verify they're assigned to project with "Developer" or higher role

## Next Steps

- [Permission Management](./permission-management.md) - Configure access control
- [Automation Setup](./automation-setup.md) - Create automation rules
- [Workflow Basics](../work-management/workflow-basics.md) - Advanced workflow configuration

---

**Estimated Time**: 30-45 minutes
