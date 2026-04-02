"""
Bulk upload reports to Dan's World dropzone.

Reads HTML files from CTOWorkspace, copies them to the dropzone directory,
and inserts records into the admin SQLite database with category, visibility,
and report metadata.

Usage:
    python3 bulk_upload_reports.py [--dry-run] [--db PATH] [--dropzone PATH]

Defaults assume running from the dans-world directory with the Docker volume
paths available locally (for pre-staging before container rebuild).
"""

import os
import sys
import uuid
import shutil
import sqlite3
import argparse
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration: base path for source files
# ---------------------------------------------------------------------------
WORKSPACE = os.path.expanduser("~/CTOWorkspace")

# ---------------------------------------------------------------------------
# Report manifest: each entry defines a file to upload
# ---------------------------------------------------------------------------
# Fields: (source_path, title, description, category, is_public, data_flag)
# data_flag is for reference only (CUSTOMER, GENERIC, ANONYMIZED, INTERNAL)
# is_public is derived from data_flag: GENERIC/ANONYMIZED -> True, else False

REPORTS = [
    # =========================================================================
    # Integration Capability Briefs
    # =========================================================================
    (
        "03_Product/integration_catalog/Attack_Surface_Coverage_Brief.html",
        "Arctic Wolf Security Operations Coverage Brief",
        "Attack surface coverage across endpoint, identity, network, cloud, SaaS, email, and vulnerability domains",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/AWN_MDR_Signals_OnePager.html",
        "Arctic Wolf MDR Signals - Coverage Matrix",
        "One-page overview of MDR signal ingestion across all integration categories",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/AWN_MDR_Coverage_Matrix.html",
        "Arctic Wolf MDR Coverage Matrix",
        "Detailed coverage matrix for MDR integrations",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "scratch/cato_networks_capability_brief.html",
        "Arctic Wolf + Cato Networks SSE 360 -- Technical Capability Brief",
        "Detection capabilities, data fields, setup requirements, and MITRE coverage for Cato SSE 360 integration",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "scratch/okta_detection_coverage_report_jazzy.html",
        "Okta Detection Coverage Report",
        "Comprehensive overview of Arctic Wolf detection capabilities for Okta environments",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Endpoint_Coverage.html",
        "Coverage One-Pager: Endpoint",
        "Endpoint integration coverage across CrowdStrike, SentinelOne, Defender, Carbon Black, Sophos, and more",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Identity_Coverage.html",
        "Coverage One-Pager: Identity",
        "Identity integration coverage across Entra ID, Okta, Duo, CyberArk, and more",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Network_Coverage.html",
        "Coverage One-Pager: Network",
        "Network integration coverage across firewalls, IDS/IPS, DNS, and proxy solutions",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Cloud_Coverage.html",
        "Coverage One-Pager: Cloud",
        "Cloud integration coverage across AWS, Azure, GCP, and cloud security posture",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/SaaS_Coverage.html",
        "Coverage One-Pager: SaaS",
        "SaaS integration coverage across M365, Google Workspace, Salesforce, Box, and more",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Email_Coverage.html",
        "Coverage One-Pager: Email",
        "Email security integration coverage across Proofpoint, Mimecast, Cisco Secure Email, and more",
        "Integration Capability Briefs", True, "GENERIC",
    ),
    (
        "03_Product/integration_catalog/one_pagers/Vulnerability_Coverage.html",
        "Coverage One-Pager: Vulnerability",
        "Vulnerability management integration coverage across Tenable, Qualys, Rapid7, and more",
        "Integration Capability Briefs", True, "GENERIC",
    ),

    # =========================================================================
    # ITDR / Managed Identity
    # =========================================================================
    (
        "03_Product/ITDR_SKU/ITDR_SKU_OnePager.html",
        "Arctic Wolf ITDR SKU - One Pager",
        "Product one-pager for the ITDR (Identity Threat Detection and Response) SKU",
        "ITDR / Managed Identity", True, "GENERIC",
    ),
    (
        "03_Product/ITDR_SKU/ITDR_Battlecard.html",
        "Arctic Wolf ITDR - Competitive Battlecard",
        "Competitive positioning against CrowdStrike Falcon Identity, Microsoft Defender for Identity, Semperis, and others",
        "ITDR / Managed Identity", True, "GENERIC",
    ),
    (
        "03_Product/ITDR_SKU/ITDR_Competitive_Analysis.html",
        "ITDR Competitive Landscape Analysis",
        "Full competitive landscape analysis for the managed identity / ITDR market",
        "ITDR / Managed Identity", True, "GENERIC",
    ),

    # =========================================================================
    # Customer Security Reports (PRIVATE)
    # =========================================================================
    (
        "scratch/concordhospital_report/security_report.html",
        "Concord Hospital Security Report - Q4 2025",
        "Quarterly security operations report for Concord Hospital",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/concordhospital_report/security_report_board.html",
        "Concord Hospital - Executive Security Risk Assessment",
        "Board-level executive security risk assessment",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/concordhospital_report/security_report_cst.html",
        "Concord Hospital - CST Internal Report - Q4 2025",
        "Internal CST report with operational metrics and recommendations",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/traderjoes_cisco_email_report.html",
        "Cisco Secure Email Analysis - Trader Joe's",
        "Week-long Cisco Secure Email traffic analysis: 9,909 messages, quarantine breakdown, detection gap assessment",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/agero_firewall_health.html",
        "Agero Health Report (Firewall)",
        "Firewall health analysis for Agero",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/agero_service_health.html",
        "Service Health - Agero, Inc.",
        "Comprehensive service health report for Agero",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/steptoe_investigation.html",
        "Investigation Graph - Steptoe LLP",
        "Security investigation graph visualization",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/steptoe_findings.html",
        "Investigation Findings - Steptoe LLP",
        "Detailed investigation findings and timeline",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/onespaworld_investigation_standalone.html",
        "Security Investigation - OneSpaWorld",
        "Standalone security investigation report",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/amdq/AMDQ_Microsoft_Integration_Report.html",
        "Microsoft Integration Capabilities - American Dairy Queen",
        "Microsoft integration coverage assessment for AMDQ",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ultraintelligence/security_report.html",
        "Ultra Intelligence - Security Assessment",
        "Security posture assessment",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ultraintelligence/network_map.html",
        "Ultra Intelligence - Network Map",
        "Network topology visualization",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ultraintelligence/network_topology.html",
        "Ultra Intelligence - Network Topology",
        "Detailed network topology analysis",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ultraintelligence/security_report_full.html",
        "Ultra Intelligence - Full Security Report",
        "Comprehensive security report with all findings",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ultraintelligence/ms_best_practices.html",
        "Ultra Intelligence - Microsoft Best Practices",
        "Microsoft environment best practices recommendations",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/steve_hunter_law_firm/elastic_rules_report.html",
        "Elastic Security Detection Rules Report - KWM",
        "Elastic detection rules analysis for MDR migration assessment",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/steve_hunter_law_firm/kwm_mdr_migration_analysis.html",
        "KWM MDR Migration Analysis",
        "MDR migration feasibility analysis from Elastic to Arctic Wolf",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/tmp_bacon_tickets/bacon_security_2025_infographic.html",
        "Bacon Security - 2025 Year in Review",
        "Annual security operations infographic",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/tmp_bacon_tickets/bacon_security_2025_wrapped.html",
        "Bacon Security - 2025 Wrapped",
        "Year-end wrap-up report in Spotify Wrapped style",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ldi/ldi_comprehensive_year_review_2025.html",
        "LDI 2025 Comprehensive Year in Review",
        "Full year-in-review for Liberty Diversified International",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ldi/ldi_deployment_infographic_2025-12-14.html",
        "LDI - Deployment Overview Infographic",
        "Deployment status infographic",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ldi/ldi_year_in_review_2025.html",
        "LDI 2025 Year in Review (Alt)",
        "Alternative year-in-review format",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ldi/ldi_deployment_jazzy_2025.html",
        "LDI - Deployment Jazzy 2025",
        "Deployment overview in jazzy theme",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/ldi/ldi_focus_jazzy_2025.html",
        "LDI - Security Focus Jazzy 2025",
        "Security focus report in jazzy theme",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "03_Product/infographic_runs/lbmc_executive_summary_professional.html",
        "LBMC Technology Solutions - 2025 Security Partnership Review",
        "Executive security partnership review",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "04_Engineering/coverage_report_concordhospital.html",
        "Broad Visibility with Open XDR - Concord Hospital",
        "Open XDR coverage analysis",
        "Customer Security Reports", False, "CUSTOMER",
    ),
    (
        "scratch/feature_extractor/feature_requests_report_with_ssr.html",
        "Feature Requests - All Regions",
        "Cross-region feature request analysis with SSR data",
        "Customer Security Reports", False, "CUSTOMER",
    ),

    # =========================================================================
    # Anonymized / Sample Reports
    # =========================================================================
    (
        "scratch/concordhospital_report/security_report_board_anonymized.html",
        "ACME Healthcare - Executive Security Risk Assessment (Anonymized)",
        "Board-level security assessment template using anonymized data",
        "Anonymized / Sample Reports", True, "ANONYMIZED",
    ),
    (
        "scratch/sampleco_charlie_investigation.html",
        "Investigation Graph - Sample Co LLP (charlie.rogue)",
        "Demo investigation visualization using Sample Co placeholder",
        "Anonymized / Sample Reports", True, "ANONYMIZED",
    ),
    (
        "scratch/sampleco_ad_review_executive_report.html",
        "Sampleco - Active Directory Security Review",
        "AD security review executive report using anonymized data",
        "Anonymized / Sample Reports", True, "ANONYMIZED",
    ),
    (
        "scratch/wiz_sample_ticket.html",
        "[CRITICAL] Incident: Malware Detected in Container - Sample Co",
        "Sample Wiz cloud security incident ticket",
        "Anonymized / Sample Reports", True, "ANONYMIZED",
    ),

    # =========================================================================
    # Churn Analysis (PRIVATE)
    # =========================================================================
    (
        "scratch/churn_explorer/executive_report.html",
        "Executive Report - Q3'26 Churn Analysis",
        "Executive summary of Q3 FY26 churn patterns: 309 customers, resolution time as #1 predictor",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/executive_summary_q326.html",
        "Q3 FY26 Churn Analysis: What the Data Tells Us",
        "Narrative churn analysis with key findings and recommendations",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/ticket_dashboard.html",
        "Churn Ticket Intelligence",
        "Ticket-based churn signal analysis dashboard",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/ops_dashboard.html",
        "Operational Intelligence",
        "Ops metrics comparison between churned and renewed customers",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/churn_signals.html",
        "Churn Signal Analytics",
        "Multi-signal churn prediction model visualization",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/competitor_mentions.html",
        "Competitor Intelligence",
        "Competitor mentions extracted from churned customer tickets",
        "Churn Analysis", False, "CUSTOMER",
    ),
    (
        "scratch/churn_explorer/risk_model.html",
        "Risk Model Comparison",
        "Churn risk model comparison across customer segments",
        "Churn Analysis", False, "CUSTOMER",
    ),

    # =========================================================================
    # Threat Hunting & R&D
    # =========================================================================
    (
        "02_R_and_D/mcp-aurora/mimikatz_threat_hunt.html",
        "Threat Hunt Graph - Mimikatz Detection",
        "Interactive threat hunt visualization for Mimikatz credential theft scenario",
        "Threat Hunting & R&D", True, "DEMO",
    ),
    (
        "02_R_and_D/mcp-aurora/mimikatz_detection_graph.html",
        "Mimikatz Detection Graph",
        "Detection correlation graph for Mimikatz Sekurlsa execution",
        "Threat Hunting & R&D", True, "DEMO",
    ),
    (
        "02_R_and_D/mcp-aurora/threat_hunt_v2.html",
        "Threat Hunt: Sample Co LLP - Investigation Graph",
        "Investigation graph visualization using anonymized Sample Co data",
        "Threat Hunting & R&D", True, "ANONYMIZED",
    ),
    (
        "02_R_and_D/mcp-aurora/week_threat_hunt.html",
        "Weekly Threat Hunt Report",
        "Weekly threat hunting summary template",
        "Threat Hunting & R&D", True, "DEMO",
    ),
    (
        "02_R_and_D/mcp-aurora/ticket_investigation.html",
        "Ticket Investigation Visualization",
        "Interactive ticket investigation graph",
        "Threat Hunting & R&D", True, "DEMO",
    ),
    (
        "02_R_and_D/mcp-aurora/correlation_graph.html",
        "Correlation Graph",
        "Multi-signal correlation graph prototype",
        "Threat Hunting & R&D", True, "DEMO",
    ),

    # =========================================================================
    # Dynaframe Dashboards
    # =========================================================================
    (
        "02_R_and_D/dynaframe_dashboard/output/dashboard.html",
        "OCSF Integration Factory - Coverage Dashboard",
        "Main digital signage dashboard for OCSF coverage metrics",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/01_overview.html",
        "OCSF Coverage Overview",
        "High-level OCSF integration coverage overview",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/02_process_activity.html",
        "OCSF Process Activity Coverage",
        "Process activity class coverage across endpoints",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/03_file_activity.html",
        "OCSF File Activity Coverage",
        "File activity class coverage metrics",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/04_network_dns.html",
        "OCSF Network / DNS Activity Coverage",
        "Network and DNS activity coverage across integrations",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/05_iam.html",
        "OCSF IAM Activity Coverage",
        "Identity and access management event coverage",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/06_application.html",
        "OCSF Application Activity Coverage",
        "Application activity event coverage",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/07_summary.html",
        "OCSF Coverage Summary",
        "Summary view of all OCSF class coverage",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/08_mitre_matrix.html",
        "MITRE ATT&CK Matrix (Summary)",
        "MITRE ATT&CK tactic/technique coverage summary",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/09_mitre_subtechniques.html",
        "MITRE ATT&CK Subtechniques",
        "MITRE subtechnique-level coverage map",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/10_mitre_subtechniques_matrix.html",
        "MITRE ATT&CK Subtechniques Matrix",
        "Full MITRE subtechnique matrix with coverage overlay",
        "Dynaframe Dashboards", True, "GENERIC",
    ),
    (
        "02_R_and_D/dynaframe_dashboard/output/10_mitre_full_matrix.html",
        "MITRE ATT&CK Full Matrix",
        "Complete MITRE ATT&CK Enterprise matrix with coverage overlay",
        "Dynaframe Dashboards", True, "GENERIC",
    ),

    # =========================================================================
    # Internal / Operational
    # =========================================================================
    (
        "03_Product/infographic_runs/awn_executive_summary_professional.html",
        "AWN-CORP - Internal Security Operations Overview",
        "Arctic Wolf's own internal security operations summary",
        "Internal / Operational", False, "INTERNAL",
    ),
    (
        "03_Product/infographic_runs/awn_executive_summary_infographic.html",
        "AWN-CORP - Executive Summary (Infographic)",
        "Internal executive summary in infographic format",
        "Internal / Operational", False, "INTERNAL",
    ),
    (
        "03_Product/infographic_runs/awn_msp_focus_infographic_2025-12-11.html",
        "AWN-CORP MSP - Security Journey Report 2025",
        "Internal MSP instance security journey infographic",
        "Internal / Operational", False, "INTERNAL",
    ),
    (
        "03_Product/infographic_runs/ocsf_meeting_summary_2025-12-05.html",
        "Parsing & OCSF Strategy - Meeting Summary (Dec 5)",
        "Meeting notes: OCSF strategy discussion with action items",
        "Internal / Operational", True, "GENERIC",
    ),

    # =========================================================================
    # Training & Service Delivery
    # =========================================================================
    (
        "05_Service_Delivery/training/tier1_analyst_training/tier1_training_prototype.html",
        "Tier 1 SOC Analyst Training - Quick Reads",
        "Training module prototype for Tier 1 analysts",
        "Training & Service Delivery", True, "GENERIC",
    ),

    # =========================================================================
    # Content catalog itself
    # =========================================================================
    (
        "scratch/generated_content_catalog.html",
        "Generated Content Catalog",
        "Master catalog of all generated reports, briefs, and dashboards across CTOWorkspace",
        "Internal / Operational", True, "GENERIC",
    ),
]


