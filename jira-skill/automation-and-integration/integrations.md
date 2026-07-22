# Integrations Guide

## What Are Integrations?

Integrations are "installable components that supplement or enhance the functionality of your instance."

Jira supports **3,000+ apps** through Atlassian Marketplace, reducing tool fragmentation and improving team efficiency.

## Key Statistics

- **Typical developer workflow**: Checks 3.3 tools to learn project status
- **Jira customer workflow**: Checks 2.3 tools (40% fewer)
- **Confluence integration benefit**: 76% of customers report faster shipping

## Popular Integration Categories

### Design Tools
- Figma, Adobe XD, Invision, Draw.io, Balsamiq, Lucidchart, Miro

### DevOps & CI/CD
- Jenkins, GitHub, GitLab, Bitbucket Cloud, CircleCI, Dynatrace, Opsgenie

### Communication
- Slack, Microsoft Teams, Zoom, Gmail, Outlook, Zendesk

### Collaboration & Documentation
- Confluence, Trello, Google Sheets, Google Docs

## Atlassian Marketplace

**Purpose**: Central hub for discovering and installing apps

**Features**:
- Browse 3,000+ applications
- Read reviews and ratings
- Filter by category (top-rated, trending)
- Easy one-click installation
- Many apps free; some have commercial licenses

**Access**: Settings → Apps

## Integration Installation Procedure

1. Navigate to Atlassian Marketplace
2. Search for desired app
3. Review app documentation
4. Check permissions required
5. Click "Install"
6. Grant necessary permissions
7. Configure app settings (API keys, authentication)
8. Test functionality

## Governance Considerations

### Before Installation

**Vet the App**:
- ✅ What permissions does it request?
- ✅ What data does it access?
- ✅ Is it from trusted vendor?
- ✅ Are there alternatives?
- ✅ Cost considerations?

**Review Permissions**:
- Read access only? Or write/delete?
- Which data does it access?
- Can it access sensitive work items?

### After Installation

- ✅ Test functionality with sample data
- ✅ Document app purpose and configuration
- ✅ Restrict access if needed
- ✅ Regular security review
- ✅ Remove unused apps

## Critical Integration: Confluence

**Definition**: Atlassian's documentation platform

**Integration Benefits**:
- Link issues to documentation pages
- Embed issue information in Confluence
- Cross-link work and documentation
- Unified knowledge base

**Benefit Evidence**: 76% of Jira customers shipping faster after integration

**Use**: Ideal for organizations requiring comprehensive documentation and compliance

## Governance Best Practices

**Documentation**:
- List all installed apps
- Document app purpose
- Record configuration details
- Note permissions granted

**Security**:
- Review app permissions quarterly
- Disable apps no longer used
- Monitor for suspicious activity
- Update app configuration as needed

**Compliance**:
- Verify app complies with data governance
- Check data residency if required
- Audit app access patterns
- Document app in compliance framework

## Integration Audit Procedure

**Quarterly Review**:
1. List all installed apps
2. For each app:
   - Verify still needed
   - Review permissions
   - Check recent usage
   - Confirm documentation current
3. Disable unused apps
4. Update configuration if needed
5. Document findings

## Common Integration Scenarios

**Scenario 1**: Connect Slack for notifications
- App: Slack integration
- Benefit: Real-time team alerts
- Configuration: Channel routing, event types

**Scenario 2**: GitHub integration for developers
- App: GitHub integration
- Benefit: Link PRs to issues, automation
- Configuration: Repository mapping

**Scenario 3**: Confluence integration for documentation
- App: Confluence integration
- Benefit: Unified knowledge base
- Configuration: Page linking, embeds

## Next Steps

- [Marketplace Overview](./marketplace.md) - App discovery
- [Integration Setup](../procedures/automation-setup.md) - Implementation
- [Compliance](../compliance/compliance-framework.md) - Governance

---

**Estimated Reading Time**: 10 minutes
