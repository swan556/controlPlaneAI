# Northstar Systems — Product Information

## 1. Northstar Cloud

Northstar Cloud is a managed cloud infrastructure platform.

### Features
- Virtual machines
- Container hosting
- Block storage
- Virtual networking
- Automated backups
- Monitoring
- API access

### Supported Operating Systems
- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12
- Rocky Linux 9

### Limits
- Maximum VM size: 64 vCPU
- Maximum memory per VM: 512 GB
- Maximum storage volume: 16 TB
- Maximum volume size depends on the customer's plan.

### Availability
- US East
- US West
- Europe West
- Asia Pacific

---

## 2. Northstar Edge

Northstar Edge provides infrastructure services closer to customer locations.

### Features
- Edge compute
- Local caching
- Traffic routing
- Regional deployments
- Edge monitoring

### Requirements
- Supported Northstar Edge hardware
- Compatible local network
- Business or Enterprise subscription

### Availability
- North America
- Europe
- Asia Pacific

### Limitations
- Edge deployments are not available in every country.
- Hardware availability varies by region.
- Some advanced routing features require an Enterprise plan.

---

## 3. Northstar Monitor

Northstar Monitor provides monitoring for infrastructure and applications.

### Features
- Infrastructure metrics
- Application metrics
- Log collection
- Custom dashboards
- Alerts
- Webhooks
- Incident notifications

### Supported Notifications
- Email
- Slack
- Microsoft Teams
- Webhooks
- PagerDuty

### Data Retention
- Starter: 7 days
- Business: 30 days
- Enterprise: Custom

### Advanced Features
- Custom alert rules require Business or Enterprise.
- Advanced dashboards require Business or Enterprise.
- Custom retention is available to Enterprise customers.

---

## 4. Northstar API

Northstar API provides programmatic access to supported Northstar services.

### Features
- REST API
- API keys
- OAuth authentication
- Webhooks
- Resource management
- Usage monitoring

### Rate Limits
- Starter: 60 requests/minute
- Business: 300 requests/minute
- Enterprise: Custom

### API Responses
- `200` — Request successful
- `400` — Invalid request
- `401` — Authentication required
- `403` — Insufficient permissions
- `404` — Resource not found
- `429` — Rate limit exceeded
- `500` — Internal server error

### API Versions
- Current version: v2
- Previous versions remain supported for 12 months after deprecation.
- Deprecated versions do not receive new features.

---

## 5. Northstar Backup

Northstar Backup provides automated backups for supported Northstar Cloud resources.

### Features
- Automated backups
- Encrypted storage
- Scheduled backups
- Point-in-time restoration
- Backup restoration

### Retention
- Starter: Not included
- Business: 30 days
- Enterprise: Custom

### Restoration
- Business customers can request restoration from available backups.
- Enterprise customers can configure custom restoration requirements.
- Restoration time depends on data size and system availability.

---

## 6. Northstar Secure Gateway

Northstar Secure Gateway provides network security and access-control features.

### Features
- Traffic filtering
- IP allowlisting
- Access policies
- TLS termination
- Network logging
- Private connectivity

### Availability
- Business: Core gateway features
- Enterprise: Full gateway features

### Enterprise Features
- Advanced access policies
- Custom network rules
- Private connectivity
- Dedicated configuration support

---

## 7. Product Integrations

Northstar supports integrations with:

- AWS
- Microsoft Azure
- Google Cloud
- GitHub
- GitLab
- Slack
- Microsoft Teams
- Datadog
- PagerDuty
- Terraform
- Kubernetes

### Integration Requirements
- Some integrations require administrator permissions.
- Some integrations are available only on Business or Enterprise plans.
- Unsupported third-party integrations are not guaranteed to work.

---

## 8. Kubernetes Support

Northstar Cloud supports Kubernetes workloads.

### Supported Versions
- Kubernetes 1.29
- Kubernetes 1.30
- Kubernetes 1.31
- Kubernetes 1.32

### Features
- Cluster deployment
- Container workloads
- Persistent storage
- Network configuration
- Monitoring

### Requirements
- Business or Enterprise plan
- Supported Kubernetes version
- Compatible Northstar Cloud resources

---

## 9. Product Compatibility

### Browsers
- Google Chrome
- Mozilla Firefox
- Microsoft Edge
- Safari

### Operating Systems
- Windows 11
- macOS 13 or later
- Ubuntu 22.04 or later
- Debian 12 or later

### Mobile
- iOS 16 or later
- Android 13 or later

---

## 10. Product Availability by Plan

| Feature | Starter | Business | Enterprise |
|---|---|---|---|
| Northstar Cloud | Yes | Yes | Yes |
| Northstar Edge | No | Yes | Yes |
| Northstar Monitor | Basic | Advanced | Advanced |
| Northstar API | Yes | Yes | Yes |
| Northstar Backup | No | Yes | Yes |
| Secure Gateway | Basic | Yes | Advanced |
| SSO | No | No | Yes |
| Custom Roles | No | No | Yes |
| Dedicated Support | No | No | Yes |
| Custom API Limits | No | No | Yes |
| Custom Data Retention | No | No | Yes |

---

## 11. Product Updates

- Northstar releases product updates continuously.
- Major releases are announced through the customer dashboard.
- New features may initially be available only to selected plans.
- Deprecated features receive advance notice.
- Customers are responsible for migrating away from deprecated APIs before their removal date.

---

## 12. Product Limitations

- Product availability varies by region.
- Features may differ between subscription plans.
- Enterprise customers may have custom limits defined in their contracts.
- Northstar does not guarantee compatibility with unsupported software or hardware.
- Service availability depends on the applicable product and subscription agreement.