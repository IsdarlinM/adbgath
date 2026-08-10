# ADBGath 3.7.2 exception-hardening audit

This audit focuses on failures that could escape as raw tracebacks, terminate a public entrypoint unexpectedly, or turn malformed operator input into an unclassified server exception.

## Corrected boundaries

- Starlette route wrappers now tolerate `Mount` and other route objects without a callable `endpoint`.
- Remote first-run setup no longer assumes every route exposes `endpoint`/`dependant`.
- WebSocket cleanup and session-expiry wrappers skip non-endpoint mounted routes safely.
- `adbgath` contains unexpected runtime failures at the CLI process boundary; `--verbose` remains available for diagnostic tracebacks.
- `adbgath-web` now has the same controlled process boundary.
- Non-zero Uvicorn startup exits become normal ADBGath startup errors.
- Recoverable Web initialization failures (filesystem, SQLite registry, expected runtime initialization failures) are classified as ADBGath errors.
- ADB process-start `OSError` failures are normalized to `CommandExecutionError` for text, binary, and streaming commands.
- Malformed ADB PID output used by logcat package filtering is normalized to `CommandExecutionError`.
- Wireless, metrics, inventory and QR numeric values no longer rely on raw `int(...)` conversions.
- Lab nested payloads must be JSON objects and malformed JSON is rejected as validation input.
- Advanced audit/Lab limits are normalized before legacy dispatchers parse them.
- Plugin signing, verification, publisher trust and Lab PKI file/format failures are classified into validation or operational errors.
- Every Web operation remains allowlisted and the shared payload validator rejects unknown fields before dispatch.
- Background jobs already contain worker exceptions and persist terminal `failed` state; this behavior is retained.

## Error classification policy

- **Validation/input error:** reject with `ValidationError` / HTTP 4xx.
- **Expected operational failure:** use `AdbgathError`, `DependencyError`, or `CommandExecutionError`.
- **Programming defect:** keep distinguishable as an unexpected internal error. Raw traceback is hidden by default at the public CLI boundary but remains available with `adbgath --verbose ...`.
- **Background job failure:** persist `failed` state and error details without terminating the server.

## Regression coverage added

- real FastAPI construction with the `/static` Starlette `Mount` that caused the Termux crash;
- secure and `--insecure-http` remote serve construction using the real ADBGath application and mocked Uvicorn runner;
- synthetic `/ws/` mounts against WebSocket wrappers;
- malformed Lab HTTP payload => HTTP 422;
- CLI expected/unexpected exception containment;
- direct `adbgath-web` exception containment;
- Uvicorn non-zero exit normalization;
- ADB subprocess startup failures;
- malformed ADB logcat PID responses;
- Wireless/metrics/inventory/QR numeric validation;
- advanced Lab/plugin/PKI input failures;
- unknown-field rejection across the complete registered Web operation catalog.

The full GitHub Actions matrix should still be run when account-level runner billing is available.