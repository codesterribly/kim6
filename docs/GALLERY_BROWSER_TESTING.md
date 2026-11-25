# Repeatable gallery browser verification

Run the focused regressions and generated-gallery Chrome checks from the
repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_gallery_verification.py
```

In Codex, use the per-command elevated execution approval flow and approve the
runner invocation. A restricted workspace sandbox can prevent Chrome crashpad
from starting with `setsockopt: Operation not permitted`; per-command approval
runs this check in an execution context where Chrome and DevTools can start,
without changing persistent sandbox settings. Do not add `--no-sandbox` or
weaken system security.

The runner executes publication/editor/protected-preview/viewer regressions,
then launches the existing viewer interactions and generated visual-QA matrix
in Chrome. The matrix regenerates galleries from the current renderer for
Simple Light, Simple Dark, Modern, Classic, and Dramatic at 1920×1080,
1440×900, 768×1024, 390×844, and 375×812. It checks computed contrast,
image/text rectangles and aspect ratios, Fit and zoom geometry, keyboard and
button navigation, focus and scroll restoration, heading hierarchy, horizontal
overflow, and browser exceptions.

The runner requires these twelve screenshots under the reported
`/tmp/kim-gallery-browser-artifacts-*` directory:

- Modern hero at desktop and mobile sizes.
- Modern portrait and widescreen image/description layouts at desktop and
  mobile sizes.
- Portrait Fit and 2× zoom viewer states at desktop and mobile sizes.
- Simple Dark contrast at desktop and mobile sizes.

Every required artifact must exist and have a PNG header and nonzero image
dimensions. Missing, empty, or malformed artifacts fail the runner. Browser
startup and DevTools problems are errors; dependency or browser skips never
count as a pass. Fixture HTML, generated CSS, fixture images, and Chrome profile
are temporary; screenshots remain in `/tmp` for visual review.