def extract_title_from_html(filepath):
    """Try to extract <title> from an HTML file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
        match = re.search(r"<title>(.*?)</title>", head, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Bulk upload reports to Dan's World")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes")
    parser.add_argument("--db", default=os.path.expanduser("~/CTOWorkspace/04_Engineering/dans-world/admin/data/admin.db"),
                        help="Path to admin.db")
    parser.add_argument("--dropzone", default=os.path.expanduser("~/CTOWorkspace/04_Engineering/dans-world/html-dropzone"),
                        help="Path to dropzone directory")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN MODE ===\n")

    os.makedirs(args.dropzone, exist_ok=True)

    if not args.dry_run:
        db = sqlite3.connect(args.db)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")

        # Create table if this is a fresh DB
        db.execute("""
            CREATE TABLE IF NOT EXISTS dropzone (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                is_public INTEGER DEFAULT 0,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT DEFAULT (datetime('now')),
                description TEXT,
                is_report INTEGER DEFAULT 0,
                report_title TEXT,
                category TEXT DEFAULT 'Uncategorized'
            )
        """)
        db.commit()

        # Run migration for category column on existing DBs
        for col, defn in [("is_report", "INTEGER DEFAULT 0"), ("report_title", "TEXT"),
                           ("category", "TEXT DEFAULT 'Uncategorized'")]:
            try:
                db.execute(f"ALTER TABLE dropzone ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass

    uploaded = 0
    skipped = 0
    missing = 0

    # Category stats
    cat_stats = {}

    for (rel_path, title, description, category, is_public, data_flag) in REPORTS:
        src = os.path.join(WORKSPACE, rel_path)

        if not os.path.exists(src):
            print(f"  MISSING: {rel_path}")
            missing += 1
            continue

        # Check if this file was already uploaded (by original_name)
        orig_name = os.path.basename(rel_path)
        if not args.dry_run:
            existing = db.execute(
                "SELECT id FROM dropzone WHERE original_name = ? AND category = ?",
                (orig_name, category)
            ).fetchone()
            if existing:
                print(f"  SKIP (exists): {title}")
                skipped += 1
                continue

        file_id = str(uuid.uuid4())
        filename = f"{file_id}.html"
        dest = os.path.join(args.dropzone, filename)

        vis = "PUBLIC" if is_public else "PRIVATE"
        cat_stats.setdefault(category, {"count": 0, "public": 0, "private": 0})
        cat_stats[category]["count"] += 1
        if is_public:
            cat_stats[category]["public"] += 1
        else:
            cat_stats[category]["private"] += 1

        if args.dry_run:
            print(f"  [{vis:7}] {category:35} | {title}")
        else:
            shutil.copy2(src, dest)
            db.execute(
                """INSERT INTO dropzone
                   (id, filename, original_name, is_public, uploaded_by, description,
                    report_title, category, is_report)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (file_id, filename, orig_name, 1 if is_public else 0,
                 "bulk-upload", description, title, category),
            )
            print(f"  [{vis:7}] {title}")

        uploaded += 1

    if not args.dry_run:
        db.commit()
        db.close()

    print(f"\n{'=' * 60}")
    print(f"Results: {uploaded} uploaded, {skipped} skipped, {missing} missing")
    print(f"\nBy category:")
    for cat, stats in sorted(cat_stats.items()):
        print(f"  {cat:35} {stats['count']:3} files ({stats['public']} public, {stats['private']} private)")


if __name__ == "__main__":
    main()
