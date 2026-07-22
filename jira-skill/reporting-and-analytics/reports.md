# Reports Guide

## Four Report Categories

### 1. Agile Reports
**Purpose**: "Understand your team's velocity, spot bottlenecks, and better predict future performance"

**Key Metrics**:
- **Velocity**: Completed work per sprint
- **Burndown**: Work remaining vs. time
- **Sprint Progress**: Completion percentage by status
- **Cumulative Flow**: Work progression over time

**Audience**: Scrum teams, project managers  
**Audit Value**: Delivery performance evidence

### 2. DevOps Reports
**Purpose**: "Understand deployment pipeline and frequency to enable greater collaboration"

**Key Metrics**:
- **Deployment Frequency**: How often deployed
- **Build Success**: Pipeline reliability
- **Lead Time**: Time from commit to deployment
- **Pipeline Stage Completion**: Progress through stages

**Audience**: DevOps, engineering managers  
**Audit Value**: Release management tracking

### 3. Issue Analysis Reports
**Purpose**: Track work types and team capacity vs. workload

**Key Metrics**:
- **Issues by Status**: Distribution across workflow
- **Issues by Priority**: Urgency distribution
- **Issues by Assignee**: Workload distribution
- **Work Type Distribution**: Bug vs. feature mix

**Audience**: Project managers, team leads  
**Audit Value**: Workload distribution tracking

### 4. Forecast & Management Reports
**Purpose**: Evaluate team capacity and forecast future performance

**Key Metrics**:
- **Capacity Forecasts**: Predicted team capacity
- **Velocity Trends**: Historical velocity patterns
- **Timeline Predictions**: Expected completion dates
- **Resource Allocation**: Team member assignments

**Audience**: Program managers, executives  
**Audit Value**: Capacity planning evidence

## Running Reports

**Steps**:
1. Navigate to desired project
2. Select "Reports" tab
3. Choose report type
4. Configure parameters:
   - Project/space selection
   - Time period
   - Metrics to display
5. Apply filters if needed
6. Export (if needed)

## Report Customization

- **Time Period**: Last sprint, last quarter, custom date range
- **Projects**: Single or multiple projects
- **Filters**: Use JQL to filter issues
- **Metrics**: Select which data to display

## Report Export

**Formats**: PDF, PNG (static), CSV (data)

**Use Cases**:
- Presentations
- Stakeholder updates
- Archive for audit
- Further analysis

## Compliance-Focused Reports

### Change Management Report
**Purpose**: Track all changes by date range

**Procedure**:
1. Use Issue Analysis report
2. Filter by custom "ChangeRequest" field
3. Time period: Current month
4. Group by: Status and Priority
5. Export for change control log

### Work Item Completion Report
**Purpose**: Track completion rates and delays

**Procedure**:
1. Use Forecast report
2. Filter by project
3. Show: Completion dates vs. due dates
4. Identify overdue items
5. Export for compliance review

### Resource Allocation Report
**Purpose**: Track team member workload

**Procedure**:
1. Use Issue Analysis report
2. Filter by assignee
3. Group by: Priority
4. Show: Open items per person
5. Identify overloaded team members

## Report Best Practices

1. **Regular Export**: Run compliance reports monthly
2. **Baseline**: Compare against historical trends
3. **Documentation**: Record report purpose and findings
4. **Stakeholder Access**: Share relevant reports with teams
5. **Archival**: Archive monthly reports for audit

## Next Steps

- [Insights](./insights.md) - AI-powered analytics
- [JQL Reference](./jql-guide.md) - Advanced filtering
- [Dashboards](./dashboards.md) - Real-time views

---

**Estimated Reading Time**: 10 minutes
