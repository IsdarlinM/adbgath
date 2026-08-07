# ADB-Gath 3.6 Security Model

## Distributed mode

Distributed Lab is disabled unless the operator explicitly starts a controller or agent. Controller transport requires mutual TLS and agent bearer authentication. Agents are outbound-only and execute only catalogued ADB-Gath operations.

## Authorization

RBAC decisions are evaluated before queueing and immediately before a remote job is delivered. Device-changing operations require explicit approval. The remote deny list excludes updater, Web server, controller/agent management and raw extension-management operations.

## Secrets

Pairing codes, QR secrets, lab private keys, agent bearer tokens and plugin private signing keys must never be included in project exports, metrics, audit details or normal API listings. Agent tokens are stored controller-side only as SHA-256 hashes.

## Evidence integrity

Content-addressed objects are keyed by SHA-256 and verified after materialization. Audit events form a hash chain. Existing project evidence manifests remain available for per-collection hashing/signing.

## Plugin trust

3.6 adds Ed25519 signing and verification for plugin files and manifests. Signature verification does not itself grant plugin permissions; the existing plugin permission approval remains mandatory.
