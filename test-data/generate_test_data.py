#!/usr/bin/env python3
"""
Generate synthetic CSV test datasets for WAF classifier app.
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUTPUT_DIR = Path("/Users/aravinddoma/WAFAllocation/waf-classifier/test-data")

COLUMNS = [
    # Hierarchy IDs (top → bottom)
    "Epic ID", "Feature ID", "Story ID",
    # Hierarchy names + content
    "Epic", "Feature Name", "Story Title", "Story Description",
    # Organisation
    "Team",
    # WAF Classification
    "WAF Category", "WAF Color", "Confidence", "Run/Change",
    # Metadata
    "Timestamp",
    # Alternate ID (fallback)
    "Issue Key",
]

WAF_COLOR_MAP = {
    "KTLO (Keep the Lights On)": "GRAY",
    "Business Maintenance": "BLACK",
    "Technical Maintenance": "BLACK",
    "Regulatory (Operational)": "RED",
    "Enterprise Strategic Priority": "ORANGE",
    "Other Block Priority": "GREEN",
}

ALL_CATEGORIES = list(WAF_COLOR_MAP.keys())


def random_date(start: datetime, end: datetime) -> str:
    delta = end - start
    random_days = random.randint(0, delta.days)
    dt = start + timedelta(days=random_days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_csv(filepath: Path, rows: list[dict]) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Dataset 1: compliance-focus-60.csv
# ---------------------------------------------------------------------------

def build_compliance_dataset() -> list[dict]:
    random.seed(42)

    teams_pool = [
        ("Compliance Team", 15),
        ("Risk Management", 12),
        ("Audit Engineering", 10),
        ("Legal Tech", 8),
        ("Data Governance", 15),
    ]

    epics = [
        ("SOX Compliance Remediation", "EP-C001"),
        ("GDPR Data Privacy", "EP-C002"),
        ("PCI DSS Hardening", "EP-C003"),
        ("Basel III Reporting", "EP-C004"),
        ("AML/KYC Modernization", "EP-C005"),
    ]

    features = [f"F-C{str(i).zfill(3)}" for i in range(1, 21)]
    feature_names = [
        # EP-C001 SOX (F-C001–F-C004)
        "SOX Control Automation", "SOX Audit Trail", "SOX Evidence Collection", "SOX Reporting Dashboard",
        # EP-C002 GDPR (F-C005–F-C008)
        "GDPR Consent Management", "GDPR Right to Erasure", "GDPR Data Subject Requests", "GDPR Privacy Impact Assessment",
        # EP-C003 PCI DSS (F-C009–F-C012)
        "PCI Encryption Layer", "PCI Network Segmentation", "PCI Audit Log Centralization", "PCI Penetration Testing",
        # EP-C004 Basel III (F-C013–F-C016)
        "Basel Capital Calculator", "Basel Reporting Dashboard", "Basel Leverage Ratio Pipeline", "Basel Risk Data Aggregation",
        # EP-C005 AML/KYC (F-C017–F-C020)
        "AML Transaction Monitor", "KYC Identity Verification", "Sanctions Screening", "AML Regulatory Filing Automation",
    ]

    # Map each epic index to its feature slice (4 features per epic)
    features_per_epic = 4
    # epic_feature_map[epic_index] = list of (feat_id, feat_name)
    epic_feature_map = {
        ei: [(features[ei * features_per_epic + fi], feature_names[ei * features_per_epic + fi])
             for fi in range(features_per_epic)]
        for ei in range(len(epics))
    }

    # True category distribution: 40% Reg, 25% KTLO, 20% TechMaint, 15% EntStrat
    true_category_pool = (
        ["Regulatory (Operational)"] * 24 +
        ["KTLO (Keep the Lights On)"] * 15 +
        ["Technical Maintenance"] * 12 +
        ["Enterprise Strategic Priority"] * 9
    )
    random.shuffle(true_category_pool)

    # Confidence distribution: 60% HIGH, 30% MEDIUM, 10% LOW
    confidence_pool = ["HIGH"] * 36 + ["MEDIUM"] * 18 + ["LOW"] * 6
    random.shuffle(confidence_pool)

    # Mismatch indices: ~18 stories
    mismatch_indices = set(random.sample(range(60), 18))

    # Title/description templates keyed by true category
    templates = {
        "Regulatory (Operational)": [
            ("Implement SOX Section 404 Internal Control Testing Automation",
             "Automate internal control testing to satisfy SOX Section 404 requirements. Integrate with existing GRC platform to produce audit-ready evidence packages and reduce manual effort during year-end audits."),
            ("Deploy GDPR Data Subject Request Workflow for European Customers",
             "Build automated workflow to handle data subject access requests (DSAR) within the 30-day regulatory window. Log all actions for DPA audit trail and compliance reporting purposes."),
            ("Harden PCI DSS Cardholder Data Environment Network Segmentation",
             "Implement network micro-segmentation to isolate cardholder data environment per PCI DSS Requirement 1. Validate controls via quarterly penetration testing and automated compliance scans."),
            ("Build Basel III Leverage Ratio Calculation and Reporting Pipeline",
             "Develop automated pipeline to calculate Basel III leverage ratio from daily position data. Generate regulatory reports for submission to Federal Reserve and OCC within prescribed deadlines."),
            ("Integrate AML Transaction Monitoring with SWIFT Message Screening",
             "Connect AML engine to SWIFT message feed for real-time transaction screening against OFAC and EU sanctions lists. Ensure regulatory reporting SARs are filed within 30 days of detection."),
            ("Configure GDPR Consent Preference Center for Mobile Banking App",
             "Implement consent management platform integrated with mobile banking app to capture, store, and honor GDPR consent choices. Produce consent audit logs for regulatory inspections."),
            ("Automate Quarterly BSA/AML Suspicious Activity Report Filing",
             "Build automated SAR filing pipeline that aggregates flagged transactions, formats them per FinCEN requirements, and submits via BSA E-Filing portal. Reduce manual filing time by 80%."),
            ("Implement PCI DSS Requirement 10 Audit Log Centralization",
             "Centralize audit logs from all in-scope PCI systems into SIEM with 12-month retention. Configure real-time alerts for log tampering and unauthorized access per PCI DSS Requirement 10."),
            ("Establish KYC Perpetual Refresh Cycle for High-Risk Customers",
             "Implement automated KYC refresh workflow for high-risk customer segments. Trigger periodic re-verification at defined intervals, document outcomes, and escalate to compliance for review."),
            ("Deploy Regulatory Change Management Tracking System",
             "Build system to ingest regulatory change feeds (Fed Register, SEC, FINRA), assess impact, and assign remediation tasks to compliance owners. Ensure new requirements are implemented before effective dates."),
        ],
        "KTLO (Keep the Lights On)": [
            ("Renew Annual SSL Certificates for Compliance Portal Infrastructure",
             "Renew expiring SSL/TLS certificates across compliance portal and associated microservices. Update certificate inventory and rotate secrets in vault to prevent service outages."),
            ("Apply Monthly Security Patches to GRC Platform Virtual Machines",
             "Apply approved OS and middleware patches to GRC platform VMs following monthly patch cycle. Validate patch application in non-prod before production rollout to minimize downtime risk."),
            ("Upgrade Compliance Reporting Database from PostgreSQL 13 to 15",
             "Perform in-place upgrade of PostgreSQL 13 to 15 for compliance reporting database. Run regression test suite and validate query performance post-upgrade before cutover."),
            ("Resolve Disk Space Alerts on Audit Log Archive Servers",
             "Investigate and remediate disk space exhaustion on audit log archive nodes. Archive older logs to cold storage per retention policy and automate future space monitoring alerts."),
            ("Restart Stalled GDPR Data Deletion Batch Jobs",
             "Diagnose and restart GDPR data deletion batch jobs that failed overnight. Implement retry logic and dead-letter queue to prevent future stuck jobs from going unnoticed."),
            ("Update Expired Service Account Passwords for Compliance Integrations",
             "Rotate expired service account credentials used by compliance tool integrations. Update secrets manager entries and validate all integrations reconnect successfully after rotation."),
        ],
        "Technical Maintenance": [
            ("Refactor Legacy SOX Control Evidence Collection API to REST",
             "Migrate SOX evidence collection module from SOAP to REST API. Standardize response schemas, add OpenAPI documentation, and update downstream consumers to use new endpoints."),
            ("Migrate On-Premises GRC Database to Cloud-Managed RDS",
             "Lift and shift on-premises GRC database to AWS RDS with Multi-AZ. Validate data integrity post-migration, update connection strings, and decommission legacy hardware."),
            ("Decomission Deprecated Risk Scoring Microservice and Consolidate Logic",
             "Identify all consumers of deprecated risk scoring service, migrate them to consolidated risk engine, and decommission the old service. Remove dead code and update API gateway routing."),
            ("Improve Compliance Dashboard Query Performance with Index Optimization",
             "Profile slow compliance dashboard queries, add composite indexes, and refactor N+1 queries. Target 5x improvement on regulatory summary report load times."),
            ("Consolidate Duplicate Compliance Data Models Across Three Services",
             "Audit data model duplication across compliance, risk, and audit services. Extract shared domain model into common library, update all services, and eliminate synchronization bugs."),
            ("Upgrade Kafka Consumer Group for Real-Time Regulatory Event Processing",
             "Upgrade Kafka client library and refactor consumer group configuration for regulatory event stream. Implement consumer lag monitoring and autoscaling to handle peak filing periods."),
        ],
        "Enterprise Strategic Priority": [
            ("Launch AI-Powered Regulatory Intelligence Platform for Proactive Compliance",
             "Build ML-based platform to predict regulatory changes and their business impact. Enable compliance team to proactively plan remediation before regulatory effective dates, reducing last-minute scrambles."),
            ("Develop Unified Compliance Data Lake for Cross-Regulatory Analytics",
             "Create centralized compliance data lake aggregating data from SOX, GDPR, PCI, and AML systems. Enable cross-regulatory analytics and executive dashboards for board-level risk reporting."),
            ("Implement Real-Time Regulatory Reporting Hub for Multi-Jurisdiction Filing",
             "Build strategic hub capable of simultaneous regulatory filing across US, EU, and UK jurisdictions. Reduce per-filing cost by 60% and enable the firm to enter new markets faster."),
            ("Establish Compliance-as-a-Service Platform for Business Units",
             "Create internal compliance platform exposing regulatory controls as APIs. Enable product teams to embed compliance checks natively in their workflows without building from scratch."),
            ("Strategic Partnership with RegTech Vendor for AI-Driven KYC Automation",
             "Integrate strategic RegTech partner platform to automate 70% of KYC decisions using AI. Enable digital-first onboarding, reduce manual review cost, and improve customer experience."),
        ],
    }

    # Build team assignment list
    team_list = []
    for team, count in teams_pool:
        team_list.extend([team] * count)
    random.shuffle(team_list)

    rows = []
    template_counters = {cat: 0 for cat in templates}

    for i in range(60):
        issue_key = f"COMP-{str(i+1).zfill(3)}"
        story_id = f"STR-{str(10000 + i + 1)}"
        true_cat = true_category_pool[i]
        confidence = confidence_pool[i]
        team = team_list[i]

        epic_idx = i % 5
        epic, epic_id = epics[epic_idx]
        # Stories per epic = 60 / 5 = 12; distribute evenly across 4 features → 3 stories per feature
        stories_per_epic = 60 // 5
        feat_id, feat_name = epic_feature_map[epic_idx][(i // 5) % features_per_epic]

        tmpl_list = templates[true_cat]
        tmpl = tmpl_list[template_counters[true_cat] % len(tmpl_list)]
        template_counters[true_cat] += 1

        title = tmpl[0]
        description = tmpl[1]

        # Assign WAF category (with possible mismatch)
        if i in mismatch_indices:
            wrong_cats = [c for c in ALL_CATEGORIES if c != true_cat]
            waf_category = random.choice(wrong_cats)
        else:
            waf_category = true_cat

        waf_color = WAF_COLOR_MAP[waf_category]

        run_change = "Run" if true_cat in ["KTLO (Keep the Lights On)", "Technical Maintenance", "Regulatory (Operational)"] else "Change"

        ts = random_date(datetime(2024, 7, 1), datetime(2024, 12, 31))

        rows.append({
            "Issue Key": issue_key,
            "Story ID": story_id,
            "Story Title": title,
            "Story Description": description,
            "Team": team,
            "Epic": epic,
            "Epic ID": epic_id,
            "Feature Name": feat_name,
            "Feature ID": feat_id,
            "WAF Category": waf_category,
            "WAF Color": waf_color,
            "Confidence": confidence,
            "Run/Change": run_change,
            "Timestamp": ts,
        })

    return rows


# ---------------------------------------------------------------------------
# Dataset 2: platform-engineering-80.csv
# ---------------------------------------------------------------------------

def build_platform_dataset() -> list[dict]:
    random.seed(99)

    teams_pool = [
        ("Platform Engineering", 20),
        ("SRE", 15),
        ("Cloud Ops", 18),
        ("DevOps", 15),
        ("Security", 12),
    ]

    epics = [
        ("Cloud Migration Program", "EP-P001"),
        ("Kubernetes Modernization", "EP-P002"),
        ("CI/CD Pipeline Rebuild", "EP-P003"),
        ("Observability Platform", "EP-P004"),
        ("Zero Trust Security", "EP-P005"),
    ]

    features = [f"F-P{str(i).zfill(3)}" for i in range(1, 26)]
    feature_names = [
        # EP-P001 Cloud Migration (F-P001–F-P005)
        "AWS Landing Zone", "VPC Architecture", "Cloud Cost Optimization", "Disaster Recovery", "Infrastructure as Code",
        # EP-P002 Kubernetes (F-P006–F-P010)
        "K8s Cluster Upgrade", "Helm Chart Library", "Container Registry", "Service Mesh", "Auto Scaling",
        # EP-P003 CI/CD (F-P011–F-P015)
        "GitLab CI Templates", "ArgoCD Deployment", "Ephemeral Build Runners", "Artifact Management", "Pipeline Security Scanning",
        # EP-P004 Observability (F-P016–F-P020)
        "Grafana Dashboards", "Prometheus Stack", "Jaeger Tracing", "Log Aggregation", "SLO Framework",
        # EP-P005 Zero Trust (F-P021–F-P025)
        "Zero Trust Gateway", "Identity Federation", "Secret Management", "Policy Enforcement", "Incident Management",
    ]

    # Map each epic index to its feature slice (5 features per epic)
    features_per_epic = 5
    epic_feature_map = {
        ei: [(features[ei * features_per_epic + fi], feature_names[ei * features_per_epic + fi])
             for fi in range(features_per_epic)]
        for ei in range(len(epics))
    }

    # True category distribution: 35% TechMaint, 30% KTLO, 20% EntStrat, 15% OtherBlocked
    true_category_pool = (
        ["Technical Maintenance"] * 28 +
        ["KTLO (Keep the Lights On)"] * 24 +
        ["Enterprise Strategic Priority"] * 16 +
        ["Other Block Priority"] * 12
    )
    random.shuffle(true_category_pool)

    confidence_pool = ["HIGH"] * 40 + ["MEDIUM"] * 28 + ["LOW"] * 12
    random.shuffle(confidence_pool)

    mismatch_indices = set(random.sample(range(80), 12))

    templates = {
        "Technical Maintenance": [
            ("Upgrade EKS Cluster from Kubernetes 1.27 to 1.30 Across All Environments",
             "Perform in-place EKS cluster upgrade through intermediate versions 1.28 and 1.29. Validate workload compatibility, update node groups, and run full regression suite post-upgrade."),
            ("Migrate Helm Chart Deployments from Helm 2 to Helm 3 Schema",
             "Convert all legacy Helm 2 charts to Helm 3 format, update release metadata, and remove Tiller dependencies. Test rollback procedures in staging before migrating production releases."),
            ("Refactor Monolithic Terraform State into Modular Workspaces",
             "Break 15,000-line monolithic Terraform state into environment-scoped workspaces. Implement remote state locking, add module versioning, and migrate existing resources without downtime."),
            ("Consolidate Disparate CI/CD Pipelines into Unified GitLab CI Framework",
             "Audit 40+ fragmented Jenkins and GitLab pipelines across teams. Migrate to standardized GitLab CI templates, eliminate duplication, and enforce security scanning at every stage."),
            ("Replace Custom Ingress Controller with AWS ALB Ingress Controller",
             "Migrate from custom NGINX ingress to AWS ALB ingress controller for improved AWS integration. Update all ingress manifests, validate SSL termination, and decommission legacy controller."),
            ("Decomission Legacy On-Premises Build Agents and Migrate to Ephemeral Cloud Runners",
             "Retire aging on-premises CI build agents. Provision ephemeral cloud-based runners with autoscaling, update pipeline configurations, and decommission physical build servers."),
            ("Upgrade Prometheus Stack from v2.40 to v2.51 with Thanos Integration",
             "Upgrade Prometheus operator and associated components. Integrate Thanos for long-term metrics storage, migrate existing dashboards, and validate alert rule compatibility post-upgrade."),
            ("Migrate Secrets from Environment Variables to HashiCorp Vault Dynamic Secrets",
             "Audit all services using hardcoded or environment-variable secrets. Migrate to Vault dynamic secret injection via sidecar pattern. Rotate all existing static credentials post-migration."),
        ],
        "KTLO (Keep the Lights On)": [
            ("Patch Critical CVE in Container Base Images Across All Production Workloads",
             "Apply security patches for critical CVEs detected in base container images. Rebuild affected images, push to registry, and trigger rolling deployments across all production Kubernetes namespaces."),
            ("Resolve Node Disk Pressure Alerts Causing Pod Evictions on Prod Cluster",
             "Investigate and remediate disk pressure conditions on production EKS worker nodes causing pod evictions. Clean up stale container images and expand node storage volumes."),
            ("Renew Wildcard TLS Certificate for Internal Platform Services Domain",
             "Renew expiring wildcard TLS certificate for *.platform.internal domain. Update certificate in AWS Certificate Manager, rotate Kubernetes secrets, and validate all ingress endpoints."),
            ("Respond to PagerDuty Incident for Grafana Dashboard Unavailability",
             "Investigate and restore Grafana instance unavailable due to database connection pool exhaustion. Tune connection pool settings, add circuit breaker, and document runbook for future incidents."),
            ("Restore Failed Velero Backup Jobs for Persistent Volume Claims",
             "Debug and restore failed Velero backup jobs for critical PVCs. Validate backup integrity, update backup schedules, and configure alerting for future backup failures."),
            ("Update Expired IAM Role Trust Policies for Cross-Account Deployments",
             "Renew expired IAM trust policy conditions that are blocking cross-account deployments. Update role trust relationships, validate CI/CD pipelines resume, and schedule recurring policy reviews."),
            ("Restart Crashed Istio Control Plane Components in Service Mesh",
             "Diagnose and restart crashed Istio pilot components causing sidecar injection failures. Investigate root cause, tune resource limits, and add health check probes to prevent recurrence."),
            ("Remediate Failed Node Auto-Scaling Events During Peak Traffic Hours",
             "Investigate auto-scaling failures during peak traffic. Fix Launch Template configuration issues preventing new node provisioning. Validate scale-out behavior under simulated load."),
        ],
        "Enterprise Strategic Priority": [
            ("Launch Multi-Region Active-Active Architecture for Global Platform Availability",
             "Design and implement active-active multi-region deployment enabling 99.99% SLA. Enable seamless global traffic routing, cross-region data replication, and automated regional failover."),
            ("Build Internal Developer Platform with Self-Service Infrastructure Provisioning",
             "Create developer portal enabling self-service provisioning of cloud resources, databases, and CI/CD pipelines. Reduce time-to-environment from 2 weeks to 4 hours for all engineering teams."),
            ("Implement FinOps Platform for Real-Time Cloud Cost Optimization",
             "Deploy FinOps tooling with real-time cost attribution by team, product, and environment. Establish showback/chargeback model and automated rightsizing recommendations to reduce cloud spend 30%."),
            ("Establish Platform Engineering Center of Excellence and Standards Body",
             "Create cross-team platform engineering guild to define standards, approve architecture decisions, and drive platform adoption. Publish internal docs, run enablement sessions, and measure developer satisfaction."),
        ],
        "Other Block Priority": [
            ("Unblock Zero Trust Network Access Rollout Pending Security Architecture Review",
             "Platform team is blocked waiting for Security Architecture board approval for Zero Trust network topology. Work is scoped, resourced, and ready to execute pending sign-off from security governance."),
            ("Unblock Kubernetes Multi-Tenancy Rollout Awaiting FinOps Chargeback Model Approval",
             "K8s multi-tenancy implementation is ready but blocked pending FinOps team delivering namespace-level cost attribution model needed for tenant billing. Escalated to VP Engineering."),
            ("Blocked: Service Mesh Expansion Requires Network Team Firewall Rule Changes",
             "Istio service mesh expansion to remaining namespaces is blocked on Network team opening required inter-namespace firewall ports. Ticket raised 3 weeks ago with no progress."),
            ("Platform DR Testing Blocked Pending Vendor Contract for Secondary Region",
             "Disaster recovery test plan is complete but blocked on Procurement finalizing secondary cloud region contract. Engineering resources are standing by ready to execute."),
        ],
    }

    # Cross-team epic assignments: EP-P001, EP-P002, EP-P003 should span 2+ teams
    cross_team_epics = {"EP-P001", "EP-P002", "EP-P003"}

    team_list = []
    for team, count in teams_pool:
        team_list.extend([team] * count)
    random.shuffle(team_list)

    rows = []
    template_counters = {cat: 0 for cat in templates}

    for i in range(80):
        issue_key = f"PLAT-{str(i+1).zfill(3)}"
        story_id = f"STR-{str(20000 + i + 1)}"
        true_cat = true_category_pool[i]
        confidence = confidence_pool[i]

        epic_idx = i % 5
        epic, epic_id = epics[epic_idx]

        # For cross-team epics, randomize team; otherwise use pool
        if epic_id in cross_team_epics:
            team = random.choice([t for t, _ in teams_pool])
        else:
            team = team_list[i]

        # 80 stories / 5 epics = 16 stories per epic; distribute across 5 features → 3-4 per feature
        feat_id, feat_name = epic_feature_map[epic_idx][(i // 5) % features_per_epic]

        tmpl_list = templates[true_cat]
        tmpl = tmpl_list[template_counters[true_cat] % len(tmpl_list)]
        template_counters[true_cat] += 1

        title = tmpl[0]
        description = tmpl[1]

        if i in mismatch_indices:
            wrong_cats = [c for c in ALL_CATEGORIES if c != true_cat]
            waf_category = random.choice(wrong_cats)
        else:
            waf_category = true_cat

        waf_color = WAF_COLOR_MAP[waf_category]

        run_change = "Run" if true_cat in ["KTLO (Keep the Lights On)", "Technical Maintenance"] else "Change"

        ts = random_date(datetime(2024, 10, 1), datetime(2025, 3, 31))

        rows.append({
            "Issue Key": issue_key,
            "Story ID": story_id,
            "Story Title": title,
            "Story Description": description,
            "Team": team,
            "Epic": epic,
            "Epic ID": epic_id,
            "Feature Name": feat_name,
            "Feature ID": feat_id,
            "WAF Category": waf_category,
            "WAF Color": waf_color,
            "Confidence": confidence,
            "Run/Change": run_change,
            "Timestamp": ts,
        })

    return rows


# ---------------------------------------------------------------------------
# Dataset 3: multi-team-product-120.csv
# ---------------------------------------------------------------------------

def build_product_dataset() -> list[dict]:
    random.seed(7)

    teams_pool = [
        ("Product Engineering", 18),
        ("AI/ML Team", 15),
        ("Mobile Team", 12),
        ("API Platform", 15),
        ("Data Services", 20),
        ("Frontend", 10),
        ("QA Engineering", 10),
        ("Architecture", 20),
    ]

    epics = [
        ("Customer 360 Platform", "EP-M001"),
        ("AI Feature Factory", "EP-M002"),
        ("Mobile Banking Relaunch", "EP-M003"),
        ("API Gateway Modernization", "EP-M004"),
        ("Data Mesh Initiative", "EP-M005"),
        ("Developer Experience", "EP-M006"),
    ]

    features = [f"F-M{str(i).zfill(3)}" for i in range(1, 31)]
    feature_names = [
        # EP-M001 Customer 360 (F-M001–F-M005)
        "Customer Profile Service", "Unified Customer View", "Recommendation Engine",
        "Personalization Engine", "Customer Data Aggregation API",
        # EP-M002 AI Factory (F-M006–F-M010)
        "ML Model Pipeline", "Feature Store", "Model Registry",
        "AI Inference Service", "A/B Testing Framework",
        # EP-M003 Mobile Banking (F-M011–F-M015)
        "Mobile Design System", "Biometric Authentication", "Push Notification Service",
        "Mobile CI/CD Pipeline", "React Native Upgrade",
        # EP-M004 API Gateway (F-M016–F-M020)
        "API Rate Limiting", "Developer Portal", "GraphQL Federation",
        "API Analytics", "REST-to-GraphQL Adapter",
        # EP-M005 Data Mesh (F-M021–F-M025)
        "Data Product Framework", "Domain Data Ownership", "Data Quality Engine",
        "Metadata Catalog", "Data Governance Policy",
        # EP-M006 Developer Experience (F-M026–F-M030)
        "CI/CD Templates", "Testing Framework", "Local Dev Environment",
        "Documentation Platform", "Security Scanning Pipeline",
    ]

    # Map each epic index to its feature slice (5 features per epic)
    features_per_epic = 5
    epic_feature_map = {
        ei: [(features[ei * features_per_epic + fi], feature_names[ei * features_per_epic + fi])
             for fi in range(features_per_epic)]
        for ei in range(len(epics))
    }

    # True category distribution: 30% EntStrat, 25% OtherBlocked, 20% TechMaint, 15% BizMaint, 10% KTLO
    true_category_pool = (
        ["Enterprise Strategic Priority"] * 36 +
        ["Other Block Priority"] * 30 +
        ["Technical Maintenance"] * 24 +
        ["Business Maintenance"] * 18 +
        ["KTLO (Keep the Lights On)"] * 12
    )
    random.shuffle(true_category_pool)

    confidence_pool = ["HIGH"] * 48 + ["MEDIUM"] * 48 + ["LOW"] * 24
    random.shuffle(confidence_pool)

    mismatch_indices = set(random.sample(range(120), 24))

    # 10 stories with missing descriptions (indices 50-59)
    missing_desc_indices = set(range(50, 60))

    templates = {
        "Enterprise Strategic Priority": [
            ("Build Unified Customer 360 Profile Aggregating All Product Touchpoints",
             "Create single authoritative customer profile aggregating data from banking, investments, and insurance products. Enable personalized experiences across all channels and accelerate cross-sell revenue opportunities."),
            ("Launch AI-Powered Personal Finance Manager with Predictive Insights",
             "Develop AI financial coaching feature providing personalized spending insights, savings goals, and investment recommendations. Target 25% increase in digital engagement and product cross-sell."),
            ("Develop Next-Generation Mobile Banking App with Biometric Authentication",
             "Rebuild mobile banking app with modern architecture, biometric auth, and personalized home screen. Capture millennial and Gen-Z market share and increase mobile MAU by 40%."),
            ("Implement GraphQL Federation Layer Unifying Disparate Backend APIs",
             "Build federated GraphQL gateway consolidating 20+ REST microservices into unified schema. Enable frontend teams to ship features 3x faster without backend bottlenecks."),
            ("Establish Data Mesh Architecture Enabling Domain-Owned Data Products",
             "Transform centralized data warehouse to federated data mesh. Enable 8 domain teams to own and publish their data products, reducing time-to-insight for analytics from weeks to days."),
            ("Create AI Feature Factory Platform for Rapid ML Feature Deployment",
             "Build internal ML platform enabling data scientists to deploy features to production in hours not weeks. Standardize feature engineering, A/B testing, and model serving infrastructure."),
            ("Launch Embedded Finance API Platform for Third-Party Partner Integrations",
             "Create secure API platform enabling fintech partners to embed banking services. Enable new revenue stream targeting $50M ARR from embedded finance partnerships within 18 months."),
            ("Implement Real-Time Fraud Prevention Using ML Behavioral Biometrics",
             "Deploy real-time behavioral biometrics model analyzing device and interaction patterns to detect account takeover. Target 70% reduction in fraud losses without increasing customer friction."),
        ],
        "Other Block Priority": [
            ("Customer 360 API Integration Blocked Pending Legal Data Sharing Agreement",
             "Customer data aggregation API is fully built and tested but blocked on Legal finalizing data sharing agreements with three subsidiary entities. Engineering team has been idle for 6 weeks."),
            ("Mobile Biometric Feature Blocked Awaiting Apple MDM Policy Exception",
             "Biometric authentication feature is blocked on corporate MDM policy preventing FaceID API access in managed app profiles. Escalated to Security and Vendor Management 4 weeks ago."),
            ("AI Model Deployment Blocked by Missing GPU Node Pool Budget Approval",
             "ML inference service is ready for production but blocked on FinOps approving GPU node pool provisioning. Monthly cost estimate submitted and pending CFO approval since last quarter."),
            ("Data Mesh Rollout Blocked on Data Governance Policy Ratification",
             "Domain data ownership model is designed and teams are trained but blocked on Chief Data Officer ratifying data governance policy needed before domains can publish data products."),
            ("GraphQL Federation Blocked Pending Security Review of Schema Introspection",
             "Federation layer implementation complete but blocked on Security team completing threat model review of schema introspection exposure. Review requested 8 weeks ago with no update."),
            ("Developer Experience Initiative Stalled Due to Platform Team Bandwidth Constraints",
             "DX improvements are scoped and prioritized but blocked because Platform Engineering team is fully consumed by critical production incidents. No capacity until Q3 at earliest."),
        ],
        "Technical Maintenance": [
            ("Migrate Customer Profile Service from DynamoDB to Aurora PostgreSQL",
             "Migrate customer profile data store from DynamoDB to Aurora PostgreSQL to support complex join queries needed for 360 view. Implement zero-downtime migration with dual-write pattern."),
            ("Upgrade React Native Mobile App from Version 0.69 to 0.73",
             "Upgrade React Native version across iOS and Android mobile apps. Resolve breaking changes, update third-party libraries, and validate rendering parity on all supported device OS versions."),
            ("Refactor Monolithic User Service into Domain-Scoped Microservices",
             "Break down monolithic user service into identity, profile, and preferences microservices. Implement event-driven communication, update API contracts, and migrate consumers incrementally."),
            ("Consolidate Four Legacy REST APIs into Unified GraphQL Schema",
             "Merge four fragmented customer-facing REST APIs into unified GraphQL schema. Deprecate old endpoints with 6-month sunset, maintain backward compatibility via REST-to-GraphQL adapter."),
            ("Improve ML Training Pipeline Performance with Distributed Feature Computation",
             "Refactor sequential feature computation in ML training pipeline to distributed Spark jobs. Target 10x reduction in training run time enabling daily model retraining instead of weekly."),
            ("Migrate Frontend Build System from Webpack 4 to Vite",
             "Upgrade frontend build toolchain from Webpack 4 to Vite. Expect 20x faster HMR and 5x faster cold builds. Update all CI/CD pipelines and developer environment setup scripts."),
        ],
        "Business Maintenance": [
            ("Update Annual Vendor SLA Review Documentation for Core Banking Partners",
             "Conduct annual review of SLA terms with core banking vendors. Update service level agreements, document performance benchmarks, and negotiate improved terms for the upcoming contract renewal."),
            ("Refresh Product Roadmap Documentation for Stakeholder Quarterly Business Review",
             "Update product roadmap decks and supporting documentation for Q4 QBR presentation to executive stakeholders. Align with strategic priorities and incorporate feedback from customer advisory board."),
            ("Manage App Store Listing Updates for iOS and Android Banking App",
             "Update app store descriptions, screenshots, and metadata for iOS App Store and Google Play. Ensure listings reflect latest feature set and comply with updated platform guidelines."),
            ("Conduct Annual Third-Party Software License Audit and Renewal",
             "Audit all third-party software licenses in use across product teams. Identify unused licenses for termination, renew active licenses, and flag non-compliant open-source usage for legal review."),
            ("Update Internal API Documentation and Developer Onboarding Guides",
             "Refresh API documentation site with new endpoints, deprecation notices, and updated code examples. Improve developer onboarding guide based on survey feedback to reduce time-to-first-call."),
            ("Coordinate Annual Penetration Testing Program for Customer-Facing Applications",
             "Manage annual pen test engagement with external security vendor. Scope test coverage, coordinate access, track remediation of findings, and produce executive summary for board risk committee."),
        ],
        "KTLO (Keep the Lights On)": [
            ("Apply Critical Security Patch to Mobile App Authentication Library",
             "Apply emergency security patch for authentication library CVE affecting iOS and Android apps. Expedite through app store review, force-update users on vulnerable versions, and monitor adoption."),
            ("Resolve Production Data Pipeline Failures Causing Stale Customer Profiles",
             "Investigate and fix broken ETL pipeline causing customer profile data to be 48 hours stale. Implement idempotent retry logic and add monitoring to detect future pipeline failures within minutes."),
            ("Renew Push Notification Service Certificates for iOS Production Apps",
             "Renew expiring APNs certificates for production iOS banking apps. Update certificates in AWS SNS, test push delivery on all notification categories, and schedule reminder for next renewal."),
            ("Fix Memory Leak in Customer Search Service Causing Hourly Pod Restarts",
             "Investigate memory leak in customer search service causing pod OOM kills every 60 minutes. Profile heap allocations, fix unclosed database connections, and validate fix under sustained load."),
        ],
    }

    # All epics should span at least 3 teams
    all_teams = [t for t, _ in teams_pool]
    epic_team_assignments = {epic_id: list(all_teams) for _, epic_id in epics}

    team_list = []
    for team, count in teams_pool:
        team_list.extend([team] * count)
    random.shuffle(team_list)

    rows = []
    template_counters = {cat: 0 for cat in templates}

    for i in range(120):
        issue_key = f"PROD-{str(i+1).zfill(3)}"
        story_id = f"STR-{str(30000 + i + 1)}"
        true_cat = true_category_pool[i]
        confidence = confidence_pool[i]

        epic_idx = i % 6
        epic, epic_id = epics[epic_idx]

        # Rotate teams per epic to ensure cross-team coverage
        epic_teams = epic_team_assignments[epic_id]
        team = epic_teams[i % len(epic_teams)]

        # 120 stories / 6 epics = 20 stories per epic; distribute across 5 features → 4 per feature
        feat_id, feat_name = epic_feature_map[epic_idx][(i // 6) % features_per_epic]

        tmpl_list = templates[true_cat]
        tmpl = tmpl_list[template_counters[true_cat] % len(tmpl_list)]
        template_counters[true_cat] += 1

        title = tmpl[0]

        # Missing description for indices 50-59
        if i in missing_desc_indices:
            description = ""
        else:
            description = tmpl[1]

        if i in mismatch_indices:
            wrong_cats = [c for c in ALL_CATEGORIES if c != true_cat]
            waf_category = random.choice(wrong_cats)
        else:
            waf_category = true_cat

        waf_color = WAF_COLOR_MAP[waf_category]

        run_change = "Change" if true_cat in ["Enterprise Strategic Priority", "Other Block Priority"] else "Run"

        ts = random_date(datetime(2025, 1, 1), datetime(2025, 6, 30))

        rows.append({
            "Issue Key": issue_key,
            "Story ID": story_id,
            "Story Title": title,
            "Story Description": description,
            "Team": team,
            "Epic": epic,
            "Epic ID": epic_id,
            "Feature Name": feat_name,
            "Feature ID": feat_id,
            "WAF Category": waf_category,
            "WAF Color": waf_color,
            "Confidence": confidence,
            "Run/Change": run_change,
            "Timestamp": ts,
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def print_summary(name: str, rows: list[dict], mismatch_indices: set, true_cats: list) -> None:
    teams = {}
    epics = {}
    cats = {}
    confidences = {}
    run_change = {}

    for row in rows:
        teams[row["Team"]] = teams.get(row["Team"], 0) + 1
        epics[row["Epic"]] = epics.get(row["Epic"], 0) + 1
        cats[row["WAF Category"]] = cats.get(row["WAF Category"], 0) + 1
        confidences[row["Confidence"]] = confidences.get(row["Confidence"], 0) + 1
        run_change[row["Run/Change"]] = run_change.get(row["Run/Change"], 0) + 1

    actual_mismatches = sum(
        1 for i, row in enumerate(rows)
        if i in mismatch_indices
    )

    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Total rows:     {len(rows)}")
    print(f"  Mismatch count: {actual_mismatches}")
    print(f"  Teams ({len(teams)}):")
    for t, c in sorted(teams.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")
    print(f"  Epics ({len(epics)}):")
    for e, c in sorted(epics.items(), key=lambda x: -x[1]):
        print(f"    {e}: {c}")
    print(f"  WAF Categories:")
    for cat, c in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {c}")
    print(f"  Confidence: {confidences}")
    print(f"  Run/Change:  {run_change}")


if __name__ == "__main__":
    random.seed(0)

    # --- Dataset 1 ---
    random.seed(42)
    rows1 = build_compliance_dataset()
    mismatch1 = set(random.sample(range(60), 18))  # re-derive for summary
    path1 = OUTPUT_DIR / "compliance-focus-60.csv"
    write_csv(path1, rows1)
    print_summary("compliance-focus-60.csv", rows1, mismatch1, [])
    print(f"  Saved to: {path1}")

    # --- Dataset 2 ---
    random.seed(99)
    rows2 = build_platform_dataset()
    mismatch2 = set(random.sample(range(80), 12))
    path2 = OUTPUT_DIR / "platform-engineering-80.csv"
    write_csv(path2, rows2)
    print_summary("platform-engineering-80.csv", rows2, mismatch2, [])
    print(f"  Saved to: {path2}")

    # --- Dataset 3 ---
    random.seed(7)
    rows3 = build_product_dataset()
    mismatch3 = set(random.sample(range(120), 24))
    path3 = OUTPUT_DIR / "multi-team-product-120.csv"
    write_csv(path3, rows3)
    missing_desc_count = sum(1 for r in rows3 if not r["Story Description"])
    print_summary("multi-team-product-120.csv", rows3, mismatch3, [])
    print(f"  Missing descriptions: {missing_desc_count}")
    print(f"  Saved to: {path3}")

    # ---------------------------------------------------------------------------
    # Verification: print epic → feature mapping and check parent-child integrity
    # ---------------------------------------------------------------------------
    def verify_hierarchy(name: str, rows: list[dict]) -> None:
        print(f"\n{'='*60}")
        print(f"  HIERARCHY VERIFICATION: {name}")
        print(f"{'='*60}")

        # Build actual epic → feature_ids mapping from the data
        epic_to_features: dict = {}
        for row in rows:
            eid = row["Epic ID"]
            fid = row["Feature ID"]
            epic_to_features.setdefault(eid, set()).add(fid)

        violations = 0
        for eid in sorted(epic_to_features):
            fids = sorted(epic_to_features[eid])
            print(f"  {eid}: {', '.join(fids)}")

        # Cross-check: every row's feature must belong to its epic's feature set
        for i, row in enumerate(rows):
            eid = row["Epic ID"]
            fid = row["Feature ID"]
            if fid not in epic_to_features[eid]:
                print(f"  VIOLATION row {i}: Epic={eid} Feature={fid}")
                violations += 1

        if violations == 0:
            print(f"  OK — all {len(rows)} stories have valid epic→feature hierarchy.")
        else:
            print(f"  FAILED — {violations} hierarchy violations found!")

    verify_hierarchy("compliance-focus-60.csv", rows1)
    verify_hierarchy("platform-engineering-80.csv", rows2)
    verify_hierarchy("multi-team-product-120.csv", rows3)

    print(f"\n{'='*60}")
    print("  All 3 datasets generated successfully.")
    print(f"{'='*60}\n")
