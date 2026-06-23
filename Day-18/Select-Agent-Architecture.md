Scenario 1: ShopIQ – Personalized Product Recommendation Email
Architecture Choice:  Single Agent
Why Single Agent?

All activities use the same user context:

Purchase History
Browsing History
Recommendation Model
Business Rules
Email Generation
There is no need for specialized agents communicating with each other.
                 User Purchase History
                          +
                 User Browsing History
                          |
                          v

              +----------------------+
              |   Single Agent       |
              |    Orchestrator      |
              +----------+-----------+
                         |
                         v

              +----------------------+
              | Recommendation Model |
              | Collaborative Filter |
              +----------+-----------+
                         |
                         v

              +----------------------+
              | Business Rules       |
              | Remove Out of Stock  |
              | Remove Recent Buys   |
              +----------+-----------+
                         |
                         v

              +----------------------+
              | Copywriting Module   |
              | Personalized Intro   |
              +----------+-----------+
                         |
                         v

              +----------------------+
              | Email HTML Builder   |
              +----------+-----------+
                         |
                         v

                 Personalized Email


2- Apollo Diagnostics – Automated Radiology Report + Care Pathway
Choice: Multi-Agent

Reasons for Multi-Agent:

Four distinct domains.
Different tool access requirements.
Different failure modes.
Sequential approval gates.
Medical decisions require specialized validation.
Easier auditing and compliance.

                     Chest CT Scan
                            |
                            v

                 +--------------------+
                 | Radiology Agent    |
                 | Scan Interpretation|
                 +---------+----------+
                           |
                     Findings Report
                           |
                           v

                 +--------------------+
                 | Clinical Decision  |
                 | Support Agent      |
                 | Drug Interaction   |
                 | Contraindications  |
                 +---------+----------+
                           |
                    Validated Findings
                           |
                           v

                 +--------------------+
                 | Scheduling Agent   |
                 | EMR Integration    |
                 | Follow-up Booking  |
                 +---------+----------+
                           |
                    Appointment Details
                           |
                           v

                 +--------------------+
                 | Communication      |
                 | Agent              |
                 | GP Letter          |
                 | Patient Summary    |
                 +---------+----------+
                           |
                           v

                  Final Care Package

3- ContractIQ – M&A Due Diligence on 800 Contracts
Choice: Hybrid Multi-Agent Architecture

This is not a pure single-agent problem because:

800 contracts can be processed independently → massive parallelization opportunity.
Need jurisdiction-specific compliance checks.
Need cross-document dependency analysis.
Final output requires global synthesis across all contracts.
SLA is under 4 hours, making distributed processing essential.

                     800 Contracts
                            |
      ------------------------------------------------
      |            |            |            |
      v            v            v            v

+------------+ +------------+ +------------+ +------------+
| Extractor  | | Extractor  | | Extractor  | | Extractor  |
| Agent #1   | | Agent #2   | | Agent #3   | | Agent #N   |
+------------+ +------------+ +------------+ +------------+
       |             |             |               |
       ---------------------------------------------
                            |
                            v

              +---------------------------+
              | Compliance Review Agent   |
              | Jurisdiction Checks       |
              +-------------+-------------+
                            |
                            v

              +---------------------------+
              | Dependency Analysis Agent |
              | Cross-Contract Relations  |
              +-------------+-------------+
                            |
                            v

              +---------------------------+
              | Executive Summary Agent   |
              | Risk Heat Map             |
              +-------------+-------------+
                            |
                            v

                    Final Due Diligence
                         Report


4: CloudOps Sentinel – Incident Triage & Auto-Remediation
Choice: ✅ Multi-Agent Architecture
Why?

The problem explicitly states:

Metrics investigation (Datadog)
Deployment investigation (GitHub Actions)
Database investigation (AWS RDS)
Auto-remediation (Kubernetes)
Human approval gate
RCA generation

Different tools, different data sources, and parallel investigations make this a classic multi-agent workflow.
                        Alert Triggered
                               |
                               v

                    +------------------+
                    | Coordinator Agent|
                    +---------+--------+
                              |
        ------------------------------------------------
        |                      |                       |
        v                      v                       v

+----------------+   +----------------+   +----------------+
| Metrics Agent  |   | Deployment     |   | Database Agent |
| Datadog        |   | Agent          |   | AWS RDS        |
+----------------+   | GitHub Actions |   +----------------+
                     +----------------+
        \                  |                  /
         \                 |                 /
          -----------------------------------
                          |
                          v

                +----------------------+
                | Root Cause Agent     |
                | Correlation Engine   |
                +----------+-----------+
                           |
                     Confidence Score
                           |
              -------------------------
              |                       |
      Confidence >80%        Confidence <80%
              |                       |
              v                       v

+---------------------+      +---------------------+
| Remediation Agent   |      | Human Approval Gate |
| Rollback / Restart  |      +----------+----------+
+----------+----------+                 |
           |                            |
           ------------------------------
                         |
                         v

              +----------------------+
              | RCA Report Agent     |
              | Slack Notification   |
              +----------------------+