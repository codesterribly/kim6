# KIMng Security Policy

## Development status

KIMng is under active development.

This policy does not announce a stable supported release, a guaranteed
support period or a vulnerability remediation service-level agreement.

## Report a vulnerability

Security concerns can include:

- Unintended modification or loss of source files.
- Unauthorized replacement of existing destination files.
- Unsafe symbolic-link or filesystem alias handling.
- Command injection through filenames or metadata.
- Unsafe processing of malformed image, video or document files.
- Disclosure of private metadata or GPS coordinates.
- Installation or removal of files outside KIMng's managed ownership.

Use the repository's Security section and private vulnerability
reporting facility if it is available:

https://github.com/codesterribly/kim6/security

If private reporting is unavailable, use GitHub Issues to request
a private reporting channel without publishing exploit details,
private files or sensitive information:

https://github.com/codesterribly/kim6/issues

Ordinary defects and feature requests belong in GitHub Issues.

## Information to include

Provide the affected commit or version, Linux distribution,
relevant dependency versions, the affected operation,
expected and actual behavior, and reproduction instructions.

Where possible, provide a synthetic or safely redacted test file.
Do not include private photographs, personal metadata, credentials,
unrelated filesystem contents or precise personal location information.

## Handling and disclosure

Allow the maintainer an opportunity to investigate a reported
vulnerability before publishing sensitive technical details.

There is no guaranteed response or correction timeframe.

KIMng relies on system libraries and external media-processing tools.
Vulnerabilities in those dependencies may also need to be reported
to their respective maintainers.

## Safe operation

Keep system media-processing tools and KDE components updated.

Do not disable ImageMagick security policies simply to make an
unsupported or untrusted document process successfully.

Review planned outputs before authorizing changes, and maintain
independent backups of important original files.

Metadata-stripping features are not guarantees of anonymity.
Inspect outputs before publishing or sharing sensitive images.

See `LICENSE.md` for the project's license and warranty provisions.
