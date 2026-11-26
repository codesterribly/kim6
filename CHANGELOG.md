# KIMng Changelog

## Unreleased

This section summarizes the current KIMng development source.
It is not a stable release announcement or a version designation.

### KDE integration and application identity

- Modernized KDE Image Menu workflows for KDE Plasma 6 and Dolphin.
- Introduced the KIMng application identity.
- Consolidated active actions behind the `kim_all` dispatcher.
- Standardized service-menu wording, dialog titles and action organization.
- Added a shared standalone and embedded offline User Guide.

### Image processing

- Added reviewed resize, crop, rotation and flip workflows.
- Added configurable resize geometry, enlargement and resampling controls.
- Expanded conversion and compression options with runtime encoder checks.
- Added format-impact warnings and operation-specific validation.
- Added PDF page rendering and embedded-image extraction.
- Preserved explicit protections against unsupported animation handling
  and silent frame loss.

### Recipes

- Added reusable, derivative-only image-processing workflows.
- Added a Recipe Editor, Runner, built-in Web Export recipe,
  descriptions, search and folder organization.
- Added schema 3 recipe import and export, including library bundles.
- Added planned-output inspection, destination overrides and
  preflight collision handling.
- Added direct Dolphin shortcuts for eligible saved user recipes.

### Metadata and location

- Added the read-only Metadata Browser and two-image comparison.
- Added the read-only Metadata Editor change planner.
- Added source-representation inspection and configurable metadata
  display priorities.
- Integrated shared GPS map viewing and metadata proposal controls.
- Improved dedicated metadata, copyright, date and GPS workflows.

General Metadata Editor writing, transactional batch updates and
CSV-driven metadata writing remain outside the current implemented
Editor scope.

### Publishing and video

- Expanded gallery, collage, contact sheet and PDF publication workflows.
- Added Gallery Publishing with classic Image gallery and Photo story
  workflows.
- Added story sections, multiple layouts, single-page and multiple-page
  output, local folder publication and ZIP publication.
- Retained video conversion and extraction workflows with
  runtime encoder and stream validation.

### Installation and documentation

- Established a shared installation inventory.
- Added independent packaging completeness and dependency-closure checks.
- Hardened installation recovery and ownership verification.
- Added installer progress, terminal-aware colors, compact summaries
  and verbose output.
- Verified installation, reinstallation and uninstallation while
  preserving unrelated files.
- Expanded the User Guide, CLI reference, format documentation
  and development instructions.
- Preserved historical project attribution and GPL licensing.

### Known limitations

- General Metadata Editor proposals do not write metadata.
- Format availability depends on the selected operation,
  installed encoders and validation requirements.
- Some advanced workflows and format combinations remain unsupported.
- Final application screenshots and release verification are pending.

## Historical changes

The original `ChangeLog` file remains in the repository.
It has been preserved separately from this KIMng development summary.

See the repository commit history for individual implementation changes.
