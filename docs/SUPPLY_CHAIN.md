# ADB-Gath supply-chain controls

ADB-Gath 3.6 includes runtime CycloneDX/SPDX SBOM generation and release workflows for package provenance.

```bash
adbgath sbom --format cyclonedx --output adbgath.cdx.json
adbgath sbom --format spdx --output adbgath.spdx.json
```

The release workflow builds source/wheel distributions and requests GitHub artifact provenance through `actions/attest-build-provenance` when GitHub Actions is available. Release signing certificates and Windows Authenticode keys are intentionally not committed to the repository.

For production releases:

1. Protect `main` and release tags.
2. Require CI, dependency review, and security review.
3. Create the release from a clean tag.
4. Verify generated SBOMs and artifact attestations.
5. Sign Windows installers with an organization-controlled code-signing certificate outside the source tree.
6. Publish SHA-256 checksums with the release.
7. Retain the previous stable installer/workspace migration path for rollback.
