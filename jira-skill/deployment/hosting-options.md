# Hosting Options

## Two Primary Hosting Solutions

Atlassian offers two hosting approaches with distinct governance and operational implications.

## Cloud Hosting (Atlassian-Managed)

**What**: Atlassian manages infrastructure and deployment

**Characteristics**:
- "Generally the best option for teams who want to get started quickly and easily"
- For teams "who don't want to manage the technical complexity of hosting themselves"

### Advantages
- Minimal operational overhead
- Automatic updates and maintenance
- Immediate deployment (no waiting for infrastructure)
- Managed security and compliance
- Predictable costs
- Automatic backups

### Suitability
- Small to mid-sized teams
- Organizations with limited IT infrastructure
- Rapid deployment requirements
- Managed security preference

### Compliance
- Atlassian manages compliance
- Verify Atlassian's compliance certifications (SOC 2, FedRAMP if applicable)
- Understand data residency policies
- Dependent on Atlassian's security posture

## Data Center Hosting (Self-Managed)

**What**: Organizations retain complete infrastructure control

**Deployment Options**:
- On-premises (your hardware)
- AWS (Amazon Web Services)
- Azure (Microsoft Azure)
- Other cloud providers

**Characteristics**:
- "Generally the best option for enterprise teams who need uninterrupted access to Jira and performance at scale"

### Advantages
- Complete infrastructure control
- Customization capabilities
- Data sovereignty (on-premises)
- Compliance with strict data requirements
- No cloud dependency
- Performance optimization for scale

### Operational Requirements
- IT infrastructure management
- Security patch management
- Backup and disaster recovery
- Uptime monitoring
- Capacity planning

### Suitability
- Enterprise organizations
- High-availability requirements
- Strict data residency requirements (on-premises)
- Complex compliance requirements
- Significant customization needs

### Compliance
- Organizations manage compliance
- Full control over data protection
- On-premises option for sensitive data
- Compliance aligned with organizational policies

## Hosting Comparison Matrix

| Factor | Cloud | Data Center |
|--------|-------|------------|
| Setup Time | Days | Weeks to months |
| Operational Overhead | Minimal | High |
| Customization | Standard | Extensive |
| Cost Model | Per-user predictable | Infrastructure-dependent |
| Control | Managed by Atlassian | Full organizational control |
| Compliance | Atlassian-managed | Organization-managed |
| Scalability | Automatic | Manual |
| Updates | Automatic | Manual |
| Data Residency | Atlassian-controlled | Controllable (on-prem) |
| Audit Trail | Atlassian-provided | Organization-managed |

## Government Audit Implications

### Cloud Deployment
- ✅ Simpler compliance (Atlassian handles)
- ❌ Dependent on vendor compliance
- ⚠️ Verify FedRAMP status if required

### Data Center Deployment
- ✅ Complete organizational control
- ✅ On-premises option for sensitive data
- ⚠️ Higher operational burden
- ⚠️ Compliance is organization's responsibility

## Migration Between Hosting Models

**Cloud → Data Center**: Possible with migration tools; consider business justification

**Data Center → Cloud**: Possible; verify compliance implications before migration

## Recommendation for Government

**Small/Mid Deployments**: Cloud with verified Atlassian compliance certifications

**Large Deployments**: Data Center on-premises for maximum compliance control

**Sensitive Data**: Data Center on-premises for data sovereignty

## Next Steps

- [Infrastructure Guide](./infrastructure.md) - Architecture decisions
- [Compliance Framework](../compliance/compliance-framework.md) - Governance

---

**Estimated Reading Time**: 10 minutes
