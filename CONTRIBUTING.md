# Contributing to KIMng

KIMng is an open-source image and video workflow toolkit for
KDE Plasma 6 and Dolphin.

Contributions should preserve existing workflows, protect user files
and remain consistent with native KDE desktop behavior.

## Report a bug

Use the project's
[GitHub Issues](https://github.com/codesterribly/kim6/issues).

Include:

- The KIMng version or Git commit.
- Linux distribution and KDE Plasma, Frameworks and Dolphin versions.
- The affected action, selected options and input format.
- Steps that reproduce the problem.
- Expected behavior and actual behavior.
- Relevant error output.
- Relevant ImageMagick, ExifTool or FFmpeg versions when applicable.

Use synthetic or safely redacted example files whenever possible.
Do not publish private photographs, precise GPS coordinates,
personal filesystem paths or confidential metadata.

For security vulnerabilities, follow the security reporting policy
in `SECURITY.md`.

## Development

Use the current development source from the project repository.
Read `docs/DEVELOPMENT.md` before modifying application behavior.

Keep changes focused on the problem being solved.
Avoid unrelated refactoring and unnecessary dependencies.

KIMng uses Bash, Python, PySide6 and existing Linux media tools.
Reuse established processing and graphical helpers where appropriate.

## File safety

Changes must preserve the safeguards of the affected operation.

- Do not silently overwrite original files.
- Preserve explicit overwrite authorization.
- Validate generated output before publication.
- Protect existing destination files.
- Respect approved filenames and destination plans.
- Preserve cancellation behavior.
- Do not silently substitute formats or encoders.
- Keep read-only metadata inspection and planning free of write operations.

Use temporary files and generated fixtures for development and testing.
Do not use irreplaceable photographs or videos as test fixtures.

## Graphical interface

Use native Qt and KDE-compatible controls.
Keep wording concise and consistent with existing KIMng actions.
Use US English source strings.

An ellipsis indicates that the action requires additional user input
or configuration. A read-only viewer or predetermined action does
not require an ellipsis solely because it opens a window or review.

Changes to service-menu definitions must also update the corresponding
action inventory and gettext template.

## Verification

Run focused tests for the affected behavior:

    python3 -B tests/run.py --pattern test_resize.py

Replace the example pattern with the relevant test module.

Run the documentation checks:

    python3 -B tests/run.py --pattern test_documentation.py
    python3 -B tests/test_installation_inventory.py -v
    python3 -B tools/build_manual.py --check

For changes to shell scripts, perform Bash syntax checks and relevant
ShellCheck validation.

Before submitting a change, run:

    git diff --check

Graphical and service-menu changes should also be verified in an actual
KDE Plasma and Dolphin environment. Headless tests alone do not
establish that the desktop workflow behaves correctly.

Do not weaken existing tests merely to make a change pass.
Explain intentional behavior changes and update their tests accordingly.

## Documentation

Update the relevant Markdown source whenever a user-facing action,
option, limitation or workflow changes.

Regenerate HTML references with:

    python3 -B tools/build_manual.py

Do not edit the generated HTML reference pages directly.
The illustrated landing page is maintained separately.

For changes to translatable source strings, regenerate the template:

    python3 -B tools/extract_messages.py

Include relevant generated files with the corresponding source changes.

## Submitting changes

Provide a clear explanation of the problem, the proposed change,
its scope and the verification performed.

Identify any untested behavior or known limitations.

Preserve historical copyright notices and existing license headers.
Contributions must be compatible with the project's GPL license.

See `LICENSE.md` and `ABOUT` for licensing and historical attribution.
