# Project Types & Management Models

## Team-Managed vs. Company-Managed

Jira offers two distinct project management approaches. Choose based on your organizational structure and governance needs.

### Team-Managed Projects

**What It Is**: Self-contained projects with simplified configuration managed by team members without IT involvement.

**Best For**:
- Independent teams not requiring IT oversight
- Small teams wanting autonomy
- Rapid deployment without centralized approval
- Teams with unique workflows

**Characteristics**:
- Independent configuration (doesn't affect other projects)
- Simplified interface and setup
- Team members can manage settings directly
- Limited to project-level features
- No requirement for Jira System Administrators

**Limitations**:
- Cannot share workflows across projects
- Limited advanced features (no Advanced Planning)
- Harder to enforce organizational standards
- Less audit trail control

**Typical Users**: Startup teams, independent departments, internal tool teams

### Company-Managed Projects

**What It Is**: Standardized projects with centralized governance and consistent configuration across the organization.

**Best For**:
- Organizations requiring consistency
- Government and compliance-heavy organizations
- Large multi-team environments
- Organizations needing Advanced Planning
- Regulated industries

**Characteristics**:
- Standardized processes across projects
- Centralized workflow management
- Advanced features available (Advanced Planning, complex reporting)
- Cross-space boards and dependencies
- Jira administrators maintain consistency
- Enhanced audit trail capabilities

**Capabilities**:
- Workflow schemes (apply same workflow to multiple projects)
- Multiple boards per project
- Cross-project dependencies
- Advanced permission schemes
- Detailed compliance reporting

**Typical Users**: Enterprise organizations, government agencies, financial services

## Governance Impact

| Aspect | Team-Managed | Company-Managed |
|--------|--------------|-----------------|
| Governance | Decentralized | Centralized |
| Process Consistency | Team-specific | Organization-wide |
| Audit Control | Basic | Advanced |
| Workflow Reuse | No | Yes |
| Permission Flexibility | Limited | Extensive |
| Admin Overhead | Low | Moderate to High |

## For Government Compliance

**Recommendation**: Use **Company-Managed** projects for government work:
- Better audit trail control
- Centralized permission management
- Enforced workflows for compliance
- Detailed reporting capabilities
- Easier compliance documentation

## Migration Path

Start team-managed for testing, then migrate to company-managed when:
- Multiple teams need consistency
- Compliance becomes requirement
- Organization grows beyond 3-4 teams
- Advanced features needed

Atlassian provides migration tools for this transition.

## Next Steps

- [Space Organization](./space-organization.md) - Organizational structure models
- [Project Creation](./project-creation.md) - How to create your project
- [Permissions](../governance/permissions.md) - Access control implications

---

**Estimated Reading Time**: 8 minutes
