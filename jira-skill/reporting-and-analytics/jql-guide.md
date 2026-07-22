# JQL Reference Guide

## What Is JQL?

JQL (Jira Query Language) is "a sophisticated, structured search language" for building complex queries to search work items within and across projects.

Queries can be saved as filters and applied throughout Jira (boards, dashboards, reports).

## Basic Structure

Every JQL query has four components:

```
FIELD OPERATOR VALUE [KEYWORDS]
```

**Example**: `priority = High AND status = "In Progress"`

## Core Components

### Field
Represents different types of information

**Examples**:
- `priority` - Urgency level
- `status` - Current workflow stage
- `assignee` - Responsible person
- `created` - Creation date
- `duedate` - Due date
- `issuetype` - Type (Bug, Story, Task)
- `project` - Project name
- `fixVersion` - Target version

### Operator
Relationship between field and value

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Equals | `status = "Done"` |
| `!=` | Not equal | `status != "Done"` |
| `<` | Less than | `duedate < now()` |
| `>` | Greater than | `created > -7d` |
| `IN` | In list | `priority IN (High, Critical)` |
| `NOT IN` | Not in list | `assignee NOT IN (john, mary)` |
| `~` | Contains | `summary ~ "bug"` |
| `!~` | Not contains | `description !~ "duplicate"` |

### Value
The data being searched

**Types**:
- Text: `"Customer Portal"` (quotes for phrases)
- Numbers: `10`, `100`
- Dates: `2026-07-22` or relative `-7d` (7 days ago)
- Keywords: `currentUser()`, `now()`

### Keywords
Combine multiple conditions

- `AND` - Both conditions required (restrictive)
- `OR` - Either condition sufficient (inclusive)
- `NOT` - Excludes criteria

## Practical Examples

### High Priority Personal Work
```
priority = High AND assignee = currentUser()
```

### Overdue Items
```
project = "Support" AND duedate < now() AND status != Closed
```

### Recent Changes (Last 7 Days)
```
created >= -7d ORDER BY created DESC
```

### Bugs by Component
```
component IN ("Backend", "API") AND issuetype = Bug
```

### Issues Assigned to Team
```
assignee IN MEMBERSOF("developers")
```

## Advanced Queries

### Historical Search (Was Status)
```
status WAS "In Progress" AND status = "Done"
```
Finds items that were previously in "In Progress" and now are "Done"

### Change Tracking (Changed)
```
status CHANGED AFTER -1w
```
Items that changed status in last week

### Custom Fields
```
"Compliance Status" = "Approved"
```

### Nesting & Complex Logic
```
(assignee = currentUser() OR assignee = EMPTY) 
AND priority > Low 
AND status NOT IN ("Closed", "Duplicate")
```

## Audit-Relevant Queries

### Compliance Item Tracking
```
project = "Compliance" AND "Approval Status" = "Pending" 
ORDER BY created ASC
```

### Change Tracking
```
updated >= -7d AND status = "Done" 
ORDER BY updated DESC
```

### Access Violations
```
creator = user1 AND created >= -90d 
AND "Sensitivity" = "Restricted"
```

### Segregation of Duties
```
assignee = "approver" AND type = "Approval" 
AND status = "In Review"
```

## Saving Filters

1. Build query and verify results
2. Click "Save filter"
3. Name descriptively (for reuse)
4. Set sharing (private or shared)
5. Add description
6. Save

**Benefit**: Reuse filters in dashboards, reports, and board filters

## Search Options in Jira

1. **Quick Search** - Simple text (top bar)
2. **Basic Search** - Graphical interface (Projects → Filters)
3. **Advanced Search (JQL)** - This guide (Projects → Advanced)

## Next Steps

- [Dashboards](./dashboards.md) - Use filters in dashboards
- [Reports](./reports.md) - Filter reports with JQL
- [Compliance](../compliance/compliance-framework.md) - Audit queries

---

**Estimated Reading Time**: 12 minutes
