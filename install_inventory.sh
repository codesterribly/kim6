#!/usr/bin/env bash
# Authoritative KIM6 installation inventory, sourced by install/uninstall.
# Rows are checkout source | runtime destination | installed mode.
# Menus are rendered and translations compiled separately; never recursively copy.
menu_names=(
  kim_compressandresize.desktop
  kim_compressandresizevideo.desktop
  kim_video_h264.desktop
  kim_video_av1.desktop
  kim_convertandrotate.desktop
  kim_information.desktop
  kim_metadata.desktop
  kim_location.desktop
  kim_publication.desktop
  kim_recipes.desktop
  kim_videoutilities.desktop
  kim_webemail.desktop
)
languages=(de es fr hu it nl zh_TW)
legacy_names=(kim_album kim_compress kim_convert kim_flipflop kim_galery kim_multiburst
  kim_other kim_collage kim_print kim_rename kim_resize kim_resizeandsend kim_rotate
  kim_rotatewithexif kim_sortbydate kim_stripmeta kim_treatment kim_video kim_webexport)
obsolete_menu_names=(kim_compress.desktop kim_organize.desktop)
runtime_sources=()
runtime_files=()
runtime_modes=()
while IFS='|' read -r source destination mode; do
  runtime_sources+=("$source")
  runtime_files+=("$destination")
  runtime_modes+=("$mode")
