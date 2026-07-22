# Dashboards Setup

## What Are Dashboards?

Dashboards are customizable "information hubs containing gadgets that display real-time data."

## Key Features

**Scope**: Single or multiple projects  
**Sharing**: Public (shared) or private (personal only)  
**Gadgets**: Pre-built data displays (reports, charts, metrics)  
**Customization**: Arrange gadgets and layout  
**Access**: Top navigation menu or personalized default  

## Dashboard Creation Steps

### Step 1: Navigate
1. Click "Dashboards" in top navigation
2. Select "Create dashboard"

### Step 2: Configure Properties
- Dashboard name (descriptive)
- Description (purpose)
- Visibility (Private or Shared)

### Step 3: Add Gadgets
1. Click "Add gadget"
2. Browse available gadgets
3. Select desired gadget
4. Configure gadget settings:
   - Project/filter selection
   - Metrics to display
   - Time period
5. Save gadget

### Step 4: Arrange Layout
1. Drag gadgets to desired positions
2. Resize gadgets
3. Organize by importance
4. Save dashboard layout

### Step 5: Share (If Public)
1. Click "Share"
2. Select users/groups to share with
3. Set read-only if needed
4. Save sharing settings

## Common Gadgets

- **Burndown**: Sprint progress
- **Velocity**: Historical sprint metrics
- **Issue Statistics**: Count by type/status
- **Assigned to Me**: Personal work items
- **Activity Stream**: Recent changes
- **Custom Filter**: JQL-based results
- **Project Health**: Status overview

## Dashboard Examples

### Executive Dashboard
**Purpose**: High-level organizational view

**Gadgets**:
- Project health across all teams
- Burndown by team
- Velocity trends
- Key metrics (on-time delivery, quality)

### Team Dashboard
**Purpose**: Daily team standup

**Gadgets**:
- Current sprint burndown
- Issues by status
- Blocked items
- Team velocity

### Compliance Dashboard
**Purpose**: Audit readiness

**Gadgets**:
- Recent workflow changes
- User access changes
- Automation rule status
- Open audit items

### Release Dashboard
**Purpose**: Release coordination

**Gadgets**:
- Release timeline
- Completion percentage
- Dependency status
- Risk items

## Dashboard Best Practices

1. **Clear Purpose**: Each dashboard serves specific audience
2. **Relevant Metrics**: Only show data supporting decisions
3. **Real-Time Data**: Use live gadgets not static reports
4. **Limited Gadgets**: 5-8 gadgets per dashboard (not cluttered)
5. **Consistent Layout**: Organize logically
6. **Regular Review**: Update gadgets as needs change

## System Dashboard (Default)

Administrators can customize system-wide default dashboard:

1. Settings → Dashboards → System Dashboard
2. Configure default gadgets
3. Set layout for new users
4. This appears when users first log in

## Sharing Strategy

**Private Dashboards**: Personal use, sensitive data

**Shared Dashboards**:
- Team dashboards (share with team)
- Executive dashboards (share with leadership)
- Compliance dashboards (share with audit team)

**Access Control**: Shared dashboards respect item-level permissions (users only see items they can access)

## Governance Applications

**Compliance Audit Dashboard**:
- Workflow changes (last 30 days)
- User access modifications
- Automation rule executions
- Open audit findings

**Access Control Dashboard**:
- Users by role
- Recent access grants/removals
- Role assignments by project

## Next Steps

- [Reports](./reports.md) - Aggregated metrics
- [Insights](./insights.md) - AI-powered analysis
- [Dashboard Creation Procedure](../procedures/dashboard-creation.md) - Detailed steps

---

**Estimated Reading Time**: 10 minutes
