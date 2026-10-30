"""K10: shared progress helpers and actual qdbus argument contracts."""
import base64
import json
import unittest
from support import Workspace


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

    def run_helpers(self, body, *args):
        return self.w.shared_progress(body, *args)

    def calls(self, result, method):
        return [c for c in result.calls if c['tool'] == 'qdbus' and len(c['argv']) > 2 and c['argv'][2] == method]

    def assert_error(self, result):
        self.assertTrue(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))

    def test_open_passes_service_and_object_separately(self):
        result = self.run_helpers('ref="$(progress_open 2 Working)"; printf "%s\\n" "$ref"; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'org.kde.kdialog-test /ProgressDialog\n')
        self.assertTrue(result.events)
        self.assertTrue(all(e['status'] == 0 for e in result.events if e['tool'] == 'qdbus'), result.events)
        self.assertEqual(self.calls(result, 'showCancelButton')[0]['argv'],
                         ['org.kde.kdialog-test', '/ProgressDialog', 'showCancelButton', 'true'])

    def test_property_adapter_rejects_obsolete_extra_type_argument(self):
        result = self.w.command('qdbus', 'org.kde.kdialog-test', '/ProgressDialog',
            'org.freedesktop.DBus.Properties.Set', 'org.kde.kdialog.ProgressDialog', 'value', 'int32', '1')
        self.assertNotEqual(result.returncode, 0)

    def test_label_keeps_spaces_and_unicode_in_one_argument(self):
        label = 'Processing photo 雪 and space.png'
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_label "$ref" "$1"; progress_close "$ref"', label)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(result, 'setLabelText')[0]['argv'],
                         ['org.kde.kdialog-test', '/ProgressDialog', 'setLabelText', label])

    def test_values_include_zero_first_and_final_with_correct_variant_contract(self):
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_value "$ref" 1; progress_value "$ref" 2; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = [c['argv'] for c in self.calls(result, 'org.freedesktop.DBus.Properties.Set') if c['argv'][4] == 'value']
        self.assertEqual(values, [['org.kde.kdialog-test', '/ProgressDialog',
            'org.freedesktop.DBus.Properties.Set', 'org.kde.kdialog.ProgressDialog', 'value', str(n)] for n in (0, 1, 2)])

    def test_cancel_false_continues(self):
        result = self.run_helpers('ref="$(progress_open 2 Working)"; if progress_cancelled "$ref"; then exit 73; fi; progress_begin_item "$ref" "photo 雪"; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.calls(result, 'setLabelText'))

    def test_cancel_true_stops_and_closes(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'stdout': 'true\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls(result, 'close')), 1)
        self.assertFalse(self.calls(result, 'setLabelText'))
        self.assertFalse(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))

    def test_failed_query_stops_with_communication_error_not_assumed_false(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'status': 73, 'stdout': 'false\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(self.calls(result, 'setLabelText'))
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_disappeared_service_stops_quietly_and_unregisters(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'status': 1})
        self.w.respond_to('qdbus', 'org.freedesktop.DBus.NameHasOwner', {'stdout': 'false\n'})
        self.w.respond_to('qdbus', 'close', {'status': 1})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls(result, 'setLabelText'))
        self.assertFalse(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))
        self.assertEqual(len(self.calls(result, 'close')), 1)
        self.assertNotIn('could not close', result.stderr)
        self.assertEqual(self.calls(result, 'org.freedesktop.DBus.NameHasOwner')[0]['argv'],
                         ['org.freedesktop.DBus', '/org/freedesktop/DBus',
                          'org.freedesktop.DBus.NameHasOwner', 'org.kde.kdialog-test'])

    def test_service_present_query_failure_reports_distinct_error(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'status': 2})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertEqual(len(self.calls(result, 'org.freedesktop.DBus.NameHasOwner')), 1)
        self.assertFalse(self.calls(result, 'setLabelText'))

    def test_failed_ownership_query_is_not_assumed_disappearance(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'status': 2})
        self.w.respond_to('qdbus', 'org.freedesktop.DBus.NameHasOwner', {'status': 2, 'stdout': 'false\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(self.calls(result, 'setLabelText'))

    def test_malformed_ownership_reply_is_not_assumed_disappearance(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'status': 2})
        self.w.respond_to('qdbus', 'org.freedesktop.DBus.NameHasOwner', {'stdout': 'unknown\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)

    def test_shared_gate_stops_before_publication_after_service_loss(self):
        source = self.w.jpeg('input/photo.jpg')
        self.w.respond('exiftool', output_base64=base64.b64encode(source.read_bytes()).decode(),
                       disappear_progress=True)
        result = self.run_helpers('''
ref="$(progress_open 2 Working)"
progress_begin_item "$ref" first
stage="$(tmp_for_target "$2")"
exiftool -o "$stage" -- "$1"
if progress_cancelled "$ref"; then exit 73; fi
commit_tmp_to_target "$stage" "$2" create
progress_begin_item "$ref" second
''', source, self.w.root / 'published.jpg')
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertFalse(result.outputs, result.outputs)
        self.assertFalse(any(c['tool'] in ('ln', 'mv') for c in result.calls))
        self.assertEqual(len(self.calls(result, 'setLabelText')), 1)
        self.assertFalse(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertNotIn('could not close', result.stderr)

    def test_no_additional_items_after_service_loss_between_items(self):
        self.w.respond_to('qdbus', 'wasCancelled', [{'stdout': 'false\n'}, {'status': 2}])
        self.w.respond_to('qdbus', 'org.freedesktop.DBus.NameHasOwner', {'stdout': 'false\n'})
        self.w.respond_to('qdbus', 'close', {'status': 2})
        result = self.run_helpers('''
ref="$(progress_open 3 Working)"
for item in first second third; do
  progress_begin_item "$ref" "$item" || exit 73
  printf 'STARTED %s\n' "$item"
done
''')
        self.assertEqual(result.returncode, 73)
        self.assertEqual(result.stdout, 'STARTED first\n')
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_lost_service_during_updates_stops_without_spurious_error(self):
        for method, body in [('setLabelText', 'progress_label "$ref" item'),
                             ('org.freedesktop.DBus.Properties.Set', 'progress_value "$ref" 1')]:
            with self.subTest(method=method):
                self.w.respond_to('qdbus', method, [{'status': 2}] if method == 'setLabelText'
                                  else [{}, {}, {'status': 2}])
                self.w.respond_to('qdbus', 'org.freedesktop.DBus.NameHasOwner', {'stdout': 'false\n'})
                self.w.respond_to('qdbus', 'close', {'status': 2})
                result = self.run_helpers('ref="$(progress_open 2 Working)"; ' + body + '; printf UNREACHABLE')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('UNREACHABLE', result.stdout)
                self.assertFalse(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))
                self.assertNotIn('could not close', result.stderr)
                # Reset the previous route so the next subtest's setup can run.
                self.w.respond_to('qdbus', method, None)

    def test_k14_service_loss_before_publication_must_not_publish(self):
        # Intentionally remains red until K14 migrates action-local checks.
        # Do not invert this safety assertion to bless the current unsafe fallback.
        a = self.w.jpeg('input/first.jpg')
        b = self.w.jpeg('input/second.jpg')
        original = a.read_bytes()
        self.w.env['KIM_POLICY'] = 'create'
        self.w.respond('exiftool', output_base64=base64.b64encode(original).decode(),
                       disappear_progress=True)
        result = self.w.dispatch('stripmeta', a, b)
        self.assertEqual(a.read_bytes(), original)
        self.assertEqual(b.read_bytes(), original)
        producers = [c for c in result.calls if c['tool'] == 'exiftool' and '-all=' in c['argv']]
        self.assertEqual(len(producers), 1)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertEqual(sorted(result.outputs), [], 'K14: service loss was ignored by the pre-publication check')

    def test_horizontal_reference_whitespace_is_normalized(self):
        self.w.respond_to('kdialog', '--progressbar', {'stdout': '\t org.kde.kdialog-test\t /ProgressDialog \t\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; printf "%s\\n" "$ref"; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'org.kde.kdialog-test /ProgressDialog\n')

    def test_unique_service_and_nested_object_are_valid(self):
        plan = json.loads(self.w.plan.read_text())
        plan['progress_reference'] = ':1.42 /dialogs/progress_1'
        self.w.plan.write_text(json.dumps(plan))
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(result, 'showCancelButton')[0]['argv'][:2], [':1.42', '/dialogs/progress_1'])

    def test_close_is_idempotent_and_exit_does_not_close_twice(self):
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_close "$ref"; progress_close "$ref"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_exit_cleanup_closes_owned_dialog_after_failure(self):
        result = self.run_helpers('ref="$(progress_open 2 Working)"; exit 73')
        self.assertEqual(result.returncode, 73)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_missing_qdbus_does_not_open_dialog(self):
        (self.w.bin / 'qdbus').unlink()
        result = self.run_helpers(
            'kim6_qdbus_available() { return 1; }; '
            'ref="$(progress_open 2 Working)"'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(any(c['tool'] == 'kdialog' and '--progressbar' in c['argv'] for c in result.calls))

    def test_missing_kdialog_fails_without_process_termination(self):
        (self.w.bin / 'kdialog').unlink()
        result = self.run_helpers('ref="$(progress_open 2 Working)"')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr)
        self.assertFalse(any(c['tool'] == 'qdbus' for c in result.calls))

    def test_setup_failure_closes_owned_dialog(self):
        self.w.respond_to('qdbus', 'showCancelButton', {'status': 73})
        result = self.run_helpers('ref="$(progress_open 2 Working)"')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_batch_labels_values_and_close(self):
        a = self.w.jpeg('input/first 雪.jpg')
        b = self.w.jpeg('input/second space.jpg')
        self.w.env['KIM_POLICY'] = 'create'
        self.w.respond('exiftool', output_base64=base64.b64encode(a.read_bytes()).decode())
        result = self.w.dispatch('stripmeta', a, b)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.outputs), 2)
        self.assertTrue(all(e['status'] == 0 for e in result.events if e['tool'] == 'qdbus'))
        labels = [c['argv'][-1] for c in self.calls(result, 'setLabelText')]
        self.assertTrue(any('first 雪.jpg' in label for label in labels))
        self.assertTrue(any('second space.jpg' in label for label in labels))
        values = [c['argv'][-1] for c in self.calls(result, 'org.freedesktop.DBus.Properties.Set') if c['argv'][4] == 'value']
        self.assertEqual(values, ['0', '1', '2'])
        self.assertEqual(len(self.calls(result, 'close')), 1)


    def test_label_failure_stops_and_closes(self):
        self.w.respond_to('qdbus', 'setLabelText', {'status': 73})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_value_failure_stops_and_closes(self):
        self.w.respond_to('qdbus', 'org.freedesktop.DBus.Properties.Set', [{}, {}, {'status': 73}])
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_value "$ref" 1')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_close_failure_is_retried_by_exit_cleanup(self):
        self.w.respond_to('qdbus', 'close', [{'status': 73}, {}])
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_close "$ref" || true')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls(result, 'close')), 2)
        self.assertEqual([e['status'] for e in result.events if e['tool'] == 'qdbus' and e['argv'][2] == 'close'], [73, 0])

    def test_failed_kdialog_with_valid_owned_reference_is_closed(self):
        self.w.respond_to('kdialog', '--progressbar', {'status': 73, 'stdout': 'org.kde.kdialog-test /ProgressDialog\n'})
        result = self.run_helpers('ref="$(progress_open 2 Working)"')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertEqual(len(self.calls(result, 'close')), 1)

    def test_exit_cleanup_closes_all_owned_dialogs(self):
        references = ['org.kde.kdialog-a /ProgressDialog', 'org.kde.kdialog-b /ProgressDialog']
        plan = json.loads(self.w.plan.read_text())
        plan['progress_references'] = references
        self.w.plan.write_text(json.dumps(plan))
        self.w.respond_to('kdialog', '--progressbar', [{'stdout': ref + '\n'} for ref in references])
        result = self.run_helpers('a="$(progress_open 2 First)"; b="$(progress_open 2 Second)"; exit 73')
        self.assertEqual(result.returncode, 73)
        self.assertEqual([c['argv'][:2] for c in self.calls(result, 'close')], [ref.split() for ref in references])

    def test_close_does_not_contact_unowned_dialog(self):
        result = self.run_helpers('progress_close "org.kde.kdialog-test /ProgressDialog"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c['tool'] == 'qdbus' for c in result.calls))

    def test_missing_reference_stops_without_contacting_dbus(self):
        result = self.run_helpers('progress_begin_item "" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(any(c['tool'] == 'qdbus' for c in result.calls))

    def test_invalid_values_are_rejected_without_dbus_update(self):
        for value in ('-1', 'abc', '2147483648', ''):
            with self.subTest(value=value):
                result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_value "$ref" "$1"', value)
                self.assertNotEqual(result.returncode, 0)
                self.assert_error(result)
                updates = [c for c in self.calls(result, 'org.freedesktop.DBus.Properties.Set') if c['argv'][4] == 'value']
                self.assertEqual([c['argv'][-1] for c in updates], ['0'])


def malformed_case(reference):
    def test(self):
        self.w.respond_to('kdialog', '--progressbar', {'stdout': reference})
        result = self.run_helpers('ref="$(progress_open 2 Working)"')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(any(c['tool'] == 'qdbus' for c in result.calls))
    return test


for _n, _reference in enumerate(('', 'org.kde.kdialog-test', 'org.kde.kdialog-test /ProgressDialog extra',
        'org.kde.kdialog-test\n/ProgressDialog', 'org.kde.kdialog-test /bad//path',
        'org.kde.kdialog-test /bad-path', 'not-a-bus /ProgressDialog',
        'org.kde.kdialog-test /ProgressDialog\nother /object', 'org.kde.kdialog-test /ProgressDialog\r\n')):
    setattr(ProgressTests, 'test_malformed_reference_' + str(_n), malformed_case(_reference))


def reply_case(reply):
    def test(self):
        self.w.respond_to('qdbus', 'wasCancelled', {'stdout': reply})
        result = self.run_helpers('ref="$(progress_open 2 Working)"; progress_begin_item "$ref" item')
        self.assertNotEqual(result.returncode, 0)
        self.assert_error(result)
        self.assertFalse(self.calls(result, 'setLabelText'))
    return test

for _n, _reply in enumerate(('', 'yes\n', '0\n', ' true \n', 'false\ntrue\n')):
    setattr(ProgressTests, 'test_unexpected_cancellation_reply_' + str(_n), reply_case(_reply))
