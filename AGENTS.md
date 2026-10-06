# Development contract

Keep GATES.md current. Do not equate successful unit tests or dispatched UI input with native CapCut compatibility. Publish only after every required native gate passes.

Keep validations and business rules in Python backend modules. Wrap operational backend boundaries in try/catch using the shared backend decorator. Log technical errors to stderr; return generic unexpected errors in JSON. Keep explicit types and simple modules.

Use disposable projects for testing. Preserve existing projects, verify resolved paths before recursive removal, refuse linked project paths, back up before writes, and never force close an app from production commands. Do not upload credentials, raw application logs, device identifiers, user media or personal project data.

Maintain upstream attribution. Do not install or use the upstream .mcp.json; it is unrelated to the Windows bridge.
