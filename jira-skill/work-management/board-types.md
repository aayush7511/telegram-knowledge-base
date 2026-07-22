# Board Types & Configuration

## What Are Boards?

A board "accompanies each Jira space by default and provides the team with a shared view of all work that hasn't started, work that is in progress, and work that is completed." Boards visualize workflow and enable team collaboration.

## Scrum Board

**Best For**: Teams working in time-boxed sprints with planning and estimation

**Key Features**:
- Sprint management (create and plan sprints)
- Backlog organization (prioritize future work)
- Velocity tracking (measure team capacity)
- Burndown charts (track sprint progress)
- Estimation (story points)

**Typical Workflow**:
```
Backlog | To Do | In Progress | In Review | Done
```

**Team Ceremonies**:
- **Sprint Planning**: Select backlog items for sprint
- **Daily Standup**: Review board progress
- **Sprint Review**: Demonstrate completed work
- **Retrospective**: Reflect on process improvements

**Audit Value**: Sprint commitment and velocity evidence

**When to Use**:
- Software development teams
- Predictable iterative work
- Team wants time-boxed planning

## Kanban Board

**Best For**: Teams working in continuous flow without time-boxing

**Key Features**:
- Work-in-progress (WIP) limits (prevent overload)
- Continuous flow visualization
- Bottleneck identification
- Throughput metrics
- Pull-based workflow

**Typical Workflow**:
```
Backlog | To Do | In Progress | Testing | Done
(WIP Limit)     (WIP Limit)   (WIP Limit)
```

**Continuous Practices**:
- Pull work when ready
- Limit WIP at each stage
- Monitor flow efficiency
- Identify and remove bottlenecks

**Audit Value**: Work throughput and flow analysis

**When to Use**:
- Support/operations teams
- Continuous delivery teams
- Unpredictable work volume
- Focus on flow efficiency

## Board Customization

### Columns
- Represent workflow statuses
- Drag-and-drop work items between columns
- Multiple statuses can map to one column (for complex workflows)

### Swimlanes
**Purpose**: Categorize work horizontally

**Options**:
- **By Assignee**: Group by team member
- **By Workstream**: Group by feature or initiative
- **By Application Area**: Group by technical component

**Example**: Frontend, Backend, Database swimlanes for software team

### WIP Limits (Kanban)
- Set maximum items per column
- Prevents bottlenecks
- Visual indicator when exceeded
- Forces prioritization

**Example**:
- In Progress: WIP limit 5 (max 5 items)
- When 5 items exist, can't add more until one completes

## Multiple Boards (Company-Managed)

**Capability**: Create multiple boards within one project

**Use Cases**:
- Different teams need different views
- One project has distinct workstreams
- Need team-specific and executive dashboards

**Example**: "Frontend Board" and "Backend Board" for same project

## Cross-Space Boards (Company-Managed)

**Capability**: Aggregate items from multiple projects

**Use Cases**:
- Executive visibility across teams
- Program-level coordination
- Cross-team dependency tracking

**Example**: "Quarterly Release Board" combining Mobile + Web + Backend projects

## Board Configuration Best Practices

1. **Match Workflow**: Columns should align with workflow statuses
2. **Clear Naming**: Use understandable column names
3. **Appropriate WIP**: Set realistic WIP limits (Kanban)
4. **Swimlanes**: Use when team has distinct workstreams
5. **Regular Review**: Update board configuration as process evolves

## Daily Board Operations

**Typical Daily Activities**:
1. Stand up team around board
2. Review items in "In Progress"
3. Identify any blocked items
4. Move completed items to "Done"
5. Pull new items into "In Progress"

## Audit-Relevant Board Information

✅ Board layout documents workflow visualization  
✅ WIP limits enforce process discipline  
✅ Swimlanes organize related work  
✅ Completed items visible for tracking  
✅ Board history available for review  

## Next Steps

- [Workflow Basics](./workflow-basics.md) - Understand workflow structure
- [Automation Rules](../automation-and-integration/automation-rules.md) - Automate board transitions
- [Insights & Analytics](../reporting-and-analytics/insights.md) - Measure board performance

---

**Estimated Reading Time**: 10 minutes
