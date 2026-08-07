# ADB-Gath roadmap: 3.5 and 3.6

This roadmap defines scope, architecture, performance budgets, security gates, compatibility requirements, and release criteria for the next two versions. Branding is explicitly out of scope unless separately authorized.

## Version 3.5 — native async core and evidence efficiency

### Product goal

Turn the 3.4 event-driven wireless foundation into a unified asynchronous execution core, reduce storage and process overhead, and correlate static and runtime mobile-security evidence without increasing unsafe automation.

### Planned capabilities

1. **Unified asynchronous subprocess supervisor**
   - one lifecycle API for ADB, Frida, bundletool, logcat, bugreport, screenrecord, pulls, and packet capture;
   - process-tree termination on Windows and POSIX;
   - bounded stdout/stderr queues and backpressure;
   - pause/cancel/timeout/cleanup states;
   - per-device concurrency locks and global worker limits.

2. **Content-addressed artifact store**
   - SHA-256 object storage and deduplication;
   - project/session references instead of duplicate files;
   - optional compression for text, bugreports, and PCAPs;
   - atomic writes, reference counting, garbage collection, and export reconstruction;
   - migration from existing workspace paths with rollback.

3. **Native modularization**
   - remove transitional compatibility wrappers;
   - split service domains into typed interfaces;
   - typed Pydantic request/result models for every Web operation;
   - one generated operation schema for CLI, Web forms, help, and documentation.

4. **Incremental inventory engine**
   - broker-triggered inventory refresh after device/package events;
   - package version, certificate, split, permission, component, proxy, SELinux, and boot-state deltas;
   - change subscriptions and configurable retention;
   - stable hashes per inventory section to avoid re-reading unchanged domains.

5. **Static/runtime correlation**
   - correlate exported components with runtime reachability evidence;
   - correlate deep links with resolved activities;
   - correlate Network Security Configuration with observed connections;
   - correlate manifest permissions with actual grants and AppOps;
   - merge duplicate evidence into one finding with confidence and provenance.

6. **Web performance work**
   - virtualized package, finding, artifact, and log tables;
   - Web Workers for large JSON/diff/report preparation;
   - incremental DOM updates from broker events;
   - reconnecting WebSockets with exponential backoff and sequence replay;
   - accessible keyboard navigation and responsive mobile layouts.

### Performance budgets

- warm Web bootstrap: under 500 ms excluding unavailable-device timeout;
- device list update after broker event: under 250 ms;
- memory growth during 100,000 logcat lines: under 75 MiB;
- cancellation acknowledgement: under 750 ms for local child processes;
- unchanged inventory capture: at least 60% fewer ADB commands than a full capture;
- artifact deduplication: no duplicate object bytes for identical SHA-256 content.

### Success gates

- unit, integration, property, concurrency, and cancellation tests;
- Windows 10/11 and Ubuntu/Kali installation tests;
- Android 11–16 physical-device wireless matrix;
- migration/rollback tests from 3.2.9, 3.3.0, and 3.4.0 workspaces;
- performance regression suite with stored baselines;
- zero unresolved high-severity dependency or code-scanning findings;
- release candidate used in a controlled multi-device lab before `main` promotion.

## Version 3.6 — secure distributed mobile-security lab

### Product goal

Extend ADB-Gath from a single-host workspace into an optional distributed lab controller while preserving local-first defaults, explicit authorization, and the prohibition on arbitrary remote shells.

### Planned capabilities

1. **Remote lab agents**
   - Windows and Linux agents with mTLS identities;
   - explicit enrollment and certificate rotation;
   - outbound-only controller connection where possible;
   - operation allowlists and per-agent capability declarations;
   - no general command shell or arbitrary ADB command endpoint.

2. **RBAC and policy engine**
   - roles for viewer, analyst, operator, and administrator;
   - device, project, operation, and evidence-level authorization;
   - policy-as-code for destructive operations, retention, export, and remote access;
   - two-step approval for high-impact actions when enabled.

3. **Signed plugin and rule ecosystem**
   - signed manifests and publisher identity;
   - permission, dependency, compatibility, and checksum declarations;
   - isolated execution boundary for third-party plugins;
   - trusted repository plus offline bundle installation;
   - revocation and minimum-version controls.

4. **Lab orchestration**
   - device pools, leases, health checks, and scheduling;
   - topology view and transport-aware routing;
   - reproducible assessment pipelines with immutable inputs;
   - result aggregation, retry policies, and partial-failure handling;
   - Android emulator and physical-device workers.

5. **Enterprise evidence governance**
   - encryption at rest for sensitive projects;
   - configurable retention and legal-hold flags;
   - signed chain-of-custody manifests;
   - append-only audit trail with integrity verification;
   - scoped export tokens and optional external object storage.

6. **Supply-chain hardening**
   - reproducible wheels and installers;
   - CycloneDX/SPDX SBOM;
   - Sigstore attestations and SLSA provenance;
   - signed tags, checksums, and Windows installer signing;
   - OpenSSF Scorecard and dependency review gates.

### Reliability and security objectives

- controller availability target: 99.9% in supported deployments;
- no loss of accepted job state during controller restart;
- agent reconnect with bounded exponential backoff;
- all agent/controller traffic authenticated and encrypted;
- certificate/key material never included in project exports;
- complete audit event for every remote operation and policy decision;
- upgrade and rollback without deleting projects, evidence, or agent enrollment state.

### Success gates

- independent threat model and security review before beta;
- mTLS, RBAC, replay, enrollment, revocation, and authorization tests;
- chaos tests for network partitions, agent loss, duplicate delivery, and controller restart;
- compatibility tests across mixed 3.6 agent patch versions;
- load test with at least 50 agents and 200 registered devices;
- signed release provenance verified in CI and installer;
- staged alpha, controlled beta, and rollback rehearsal before `main` promotion.

## Delivery method for both releases

1. Define measurable acceptance criteria before implementation.
2. Develop behind stable interfaces and feature flags.
3. Maintain database and artifact migrations with backups and downgrade plans.
4. Run the full test matrix on every release candidate.
5. Compare performance and memory against the previous stable version.
6. Perform security review and dependency verification.
7. Publish to a release branch, validate a clean installation and upgrade, then fast-forward `main` only after all gates pass.
8. Keep the previous stable package and database backup available for rollback.
