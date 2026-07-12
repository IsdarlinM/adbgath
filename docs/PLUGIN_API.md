# Plugin API

## Discovery

Plugins are Python packages exposing the `adbgath.plugins` entry-point group.

Example package metadata:

```toml
[project.entry-points."adbgath.plugins"]
example = "example_plugin:ExamplePlugin"
```

## Interface

```python
class ExamplePlugin:
    name = "example-observer"
    version = "1.0.0"
    permissions = ("read_device", "filesystem")

    def check_requirements(self) -> list[str]:
        return []

    def execute(self, context) -> dict:
        return {
            "serial": context.serial,
            "package": context.package,
            "result": "observation complete",
        }
```

Allowed permissions:

- `read_device`
- `write_device`
- `network`
- `filesystem`

Unknown permissions, invalid names, and duplicate plugin names are rejected during discovery.

## Execution

```bash
adbgath plugin list
adbgath --device SERIAL plugin run example-observer \
  --allow-permission read_device \
  --allow-permission filesystem
```

Every declared permission must be approved explicitly. A plugin runs as local Python code and is therefore trusted code; permission declarations improve transparency but are not an operating-system sandbox.

## Recommendations

- Keep plugins small and deterministic.
- Use `context.service` instead of invoking ADB through a shell.
- Validate package names and paths through core helpers.
- Return JSON-serializable dictionaries.
- Declare all device, network, and filesystem effects.
- Avoid credential collection, persistence, evasion, or operations outside authorized scope.