done <<'KIM6_RUNTIME_FILES'
src/bin/kim_all|bin/kim_all|0755
src/bin/kim_image_ops.py|bin/kim_image_ops.py|0644
src/bin/kim_image_ops_dialog.py|bin/kim_image_ops_dialog.py|0644
src/bin/kim_annotations.py|bin/kim_annotations.py|0644
src/bin/kim_extensions_dialog.py|bin/kim_extensions_dialog.py|0644
src/bin/kim_preview.py|bin/kim_preview.py|0644
src/bin/kim_filename.py|bin/kim_filename.py|0644
src/bin/kim_ui.py|bin/kim_ui.py|0644
src/bin/kim_date_tools.py|bin/kim_date_tools.py|0644
src/bin/kim_date_dialog.py|bin/kim_date_dialog.py|0644
src/bin/kim_dates_unified.py|bin/kim_dates_unified.py|0644
src/bin/kim_location.py|bin/kim_location.py|0644
src/bin/kim_location_dialog.py|bin/kim_location_dialog.py|0644
src/bin/kim_location_ui.py|bin/kim_location_ui.py|0644
src/bin/kim_photo_selection.py|bin/kim_photo_selection.py|0644
src/bin/kim_location_map.py|bin/kim_location_map.py|0644
src/bin/kim_job.py|bin/kim_job.py|0644
src/bin/kim_job_process.py|bin/kim_job_process.py|0644
src/bin/kim_action_dialog.py|bin/kim_action_dialog.py|0644
src/bin/kim_recipe_menu.py|bin/kim_recipe_menu.py|0644
src/bin/kim_desktop_exec.py|bin/kim_desktop_exec.py|0644
src/bin/kim_recipe_run.py|bin/kim_recipe_run.py|0644
src/bin/kim_recipe_core.py|bin/kim_recipe_core.py|0644
src/bin/kim_recipe_image.py|bin/kim_recipe_image.py|0644
src/bin/kim_recipe_dates.py|bin/kim_recipe_dates.py|0644
src/bin/kim_psd_source.py|bin/kim_psd_source.py|0644
src/bin/kim_source_advisories.py|bin/kim_source_advisories.py|0644
src/bin/kim_recipe_dialog.py|bin/kim_recipe_dialog.py|0644
src/recipes/builtins.json|recipes/builtins.json|0644
src/bin/kim_png_metadata.py|bin/kim_png_metadata.py|0644
src/bin/kim_jpeg_webp_metadata.py|bin/kim_jpeg_webp_metadata.py|0644
src/bin/kim_gif_metadata.py|bin/kim_gif_metadata.py|0644
src/bin/kim_tiff_verify.py|bin/kim_tiff_verify.py|0644
src/bin/kim_isobmff_verify.py|bin/kim_isobmff_verify.py|0644
src/gallery/index.part1|gallery/index.part1|0644
src/gallery/index.part2|gallery/index.part2|0644
ABOUT|ABOUT|0644
LICENSE.md|LICENSE.md|0644
src/bin/kim_collage_dialog.py|bin/kim_collage_dialog.py|0644
src/bin/kim_contactsheet_dialog.py|bin/kim_contactsheet_dialog.py|0644
src/bin/kim_video_dialog.py|bin/kim_video_dialog.py|0644
src/bin/kim_album_dialog.py|bin/kim_album_dialog.py|0644
src/bin/kim_settings_dialog.py|bin/kim_settings_dialog.py|0644
src/bin/kim_manual_viewer.py|bin/kim_manual_viewer.py|0644
src/bin/kim_create_dialog.py|bin/kim_create_dialog.py|0644
INSTALL.md|INSTALL.md|0644
README.md|README.md|0644
docs/ACTIONS.md|docs/ACTIONS.md|0644
docs/FORMATS.md|docs/FORMATS.md|0644
docs/DEVELOPMENT.md|docs/DEVELOPMENT.md|0644
docs/commandconfig.md|docs/commandconfig.md|0644
docs/index.html|docs/index.html|0644
docs/work.css|docs/work.css|0644
docs/reference/ABOUT.html|docs/reference/ABOUT.html|0644
docs/reference/ACTIONS.html|docs/reference/ACTIONS.html|0644
docs/reference/commandconfig.html|docs/reference/commandconfig.html|0644
docs/reference/DEVELOPMENT.html|docs/reference/DEVELOPMENT.html|0644
docs/reference/FORMATS.html|docs/reference/FORMATS.html|0644
docs/reference/INSTALL.html|docs/reference/INSTALL.html|0644
docs/reference/LICENSE.html|docs/reference/LICENSE.html|0644
docs/reference/README.html|docs/reference/README.html|0644
docs/images/kim6-photo-actions.png|docs/images/kim6-photo-actions.png|0644
docs/images/kim6-video-conversion.png|docs/images/kim6-video-conversion.png|0644
docs/images/kim6-video-utilities.png|docs/images/kim6-video-utilities.png|0644
docs/images/kim6-settings-dialog.png|docs/images/kim6-settings-dialog.png|0644
docs/images/kim6-collage-dialog.png|docs/images/kim6-collage-dialog.png|0644
docs/images/kim6-animated-gif-dialog.png|docs/images/kim6-animated-gif-dialog.png|0644
docs/reference/RECIPES.html|docs/reference/RECIPES.html|0644
docs/images/kim6-recipes-menu.png|docs/images/kim6-recipes-menu.png|0644
docs/images/kim6-recipe-editor.png|docs/images/kim6-recipe-editor.png|0644
docs/images/kim6-convert-menu.png|docs/images/kim6-convert-menu.png|0644
docs/images/kim6-metadata-menu.png|docs/images/kim6-metadata-menu.png|0644
docs/images/kim6-settings-general.png|docs/images/kim6-settings-general.png|0644
src/bin/kim_process.py|bin/kim_process.py|0644
src/bin/kim_settings_file.py|bin/kim_settings_file.py|0644
KIM6_RUNTIME_FILES

# Phase 2: review-before-processing UI for video transcode presets.
# Keep the source, installed path and mode arrays index-aligned.
runtime_sources+=("src/bin/kim_video_review.py")
runtime_files+=("bin/kim_video_review.py")
runtime_modes+=("0644")
# Phase 2: Web Export review-before-processing dialog.
runtime_sources+=("src/bin/kim_webexport_review.py")
runtime_files+=("bin/kim_webexport_review.py")
runtime_modes+=("0644")
