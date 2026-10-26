# Configuration reference

KConfig is read from `${KIM_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu}`, group `<default>`. When both an environment setting and its corresponding KConfig value are present, the environment value takes precedence. The dispatcher reads supported KConfig values only when it starts. Most action options can also be supplied directly on the command line and take precedence for that invocation.

`KIM_POLICY` is the only output-policy setting. KIM6 does not define `KIM_MODE` or a legacy policy alias.

| Environment variable | KConfig key | Purpose / accepted values | Default | Invalid or empty behavior | Applicable actions |
|---|---|---|---|---|---|
| `KIM_CONFIG_FILE` | — | Path to the KConfig file used for KIM6 settings | `${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu` | If absent, use the default path. If unreadable/unavailable, KConfig values are unavailable and action defaults apply. | All settings below |
| `KIM_POLICY` | `KIM_POLICY` | `create` or `overwrite` | No fixed choice; prompt | Unsupported values do not authorize either mode and leave the action’s normal create/overwrite choice available. | Actions with a create/overwrite policy; derived-only actions ignore overwrite authorization for source replacement. |
| `KIM_NAME_AFFIX_POSITION` | `NAME_AFFIX_POSITION` | `prefix` or `suffix` for generated filename tags | `suffix` | Only exact `prefix` moves the tag before the complete stem; other values behave as suffix. KConfig accepts only the two documented values. | Compression, resize, web export, full metadata stripping |
| `KIM_WEB_QUALITY` | `WEB_EXPORT_QUALITY` | JPEG/Web quality default, integer 1–100 | `75` | Invalid KConfig values fall back to 75. Invalid environment values are presented as the dialog default and are rejected by quality validation if submitted. Explicit `--quality` is validated per invocation. | Web export |
| `KIM_WEB_FORMAT` | `WEB_EXPORT_FORMAT` | `jpg`, `jpeg`, `webp`, `avif`, `keep` | `jpg` | Invalid KConfig values fall back to `jpg`; invalid environment/CLI values fail web export. `keep` retains the supported source format. | Web export |
| `KIM_WEB_COLOR_MODE` | `WEB_COLOR_MODE` | `srgb` or `preserve` | `srgb` | Invalid KConfig values fall back to `srgb`; invalid environment/CLI values fail the action. | Web export |
| `KIM_COPYRIGHT_CREATOR` | `COPYRIGHT_CREATOR` | Default creator/artist text | Empty | Empty means no configured default; an empty interactive field leaves the tag unchanged. | Copyright metadata editing |
| `KIM_COPYRIGHT_NOTICE` | `COPYRIGHT_NOTICE` | Default copyright notice; may contain `{YEAR}` | Empty | Empty means no configured default; no tag is cleared by an empty form field. | Copyright metadata editing |
| `KIM_COPYRIGHT_USAGE_RIGHTS` | `COPYRIGHT_USAGE_RIGHTS` | Default usage-rights text | Empty | Empty means no configured default; an empty form field leaves the tag unchanged. | Copyright metadata editing |
| `KIM_GIF_DELAY` | — | Default animation delay in centiseconds, integer 0–65535 | `100` (one second) | Used as the interactive dialog’s initial value. The chosen value is range-checked before processing. | Still-image `animate` only |

Example user configuration (`~/.config/kim_kdeimagemenu`):

```ini
[<default>]
KIM_POLICY=create
NAME_AFFIX_POSITION=suffix
WEB_EXPORT_QUALITY=75
WEB_EXPORT_FORMAT=jpg
WEB_COLOR_MODE=srgb
COPYRIGHT_CREATOR=Example Photographer
COPYRIGHT_NOTICE=Copyright © {YEAR} Example Photographer
COPYRIGHT_USAGE_RIGHTS=
```

The group is literally named `<default>`. Environment overrides can be set in the environment that launches Dolphin, or for a single terminal command:

```sh
KIM_POLICY=create KIM_NAME_AFFIX_POSITION=prefix kim_all resize --size 1600x1600 -- photo.jpg
KIM_WEB_COLOR_MODE=preserve kim_all webexport --size 1600x1600 -- photo.jpg
```

## Policy and naming details

- Unset policy prompts for create versus overwrite where the action supports both. Configured `create` selects collision-safe new names; configured `overwrite` is authorization only for actions that explicitly support replacing their target.
- `webexport`, email preparation, video utilities and slideshow generation are derived-only. `KIM_POLICY=overwrite` never authorizes replacement of a selected source in those workflows.
- Prefix/suffix position affects only the complete stem, never the extension. Collision numbering remains before the extension. Rename is unaffected.
- CLI size, quality, format, color, codec and other action-specific options override defaults for that call.

See [SAFETY.md](SAFETY.md) for per-action timestamp and metadata distinctions.
