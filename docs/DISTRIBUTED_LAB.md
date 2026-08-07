# ADB-Gath 3.6 Distributed Lab

ADB-Gath remains local-first. Distributed Lab is an optional control plane for authorized Windows/Linux workers attached to Android devices or emulators.

## Trust model

- Controller/agent transport uses mutual TLS.
- Every agent also receives a random one-time enrollment token; the controller stores only its SHA-256 hash.
- Agents initiate outbound HTTPS requests. No inbound agent listener is required.
- The protocol has no shell, command string, or arbitrary ADB endpoint.
- Jobs reference the shared ADB-Gath operation catalog and are checked by RBAC before queueing and again before delivery.
- Destructive operations require explicit approval.
- Agent tokens and private keys are never returned by normal inventory/status APIs.

## PKI

```bash
adbgath lab pki-init --dir ./lab-pki
adbgath lab controller-cert --dir ./lab-pki --host 127.0.0.1
```

The CA and leaf certificates use ECDSA P-256, SHA-256 signatures, Subject Key Identifiers, Authority Key Identifiers, Extended Key Usage, and SANs for controller hosts.

## Agent enrollment

```bash
adbgath lab agent-enroll windows-lab-01 \
  --pki-dir ./lab-pki \
  --controller https://controller.example:9443
```

This creates a client certificate, private key, and an agent JSON configuration containing the one-time token. Protect this file as a credential.

## Controller

```bash
adbgath lab controller \
  --host 0.0.0.0 \
  --port 9443 \
  --cert ./lab-pki/controller-adbgath-controller-cert.pem \
  --key ./lab-pki/controller-adbgath-controller-key.pem \
  --ca ./lab-pki/ca-cert.pem
```

The TLS listener requires a client certificate signed by the configured CA.

## Worker

```bash
adbgath lab agent-run --config ./lab-pki/agent-windows-lab-01.json
```

Use `--once` for integration or scheduled health checks.

## Roles

- `viewer`: status, inventories, reports, metrics, and other read-only functions.
- `analyst`: viewer plus evidence collection and analysis.
- `operator`: analyst plus device-changing operations when explicitly approved.
- `administrator`: all catalogued operations, still subject to remote-operation deny rules.

Even administrators cannot remotely dispatch the updater, Web server, controller/agent daemon controls, or arbitrary plugin installation.

## Jobs

```bash
adbgath lab job-submit --agent windows-lab-01 --action devices --role viewer
adbgath lab job-submit --agent windows-lab-01 --action security --role analyst
adbgath lab job-submit --agent windows-lab-01 --action install --payload '{"files":["C:/lab/test.apk"]}' --role operator --approved
adbgath lab jobs
```

## Audit

```bash
adbgath audit list
adbgath audit verify
```

Every event links to the previous event hash. Verification fails if stored audit content is modified.

## Evidence store

The 3.6 object store deduplicates identical evidence by SHA-256. Project/session references are stored separately. Garbage collection removes only unreferenced objects and is dry-run by default.

## Web UI

Run `adbgath web` and open `/lab`. The page exposes non-secret agent inventory, jobs, policy evaluation, artifact integrity, and audit-chain status. Credential/private-key creation and long-running controller/agent daemons remain CLI-only security-boundary operations.
