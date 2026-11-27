"""Focused Milestone 1 tests for headless Parameterized Recipes (kim_recipe_params)."""
import copy
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'bin'))
sys.path.insert(0, str(ROOT / 'tests'))

import kim_recipe_core as core
import kim_recipe_params as params
from kim_recipe_core import RecipeError
from metadata_integrity import sha256_noatime


def base_recipe(steps, *, parameters=None, destination=None, recipe_id='param-test'):
    recipe = {
        'schema': core.AUTHORED_SCHEMA,
        'id': recipe_id,
        'name': 'Param Test',
        'description': 'Test parameterized recipe',
        'media': 'image',
        'steps': steps,
        'destination': destination or {'mode': 'beside'},
    }
    if parameters is not None:
        recipe['parameters'] = parameters
    return recipe


class RecipeParameterResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config_home = Path(self.temp.name) / 'config'
        self.config_home.mkdir()
        env_patch = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.config_home)})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        for key in (
            'KIM_COPYRIGHT_CREATOR',
            'KIM_COPYRIGHT_NOTICE',
            'KIM_COPYRIGHT_USAGE_RIGHTS',
            'KIM_WEB_QUALITY_JPEG',
            'KIM_WEB_QUALITY_WEBP',
            'KIM_WEB_QUALITY_AVIF',
        ):
            p = patch.dict(os.environ, {}, clear=False)
            p.start()
            os.environ.pop(key, None)
            self.addCleanup(p.stop)

    # 1. Ordinary authored fixed-value Recipe compiles cleanly to concrete schema 3.
    def test_01_ordinary_concrete_recipe_unchanged(self):
        recipe = core.builtins()[0]
        before = copy.deepcopy(recipe)
        expected_concrete = {**before, 'schema': core.CONCRETE_SCHEMA}
        self.assertFalse(params.is_parameterized(recipe))
        self.assertEqual(params.validate_authored(recipe), before)
        self.assertEqual(params.active_parameters(recipe), [])
        resolved = params.resolve_recipe(recipe)
        self.assertEqual(resolved, expected_concrete)
        self.assertEqual(core.validate(resolved), expected_concrete)
        self.assertEqual(recipe, before)

    # 2. One parameter binds to multiple operation fields.
    def test_02_shared_parameter_binds_multiple_fields(self):
        recipe = base_recipe(
            [
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'bindings': {'max_width': 'max_edge', 'max_height': 'max_edge'},
                },
                {
                    'op': 'image.resize_long_edge',
                    'pixels': 1600,
                    'upscale': False,
                    'bindings': {'pixels': 'max_edge'},
                },
            ],
            parameters=[
                {
                    'id': 'max_edge',
                    'label': 'Maximum edge',
                    'type': 'integer',
                    'minimum': 100,
                    'maximum': 8000,
                    'required': True,
                }
            ],
        )
        resolved = params.resolve_recipe(recipe, {'max_edge': 2048})
        self.assertEqual(resolved['steps'][0]['max_width'], 2048)
        self.assertEqual(resolved['steps'][0]['max_height'], 2048)
        self.assertEqual(resolved['steps'][1]['pixels'], 2048)
        self.assertNotIn('parameters', resolved)
        self.assertNotIn('bindings', resolved['steps'][0])
        core.validate(resolved)

    # 3. Required inputs without defaults are rejected.
    def test_03_required_inputs_without_defaults_rejected(self):
        recipe = base_recipe(
            [
                {
                    'op': 'image.convert',
                    'format': 'jpeg',
                    'quality': 95,
                    'bindings': {'quality': 'jpeg_quality'},
                },
                {'op': 'file.rename_output', 'pattern': '{param:project}_{filename}'},
            ],
            parameters=[
                {'id': 'jpeg_quality', 'label': 'JPEG quality', 'type': 'integer', 'required': True},
                {'id': 'project', 'label': 'Project', 'type': 'text', 'required': True},
            ],
        )
        with self.assertRaisesRegex(RecipeError, 'JPEG quality'):
            params.resolve_recipe(recipe, {'project': 'Alpine'})
        with self.assertRaisesRegex(RecipeError, 'Project'):
            params.resolve_recipe(recipe, {'jpeg_quality': 95})
        with self.assertRaisesRegex(RecipeError, 'Project'):
            params.resolve_recipe(recipe, {'jpeg_quality': 95, 'project': '   '})

    # 4. Valid literal defaults resolve correctly.
    def test_04_literal_defaults_resolve_correctly(self):
        recipe = base_recipe(
            [
                {
                    'op': 'image.rotate',
                    'degrees': 0,
                    'bindings': {'degrees': 'angle'},
                },
                {
                    'op': 'image.convert',
                    'format': 'jpeg',
                    'quality': 90,
                    'bindings': {'quality': 'q'},
                },
                {
                    'op': 'metadata.set_capture',
                    'mode': 'specific',
                    'datetime': '',
                    'timezone': 'unknown',
                    'fields': 'capture',
                    'bindings': {'datetime': 'taken_at'},
                },
            ],
            parameters=[
                {'id': 'angle', 'label': 'Angle', 'type': 'number', 'minimum': -360, 'maximum': 360, 'default': 12.5},
                {'id': 'q', 'label': 'Quality', 'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 95},
                {'id': 'taken_at', 'label': 'Capture date', 'type': 'capture_datetime', 'default': '2026-06-15 14:30:00'},
            ],
        )
        resolved = params.resolve_recipe(recipe)
        self.assertEqual(resolved['steps'][0]['degrees'], 12.5)
        self.assertEqual(resolved['steps'][1]['quality'], 95)
        self.assertEqual(resolved['steps'][2]['datetime'], '2026-06-15 14:30:00')
        core.validate(resolved)

    # 5. Application Settings defaults resolve correctly & freeze before review.
    def test_05_application_settings_defaults_resolve_and_freeze(self):
        settings_file = self.config_home / 'kimng' / 'settings.conf'
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            'KIM_COPYRIGHT_CREATOR=Studio Natacha\n'
            'KIM_WEB_QUALITY_JPEG=95\n',
            encoding='utf-8',
        )
        recipe = base_recipe(
            [
                {
                    'op': 'image.convert',
                    'format': 'jpeg',
                    'quality': 90,
                    'bindings': {'quality': 'q'},
                },
                {
                    'op': 'metadata.creator',
                    'bindings': {'value': 'artist'},
                },
            ],
            parameters=[
                {'id': 'q', 'label': 'Quality', 'type': 'integer', 'default_source': 'web.quality.jpeg'},
                {'id': 'artist', 'label': 'Artist', 'type': 'text', 'default_source': 'copyright.creator'},
            ],
        )
        resolved = params.resolve_recipe(recipe)
        self.assertEqual(resolved['steps'][0]['quality'], 95)
        self.assertEqual(resolved['steps'][1]['value'], 'Studio Natacha')

        # Mutating settings afterward must not alter the frozen concrete snapshot.
        settings_file.write_text(
            'KIM_COPYRIGHT_CREATOR=Changed Later\n'
            'KIM_WEB_QUALITY_JPEG=60\n',
            encoding='utf-8',
        )
        self.assertEqual(resolved['steps'][0]['quality'], 95)
        self.assertEqual(resolved['steps'][1]['value'], 'Studio Natacha')

        # Environment variable takes precedence over settings.conf.
        with patch.dict(os.environ, {'KIM_WEB_QUALITY_JPEG': '88'}):
            resolved_env = params.resolve_recipe(recipe)
            self.assertEqual(resolved_env['steps'][0]['quality'], 88)

    # 6. False and zero remain valid values.
    def test_06_false_and_zero_are_valid_values(self):
        recipe = base_recipe(
            [
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': True,
                    'bindings': {'upscale': 'allow_upscale'},
                },
                {
                    'op': 'image.compress',
                    'preset': 'custom',
                    'quality': 85,
                    'png_level': 6,
                    'jpeg_progressive': True,
                    'jpeg_optimize': True,
                    'bindings': {
                        'png_level': 'png_level',
                        'jpeg_progressive': 'progressive',
                    },
                },
                {
                    'op': 'metadata.shift_capture',
                    'seconds': 3600,
                    'bindings': {'seconds': 'offset_seconds'},
                },
            ],
            parameters=[
                {'id': 'allow_upscale', 'label': 'Allow upscale', 'type': 'boolean', 'required': True},
                {'id': 'png_level', 'label': 'PNG level', 'type': 'integer', 'minimum': 0, 'maximum': 9, 'required': True},
                {'id': 'progressive', 'label': 'Progressive', 'type': 'boolean', 'default': False},
                {'id': 'offset_seconds', 'label': 'Offset', 'type': 'integer', 'minimum': -3600, 'maximum': 3600, 'required': True},
            ],
        )
        resolved = params.resolve_recipe(
            recipe,
            {'allow_upscale': False, 'png_level': 0, 'offset_seconds': 0},
        )
        self.assertIs(resolved['steps'][0]['upscale'], False)
        self.assertEqual(resolved['steps'][1]['png_level'], 0)
        self.assertIs(resolved['steps'][1]['jpeg_progressive'], False)
        self.assertEqual(resolved['steps'][2]['seconds'], 0)
        core.validate(resolved)

    # 7. Boolean/integer confusion is rejected.
    def test_07_boolean_integer_confusion_rejected(self):
        int_recipe = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer', 'minimum': 1, 'maximum': 100}],
        )
        with self.assertRaises(RecipeError):
            params.resolve_recipe(int_recipe, {'q': True})
        with self.assertRaises(RecipeError):
            params.resolve_recipe(int_recipe, {'q': False})

        bad_default = copy.deepcopy(int_recipe)
        bad_default['parameters'][0]['default'] = True
        with self.assertRaises(RecipeError):
            params.validate_authored(bad_default)

        bool_recipe = base_recipe(
            [{'op': 'image.resize', 'max_width': 1600, 'max_height': 1600, 'upscale': False, 'bindings': {'upscale': 'u'}}],
            parameters=[{'id': 'u', 'label': 'Upscale', 'type': 'boolean'}],
        )
        with self.assertRaises(RecipeError):
            params.resolve_recipe(bool_recipe, {'u': 1})
        with self.assertRaises(RecipeError):
            params.resolve_recipe(bool_recipe, {'u': 0})

    # 8. Invalid numeric values and bounds are rejected (NaN, inf, out-of-range, bad bounds).
    def test_08_invalid_numeric_values_and_bounds_rejected(self):
        num_recipe = base_recipe(
            [{'op': 'image.rotate', 'degrees': 0, 'bindings': {'degrees': 'angle'}}],
            parameters=[{'id': 'angle', 'label': 'Angle', 'type': 'number', 'minimum': -180, 'maximum': 180}],
        )
        for bad in (float('nan'), float('inf'), float('-inf'), 181, -181, True, '90'):
            with self.assertRaises(RecipeError, msg=f'Should reject {bad!r}'):
                params.resolve_recipe(num_recipe, {'angle': bad})

        # Out-of-range parameter bounds vs operation constraints rejected during authored validation.
        out_of_range_bounds = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer', 'minimum': 1, 'maximum': 150}],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(out_of_range_bounds)

        # NaN/inf in authored bounds rejected.
        nan_bound = copy.deepcopy(num_recipe)
        nan_bound['parameters'][0]['maximum'] = math.nan
        with self.assertRaises(RecipeError):
            params.validate_authored(nan_bound)

    # 9. Unknown parameter references are rejected.
    def test_09_unknown_parameter_references_rejected(self):
        # Unknown in bindings
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'missing'}}],
                parameters=[],
            ))
        # Unknown in enabled_when
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.auto_orient', 'enabled_when': {'param': 'missing', 'equals': True}}],
                parameters=[],
            ))
        # Unknown in filename template
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'file.rename_output', 'pattern': '{param:missing}_{filename}'}],
                parameters=[],
            ))
        # Unknown in destination folder template
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.auto_orient'}],
                parameters=[],
                destination={'mode': 'subfolder', 'folder': '{param:missing}'},
            ))
        # Unknown in caller values
        valid = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Q', 'type': 'integer', 'default': 95}],
        )
        with self.assertRaises(RecipeError):
            params.resolve_recipe(valid, {'typo': 80})

    # 10. Incompatible field bindings & dotted traversal are rejected.
    def test_10_incompatible_field_bindings_and_traversal_rejected(self):
        # Text bound to integer field
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'txt'}}],
                parameters=[{'id': 'txt', 'label': 'Text', 'type': 'text', 'default': '95'}],
            ))
        # Choice with unsupported value for image.convert.format
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'format': 'fmt'}}],
                parameters=[{'id': 'fmt', 'label': 'Format', 'type': 'choice', 'choices': ['jpeg', 'raw']}],
            ))
        # Dotted traversal rejected
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{
                    'op': 'image.overlay',
                    'version': 1, 'kind': 'text', 'source': 'custom', 'value': 'Proof', 'logo': '',
                    'anchor': 'bottom_right', 'margin': 3.0, 'size': 3.0, 'opacity': 65,
                    'font': 'DejaVu Sans', 'color': '#ffffff', 'bold': False, 'italic': False,
                    'assistance': 'outline',
                    'bindings': {'text_fields.custom.value': 'txt'},
                }],
                parameters=[{'id': 'txt', 'label': 'Text', 'type': 'text', 'default': 'Proof'}],
            ))
        # Duplicate parameter IDs rejected
        with self.assertRaises(RecipeError):
            params.validate_authored(base_recipe(
                [{'op': 'image.auto_orient'}],
                parameters=[
                    {'id': 'dup', 'label': 'A', 'type': 'text'},
                    {'id': 'dup', 'label': 'B', 'type': 'text'},
                ],
            ))

    # 11. Conditional visibility behaves correctly (and rejects forward refs / cycles).
    def test_11_conditional_visibility_and_forward_ref_rejection(self):
        recipe = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'enabled_when': {'param': 'do_resize', 'equals': True},
                    'bindings': {'max_width': 'edge', 'max_height': 'edge'},
                },
            ],
            parameters=[
                {'id': 'do_resize', 'label': 'Resize', 'type': 'boolean', 'default': False},
                {
                    'id': 'edge',
                    'label': 'Long edge',
                    'type': 'integer',
                    'minimum': 100,
                    'maximum': 8000,
                    'required': True,
                    'visible_when': {'param': 'do_resize', 'equals': True},
                },
            ],
        )
        # When do_resize=False, 'edge' is inactive and required check does not trigger.
        self.assertEqual([p['id'] for p in params.active_parameters(recipe)], ['do_resize'])
        resolved_off = params.resolve_recipe(recipe, {'do_resize': False})
        self.assertFalse(resolved_off['steps'][1]['enabled'])

        # When do_resize=True, 'edge' becomes active and required.
        self.assertEqual([p['id'] for p in params.active_parameters(recipe, {'do_resize': True})], ['do_resize', 'edge'])
        with self.assertRaises(RecipeError):
            params.resolve_recipe(recipe, {'do_resize': True})
        resolved_on = params.resolve_recipe(recipe, {'do_resize': True, 'edge': 1200})
        self.assertTrue(resolved_on['steps'][1]['enabled'])
        self.assertEqual(resolved_on['steps'][1]['max_width'], 1200)

        # Forward reference rejected.
        forward = base_recipe(
            [{'op': 'image.auto_orient'}],
            parameters=[
                {'id': 'first', 'label': 'First', 'type': 'text', 'visible_when': {'param': 'second', 'equals': True}},
                {'id': 'second', 'label': 'Second', 'type': 'boolean', 'default': True},
            ],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(forward)

        # Self-reference (cycle) rejected.
        self_ref = base_recipe(
            [{'op': 'image.auto_orient'}],
            parameters=[
                {'id': 'loop', 'label': 'Loop', 'type': 'boolean', 'visible_when': {'param': 'loop', 'equals': True}},
            ],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(self_ref)

    # 12. Mutually exclusive operation activation via choice parameter.
    def test_12_mutually_exclusive_operation_activation(self):
        recipe = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {
                    'op': 'image.convert',
                    'format': 'jpeg',
                    'quality': 95,
                    'enabled_when': {'param': 'delivery_format', 'equals': 'jpeg'},
                },
                {
                    'op': 'image.convert',
                    'format': 'png',
                    'quality': None,
                    'enabled_when': {'param': 'delivery_format', 'equals': 'png'},
                },
                {
                    'op': 'image.convert',
                    'format': 'tiff',
                    'quality': None,
                    'enabled_when': {'param': 'delivery_format', 'equals': 'tiff'},
                },
            ],
            parameters=[
                {
                    'id': 'delivery_format',
                    'label': 'Delivery format',
                    'type': 'choice',
                    'choices': [
                        {'value': 'jpeg', 'label': 'JPEG (Quality 95)'},
                        {'value': 'png', 'label': 'PNG (Lossless)'},
                        {'value': 'tiff', 'label': 'TIFF (Archival)'},
                    ],
                    'default': 'jpeg',
                }
            ],
        )
        # Passes authored validation despite three image.convert steps because they are provably disjoint.
        params.validate_authored(recipe)

        for chosen, active_idx in (('jpeg', 1), ('png', 2), ('tiff', 3)):
            resolved = params.resolve_recipe(recipe, {'delivery_format': chosen})
            flags = [resolved['steps'][i]['enabled'] for i in (1, 2, 3)]
            self.assertEqual(flags, [i == active_idx for i in (1, 2, 3)])
            core.validate(resolved)

    # 13. Inactive parameters cannot supply stale values.
    def test_13_inactive_parameters_cannot_supply_stale_values(self):
        recipe = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'enabled_when': {'param': 'do_resize', 'equals': True},
                    'bindings': {'max_width': 'edge', 'max_height': 'edge'},
                },
            ],
            parameters=[
                {'id': 'do_resize', 'label': 'Resize', 'type': 'boolean', 'default': False},
                {
                    'id': 'edge',
                    'label': 'Edge',
                    'type': 'integer',
                    'minimum': 100,
                    'maximum': 8000,
                    'visible_when': {'param': 'do_resize', 'equals': True},
                },
            ],
        )
        # Caller passes a stale (even invalid/out-of-range) value for hidden 'edge':
        # must be ignored completely and never written into the step.
        resolved = params.resolve_recipe(recipe, {'do_resize': False, 'edge': 999999})
        self.assertFalse(resolved['steps'][1]['enabled'])
        self.assertEqual(resolved['steps'][1]['max_width'], 1600)
        self.assertEqual(resolved['steps'][1]['max_height'], 1600)

        # An unconditionally active step binding a conditional parameter is rejected statically.
        unguarded = base_recipe(
            [
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'bindings': {'max_width': 'edge'},
                }
            ],
            parameters=[
                {'id': 'do_resize', 'label': 'Resize', 'type': 'boolean', 'default': False},
                {
                    'id': 'edge',
                    'label': 'Edge',
                    'type': 'integer',
                    'minimum': 100,
                    'maximum': 8000,
                    'visible_when': {'param': 'do_resize', 'equals': True},
                },
            ],
        )
        with self.assertRaisesRegex(RecipeError, 'conditional parameter'):
            params.validate_authored(unguarded)

    # 14. Conflicting resolved operation sequences are rejected.
    def test_14_conflicting_operation_sequences_rejected(self):
        # Overlapping conditions on two image.convert steps -> rejected statically.
        overlap_converts = base_recipe(
            [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'enabled_when': {'param': 'a', 'equals': True}},
                {'op': 'image.convert', 'format': 'png', 'quality': None, 'enabled_when': {'param': 'b', 'equals': True}},
            ],
            parameters=[
                {'id': 'a', 'label': 'A', 'type': 'boolean', 'default': True},
                {'id': 'b', 'label': 'B', 'type': 'boolean', 'default': False},
            ],
        )
        with self.assertRaisesRegex(RecipeError, 'Multiple Convert Format'):
            params.validate_authored(overlap_converts)

        # Conditional image.resize after metadata.strip_gps -> rejected statically.
        bad_order = base_recipe(
            [
                {'op': 'metadata.strip_gps'},
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'enabled_when': {'param': 'do_resize', 'equals': True},
                },
            ],
            parameters=[{'id': 'do_resize', 'label': 'Resize', 'type': 'boolean', 'default': False}],
        )
        with self.assertRaisesRegex(RecipeError, 'pixel processing must precede'):
            params.validate_authored(bad_order)

    # 15. Filename values containing braces remain literal (no second-pass expansion).
    def test_15_filename_values_with_braces_remain_literal(self):
        recipe = base_recipe(
            [{'op': 'file.rename_output', 'pattern': '{param:project}_{filename}'}],
            parameters=[{'id': 'project', 'label': 'Project', 'type': 'text', 'required': True}],
            destination={'mode': 'subfolder', 'folder': '{param:project}'},
        )
        resolved = params.resolve_recipe(recipe, {'project': '{date}'})
        # Concrete pattern escapes braces so Stage 2 emits literal '{date}'.
        self.assertEqual(resolved['steps'][0]['pattern'], '{{date}}_{filename}')
        self.assertEqual(
            core.format_output_pattern(resolved['steps'][0]['pattern'], 'vacation', date='20260101_000000', index=1),
            '{date}_vacation',
        )
        # Subfolder is plain literal text (no brace doubling).
        self.assertEqual(resolved['destination']['folder'], '{date}')
        core.validate(resolved)

        # Also reject arbitrary Python formatting/indexing/conversion in authored template.
        for bad_pattern in ('{param:project!r}_{filename}', '{param:project:10}_{filename}', '{filename:>10}', '{param.project}'):
            bad = base_recipe(
                [{'op': 'file.rename_output', 'pattern': bad_pattern}],
                parameters=[{'id': 'project', 'label': 'Project', 'type': 'text', 'default': 'ok'}],
            )
            with self.assertRaises(RecipeError, msg=f'Should reject {bad_pattern!r}'):
                params.validate_authored(bad)

    # 16. Path traversal and unsafe components are rejected.
    def test_16_path_traversal_and_unsafe_components_rejected(self):
        recipe = base_recipe(
            [{'op': 'file.rename_output', 'pattern': '{param:folder}_{filename}'}],
            parameters=[{'id': 'folder', 'label': 'Folder', 'type': 'text', 'required': True}],
            destination={'mode': 'subfolder', 'folder': '{param:folder}'},
        )
        for bad in ('..', '.', '../escape', 'a/b', 'a\\b', 'bad\x00name', 'bad\nname'):
            with self.assertRaises(RecipeError, msg=f'Should reject {bad!r}'):
                params.resolve_recipe(recipe, {'folder': bad})

    # 17. Empty optional metadata values cannot clear metadata or accidentally inherit Settings.
    def test_17_empty_optional_metadata_never_clears_or_inherits_settings(self):
        settings_file = self.config_home / 'kimng' / 'settings.conf'
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            'KIM_COPYRIGHT_CREATOR=Global Settings Artist\n'
            'KIM_COPYRIGHT_NOTICE=Global Notice\n',
            encoding='utf-8',
        )
        recipe = base_recipe(
            [
                {'op': 'metadata.creator', 'bindings': {'value': 'opt_artist'}},
                {
                    'op': 'metadata.copyright',
                    'creator': None,
                    'notice': None,
                    'rights': '',
                    'bindings': {'creator': 'opt_artist'},
                },
            ],
            parameters=[
                {'id': 'opt_artist', 'label': 'Optional Artist', 'type': 'text', 'required': False},
            ],
        )
        # Omitted optional parameter -> explicit '' (NOT None -> does NOT pull Global Settings Artist!).
        resolved = params.resolve_recipe(recipe, {})
        self.assertEqual(resolved['steps'][0]['value'], '')
        self.assertIsNotNone(resolved['steps'][0]['value'])
        self.assertEqual(resolved['steps'][1]['creator'], '')
        # Unbound 'notice' with None still inherits Settings cleanly!
        self.assertEqual(resolved['steps'][1]['notice'], 'Global Notice')
        core.validate(resolved)

        # Explicit empty string behaves identically.
        resolved_empty = params.resolve_recipe(recipe, {'opt_artist': ''})
        self.assertEqual(resolved_empty['steps'][0]['value'], '')
        self.assertEqual(resolved_empty['steps'][1]['creator'], '')

    # 18. Authored definitions and supplied inputs remain unchanged (no mutation).
    def test_18_no_mutation_of_authored_definition_or_inputs(self):
        recipe = base_recipe(
            [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}},
                {'op': 'file.rename_output', 'pattern': '{param:tag}_{filename}'},
            ],
            parameters=[
                {'id': 'q', 'label': 'Quality', 'type': 'integer', 'default': 95},
                {'id': 'tag', 'label': 'Tag', 'type': 'text', 'required': True},
            ],
            destination={'mode': 'subfolder', 'folder': '{param:tag}'},
        )
        supplied = {'q': 92, 'tag': 'ClientA'}
        recipe_copy = copy.deepcopy(recipe)
        supplied_copy = copy.deepcopy(supplied)

        params.validate_authored(recipe)
        params.active_parameters(recipe, supplied)
        resolved = params.resolve_recipe(recipe, supplied)

        self.assertEqual(recipe, recipe_copy)
        self.assertEqual(supplied, supplied_copy)
        self.assertNotEqual(resolved, recipe)

    # 19. Unresolved authored definitions cannot reach planning or execution.
    def test_19_unresolved_authored_definitions_rejected_by_engine(self):
        recipe = base_recipe(
            [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}},
                {'op': 'file.rename_output', 'pattern': '{param:tag}_{filename}'},
            ],
            parameters=[
                {'id': 'q', 'label': 'Quality', 'type': 'integer', 'default': 95},
                {'id': 'tag', 'label': 'Tag', 'type': 'text', 'default': 'web'},
            ],
        )
        with self.assertRaises(RecipeError):
            core.validate(recipe)
        with self.assertRaises(RecipeError):
            core.plan(recipe, Path(self.temp.name) / 'nonexistent.jpg')
        with self.assertRaises(RecipeError):
            core.approve_rows(recipe, [], [])
        with self.assertRaises(RecipeError):
            core.execute(recipe, [])

        # Also verify conditional image.compress toggles quality inheritance via confirmation_snapshot.
        from kim_recipe_run import confirmation_snapshot
        compress_recipe = base_recipe(
            [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': None},
                {
                    'op': 'image.compress',
                    'preset': 'custom',
                    'quality': 80,
                    'png_level': 6,
                    'jpeg_progressive': True,
                    'jpeg_optimize': False,
                    'enabled_when': {'param': 'use_compress', 'equals': True},
                },
            ],
            parameters=[{'id': 'use_compress', 'label': 'Compress', 'type': 'boolean', 'default': True}],
        )
        with patch.dict(os.environ, {'KIM_WEB_QUALITY_JPEG': 'invalid'}):
            snap_on, err_on = confirmation_snapshot(compress_recipe, {'use_compress': True})
            self.assertIsNone(err_on)
            self.assertIsNone(snap_on['steps'][0]['quality'])
            self.assertTrue(snap_on['steps'][1]['enabled'])

            snap_off, err_off = confirmation_snapshot(compress_recipe, {'use_compress': False})
            self.assertIsNone(snap_off)
            self.assertIn('Correct Settings', err_off)

    # 20. Pure-Python check: kim_recipe_params must not depend on PySide6 / Qt.
    def test_20_module_has_no_qt_dependency(self):
        code = (
            'import sys\n'
            'sys.modules["PySide6"] = None\n'
            'sys.modules["PySide6.QtCore"] = None\n'
            'sys.modules["PySide6.QtWidgets"] = None\n'
            'sys.path.insert(0, %r)\n'
            'import kim_recipe_params\n'
            'assert callable(kim_recipe_params.resolve_recipe)\n'
        ) % str(ROOT / 'src' / 'bin')
        res = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    # 21. Planning-only verification through the real planner on a temporary image.
    # Distinguishes planning verification (core.plan) from execution verification
    # (core.execute) and inspects sha256_noatime + size/atime/mtime/ctime without
    # altering atime during observation.
    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_21_resolved_recipe_runs_through_real_planner_untouched_original(self):
        def observe_source(path):
            info = os.lstat(path)
            return (
                sha256_noatime(path),
                info.st_size,
                info.st_atime_ns,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        source = Path(self.temp.name) / 'photo.jpg'
        subprocess.run(['magick', '-size', '80x60', 'xc:navy', str(source)], check=True)
        subprocess.run(
            ['exiftool', '-overwrite_original', '-Artist=Original Author', str(source)],
            check=True,
            capture_output=True,
        )
        before = observe_source(source)
        # Protected observation itself must never alter atime, mtime, ctime, size, or content.
        self.assertEqual(observe_source(source), before)

        recipe = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {
                    'op': 'image.resize',
                    'max_width': 1600,
                    'max_height': 1600,
                    'upscale': False,
                    'bindings': {'max_width': 'edge', 'max_height': 'edge'},
                },
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95},
                {'op': 'metadata.creator', 'bindings': {'value': 'opt_artist'}},
                {'op': 'file.rename_output', 'pattern': '{param:prefix}_{filename}'},
            ],
            parameters=[
                {'id': 'edge', 'label': 'Max edge', 'type': 'integer', 'minimum': 16, 'maximum': 4000, 'default': 40},
                {'id': 'opt_artist', 'label': 'Optional artist', 'type': 'text', 'required': False},
                {'id': 'prefix', 'label': 'Prefix', 'type': 'text', 'required': True},
            ],
            destination={'mode': 'subfolder', 'folder': '{param:prefix}'},
        )

        # User supplies '{date}' as prefix (must stay literal, not trigger capture-date requirement!)
        # and leaves opt_artist omitted (must NOT clear Original Author or inherit Settings).
        with patch.dict(os.environ, {'KIM_COPYRIGHT_CREATOR': 'Should Not Leak'}):
            concrete = params.resolve_recipe(recipe, {'prefix': '{date}'})
        # Parameter resolution itself is strictly pure and preserves all 5 fields incl. atime.
        self.assertEqual(observe_source(source), before)

        # Planning verification only (core.plan; no execution or output publication).
        planned = core.plan(concrete, source, index=1)
        self.assertFalse(planned.row.problems)
        self.assertEqual(planned.name, '{date}_photo.jpg')
        self.assertEqual(planned.directory, source.parent / '{date}')
        self.assertFalse((source.parent / '{date}').exists())
        self.assertEqual(planned.state['properties']['width'], 40)
        self.assertEqual(planned.state['properties']['height'], 30)
        # No metadata edits emitted for blank optional artist -> Original Author preserved!
        self.assertEqual(planned.state['edits'], [])
        self.assertIn('EXIF:Artist: "Original Author"', planned.row.metadata)
        # Verify content hash (via O_NOATIME), size, mtime and ctime are strictly unchanged.
        # Note: existing kim_recipe_image.py passes str(source) to exiftool/magick without
        # O_NOATIME, so relatime mounts may advance st_atime_ns on the first planner read;
        # we verify sha256_noatime/size/mtime/ctime strictly and confirm our post-plan
        # observation itself does not alter st_atime_ns further.
        after = observe_source(source)
        self.assertEqual((after[0], after[1], after[3], after[4]), (before[0], before[1], before[3], before[4]))
        self.assertEqual(observe_source(source), after)

    # 22. Interactive evaluate_parameters() agrees with strict resolve_recipe() and
    # never lets invalid controlling values activate dependent parameters.
    def test_22_interactive_evaluation_and_validated_fast_path(self):
        recipe = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {
                    'op': 'image.convert',
                    'format': 'jpeg',
                    'quality': 95,
                    'enabled_when': {'param': 'mode', 'equals': 'custom'},
                    'bindings': {'quality': 'q'},
                },
                {'op': 'file.rename_output', 'pattern': '{param:project}_{filename}'},
            ],
            parameters=[
                {'id': 'project', 'label': 'Project', 'type': 'text', 'required': True},
                {'id': 'mode', 'label': 'Mode', 'type': 'choice', 'choices': ['default', 'custom'], 'required': True},
                {
                    'id': 'q',
                    'label': 'Quality',
                    'type': 'integer',
                    'default_source': 'web.quality.jpeg',
                    'visible_when': {'param': 'mode', 'equals': 'custom'},
                },
            ],
        )

        # Incomplete required inputs stay visible with field errors; dependent 'q' stays inactive.
        state = params.evaluate_parameters(recipe, {})
        self.assertEqual([p['id'] for p in state['active']], ['project', 'mode'])
        self.assertIn('project', state['errors'])
        self.assertIn('mode', state['errors'])
        self.assertEqual(state['values'], {})

        # Invalid controlling value never activates dependent 'q'.
        bad_ctrl = params.evaluate_parameters(recipe, {'project': 'Trip', 'mode': 'bogus'})
        self.assertEqual([p['id'] for p in bad_ctrl['active']], ['project', 'mode'])
        self.assertIn('mode', bad_ctrl['errors'])
        self.assertNotIn('q', bad_ctrl['values'])

        # Valid controlling value activates 'q', inheriting effective bounds (1..100)
        # and validating Settings-derived defaults consistently in both modes.
        with patch.dict(os.environ, {'KIM_WEB_QUALITY_JPEG': 'invalid'}):
            bad_settings = params.evaluate_parameters(recipe, {'project': 'Trip', 'mode': 'custom'})
            self.assertEqual([p['id'] for p in bad_settings['active']], ['project', 'mode', 'q'])
            self.assertIn('q', bad_settings['errors'])
            self.assertIn('Correct Settings', bad_settings['errors']['q'])
            with self.assertRaisesRegex(RecipeError, 'Correct Settings'):
                params.resolve_recipe(recipe, {'project': 'Trip', 'mode': 'custom'})

        # Validated fast path agrees identically with unvalidated path.
        authored = params.validate_authored(recipe)
        eff = params.effective_constraints(authored, validated=True)
        with patch.dict(os.environ, {'KIM_WEB_QUALITY_JPEG': '92'}):
            slow = params.evaluate_parameters(recipe, {'project': 'Trip', 'mode': 'custom'})
            fast = params.evaluate_parameters(
                authored, {'project': 'Trip', 'mode': 'custom'}, validated=True, constraints=eff
            )
            self.assertEqual(fast, slow)
            self.assertEqual(fast['errors'], {})
            self.assertEqual(fast['values'], {'project': 'Trip', 'mode': 'custom', 'q': 92})
            self.assertEqual(fast['constraints']['q'], {'type': 'integer', 'minimum': 1, 'maximum': 100})

    # 23. Ordinary confirmation_snapshot() continues past individual Settings errors
    # and resolves disabled steps for presentation (matching pre-Milestone-1 behavior).
    def test_23_ordinary_confirmation_snapshot_resilience_and_disabled_steps(self):
        from kim_recipe_run import confirmation_snapshot

        rec = core.builtins()[0]
        rec['steps'][3]['quality'] = None  # enabled image.convert -> invalid JPEG setting
        rec['steps'][6]['enabled'] = True  # enabled metadata.copyright_notice -> valid setting
        with patch.dict(
            os.environ,
            {
                'KIM_WEB_QUALITY_JPEG': 'invalid',
                'KIM_COPYRIGHT_CREATOR': 'Disabled Presentation Artist',
                'KIM_COPYRIGHT_NOTICE': 'Active Notice 2026',
            },
        ):
            snap, err = confirmation_snapshot(rec)
            self.assertIsNotNone(err)
            self.assertIn('Correct Settings', err)
            # Other enabled field still resolved despite earlier error.
            self.assertEqual(snap['steps'][6]['value'], 'Active Notice 2026')
            # Disabled step still resolved for presentation.
            self.assertEqual(snap['steps'][5]['value'], 'Disabled Presentation Artist')

    # 24. Effective constraints inherit from bound operations and intersect across fields.
    def test_24_effective_constraints_inherit_and_intersect(self):
        # Missing explicit bounds inherit operation bounds (1..100 for quality).
        inherited = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer'}],
        )
        eff = params.effective_constraints(inherited)
        self.assertEqual(eff['q'], {'type': 'integer', 'minimum': 1, 'maximum': 100})
        with self.assertRaises(RecipeError):
            params.resolve_recipe(inherited, {'q': 101})
        with self.assertRaises(RecipeError):
            params.resolve_recipe(inherited, {'q': 0})

        # Shared parameter across two fields intersects [1, 100] and [0, 9] -> [1, 9].
        shared = base_recipe(
            [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'lvl'}},
                {
                    'op': 'image.compress',
                    'preset': 'custom',
                    'quality': 85,
                    'png_level': 6,
                    'jpeg_progressive': True,
                    'jpeg_optimize': False,
                    'bindings': {'png_level': 'lvl'},
                },
            ],
            parameters=[{'id': 'lvl', 'label': 'Level', 'type': 'integer'}],
        )
        eff_shared = params.effective_constraints(shared)
        self.assertEqual(eff_shared['lvl'], {'type': 'integer', 'minimum': 1, 'maximum': 9})
        self.assertEqual(params.resolve_recipe(shared, {'lvl': 5})['steps'][1]['png_level'], 5)
        with self.assertRaises(RecipeError):
            params.resolve_recipe(shared, {'lvl': 10})

        # Impossible intersection (declared minimum 50 vs png_level maximum 9) rejected.
        impossible = copy.deepcopy(shared)
        impossible['parameters'][0]['minimum'] = 50
        with self.assertRaises(RecipeError):
            params.validate_authored(impossible)

        # Explicit default violating bound operation constraints rejected.
        bad_default = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer', 'default': 150}],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(bad_default)

    # 25. Literal fallback validation never conceals malformed authored step fields.
    def test_25_literal_fallback_validation_rejects_malformed_steps(self):
        # Malformed literal quality=999 on bound enabled step must be rejected.
        bad_bound = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 999, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer', 'minimum': 1, 'maximum': 100}],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(bad_bound)

        # Malformed literal fallback on disabled step must also be rejected.
        bad_disabled = base_recipe(
            [
                {'op': 'image.auto_orient'},
                {'op': 'image.convert', 'enabled': False, 'format': 'jpeg', 'quality': 999},
            ],
            parameters=[{'id': 'x', 'label': 'X', 'type': 'text'}],
        )
        with self.assertRaises(RecipeError):
            params.validate_authored(bad_disabled)

    # 26. Strict malformed-input handling: null bindings/conditions, non-string keys,
    # invalid step collections, and huge numbers produce RecipeError (never crashes).
    def test_26_malformed_inputs_raise_recipe_error(self):
        # Null bindings / enabled_when / visible_when / parameters
        for bad in (
            base_recipe([{'op': 'image.auto_orient', 'bindings': None}]),
            base_recipe([{'op': 'image.auto_orient', 'enabled_when': None}]),
            base_recipe([{'op': 'image.auto_orient'}], parameters=[{'id': 'a', 'label': 'A', 'type': 'text', 'visible_when': None}]),
            base_recipe([{'op': 'image.auto_orient'}], parameters=None) | {'parameters': None},
            {'schema': 3, 'id': 't', 'name': 'T', 'description': '', 'media': 'image', 'steps': None, 'destination': {'mode': 'beside'}, 'parameters': []},
            {'schema': 3, 'id': 't', 'name': 'T', 'description': '', 'media': 'image', 'steps': 'bad', 'destination': {'mode': 'beside'}, 'parameters': []},
            'not-a-dict',
        ):
            with self.assertRaises(RecipeError, msg=f'Should raise RecipeError for {bad!r}'):
                params.validate_authored(bad)

        # Non-string supplied-value keys
        valid = base_recipe(
            [{'op': 'image.auto_orient'}],
            parameters=[{'id': 'a', 'label': 'A', 'type': 'text'}],
        )
        with self.assertRaises(RecipeError):
            params.evaluate_parameters(valid, {1: 'x'})
        with self.assertRaises(RecipeError):
            params.resolve_recipe(valid, {1: 'x'})

        # Extremely large integer in number parameter / bound (would OverflowError in float())
        num_recipe = base_recipe(
            [{'op': 'image.rotate', 'degrees': 0, 'bindings': {'degrees': 'angle'}}],
            parameters=[{'id': 'angle', 'label': 'Angle', 'type': 'number'}],
        )
        with self.assertRaises(RecipeError):
            params.resolve_recipe(num_recipe, {'angle': 10**400})
        bad_bound_num = copy.deepcopy(num_recipe)
        bad_bound_num['parameters'][0]['maximum'] = 10**400
        with self.assertRaises(RecipeError):
            params.validate_authored(bad_bound_num)

    # 27. Literal brace-containing subfolder names remain unchanged, and resolved
    # parameter-like folder text is never interpreted a second time.
    def test_27_literal_brace_subfolder_and_single_pass_resolution(self):
        # Unrelated parameter must NOT turn ordinary folder 'Photos {2026}' into a template.
        literal_folder_recipe = base_recipe(
            [{'op': 'image.convert', 'format': 'jpeg', 'quality': 95, 'bindings': {'quality': 'q'}}],
            parameters=[{'id': 'q', 'label': 'Quality', 'type': 'integer', 'default': 95}],
            destination={'mode': 'subfolder', 'folder': 'Photos {2026}'},
        )
        resolved = params.resolve_recipe(literal_folder_recipe)
        self.assertEqual(resolved['destination']['folder'], 'Photos {2026}')
        core.validate(resolved)

        # Resolved literal folder text containing '{param:other}' is not interpreted again.
        param_folder_recipe = base_recipe(
            [{'op': 'image.auto_orient'}],
            parameters=[
                {'id': 'first', 'label': 'First', 'type': 'text', 'required': True},
                {'id': 'other', 'label': 'Other', 'type': 'text', 'default': 'SHOULD_NOT_EXPAND'},
            ],
            destination={'mode': 'subfolder', 'folder': '{param:first}'},
        )
        resolved2 = params.resolve_recipe(param_folder_recipe, {'first': '{param:other}'})
        self.assertEqual(resolved2['destination']['folder'], '{param:other}')
        core.validate(resolved2)


if __name__ == '__main__':
    unittest.main()
