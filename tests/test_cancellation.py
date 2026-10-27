"""K14: interruption gates through the dispatcher, using test-owned images."""
import base64
import unittest
from support import Workspace


class CancellationTests(unittest.TestCase):
    def exercise(self, action, mode, phase, state):
        w = Workspace()
        self.addCleanup(w.close)
        a = w.jpeg('input/first 雪.jpg')
        b = w.jpeg('input/second space.jpg')
        w.set_policy_for_test(mode)
        if action == 'convert':
            destination = w.png('input/first 雪.png')
            payload = w.png('.control/produced.png').read_bytes()
            arguments = ['png']
        else:
            tag = {'compress': 'compressed', 'resize': 'resized', 'stripmeta': 'stripped'}[action]
            destination = a if mode == 'overwrite' else w.path('input/first 雪_' + tag + '.jpg')
            if mode == 'create':
                destination.write_bytes(b'preexisting destination')
            payload = a.read_bytes()
            arguments = ['75', str(a.parent)] if action == 'compress' else ['100%', str(a.parent)] if action == 'resize' else []
        before = {p: w.observe(p) for p in (a, b, destination)}
        producer = 'exiftool' if action == 'stripmeta' else 'magick'
        response = {'output_base64': base64.b64encode(payload).decode()}
        if action == 'resize':
            response['stdout'] = '3 2\n'
        w.respond(producer, **response)
        if state is not None:
            injection = {'interrupt': state, 'passthrough': True}
            if phase == 'before':
                w.respond_to('qdbus', 'wasCancelled', dict(
                    interrupt=state, **({'stdout': 'true\n'} if state == 'cancelled' else {'status': 2})))
            elif phase == 'input':
                if action == 'convert':
                    # Conversion has no input decode: interrupt destination staging.
                    w.respond_to('mktemp', str(a.parent / '.kim6-stage.XXXXXX'), injection)
                else:
                    w.respond('identify', **injection)
            elif phase == 'producer':
                response['interrupt'] = state
                w.respond(producer, **response)
            elif phase == 'metadata':
                # Create conversion has no metadata preparation; not a test case.
                w.respond('touch' if action == 'stripmeta' else 'chmod', **injection)
            elif phase == 'between':
                # Interrupt after the first item's acknowledged progress update.
                w.respond_to('qdbus', 'org.freedesktop.DBus.Properties.Set',
                             [{}, {}, {'interrupt': state}])
            elif phase == 'publication':
                reply = {'interrupt': state}
                if state == 'cancelled':
                    reply['stdout'] = 'true\n'
                elif state == 'malformed':
                    reply['stdout'] = 'unexpected\n'
                else:
                    reply['status'] = 2
                # Begin-item, early action gate, prepared-input gate, final gate.
                w.respond_to('qdbus', 'wasCancelled', [{'stdout': 'false\n'}] * 3 + [reply])
            else:
                raise AssertionError('unknown injection phase')
        result = w.dispatch(action, *arguments, a, b)
        producers = [c for c in result.calls if c['tool'] == producer
                     and (producer != 'exiftool' or '-all=' in c['argv'])]
        publication = [c for c in result.calls if c['tool'] == 'ln'
                       or (c['tool'] == 'mv' and c['argv'] not in (['--help'], ['--version']))]
        self.assertFalse(list(w.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(w.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((w.control / 'tmp').iterdir()), [])
        self.assertNotIn('could not close owned progress', result.stderr)
        if state is None:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(producers), 2)
            self.assertEqual(len(publication), 2)
            self.assertTrue(any(c['tool'] == 'qdbus' and c['argv'][2] == 'close' for c in result.calls))
            return
        if phase == 'between':
            self.assertEqual(len(producers), 1)
            self.assertEqual(len(publication), 1)
            self.assertEqual(w.path(publication[0]['argv'][-1]).read_bytes(), payload)
            self.assertEqual(w.observe(b), before[b])
            boundary = next(n for n, e in enumerate(result.events) if e.get('progress_interruption') == state)
            published = [n for n, e in enumerate(result.events) if e['tool'] == 'ln'
                         or (e['tool'] == 'mv' and e['argv'] not in (['--help'], ['--version']))]
            self.assertTrue(all(n < boundary for n in published))
            summaries = [c for c in result.calls if c['tool'] == 'kdialog' and '--error' in c['argv']]
            self.assertEqual(len(summaries), 1)
            self.assertIn('Succeeded: 1', ' '.join(summaries[0]['argv']))
            self.assertIn('Failed: 1', ' '.join(summaries[0]['argv']))
            return
        self.assertFalse(publication, publication)
        self.assertEqual(sorted(result.outputs), [])
        for path, entry in before.items():
            self.assertEqual(w.observe(path), entry, str(path))
        self.assertEqual(len(producers), 0 if phase in ('before', 'input') else 1)
        summaries = [c for c in result.calls if c['tool'] == 'kdialog'
                     and '--error' in c['argv'] and 'Failed: 1' in ' '.join(c['argv'])]
        self.assertEqual(len(summaries), 1, result.calls)
        self.assertIn('Succeeded: 0', ' '.join(summaries[0]['argv']))
        errors = [c for c in result.calls if c['tool'] == 'kdialog' and '--error' in c['argv']
                  and c not in summaries]
        self.assertEqual(len(errors), 0 if state in ('cancelled', 'gone') else 1)
        if state == 'gone':
            ownership = [c for c in result.calls if c['tool'] == 'qdbus'
                         and c['argv'][2] == 'org.freedesktop.DBus.NameHasOwner']
            self.assertTrue(ownership)
        else:
            closes = [e for e in result.events if e['tool'] == 'qdbus' and e['argv'][2] == 'close']
            self.assertEqual(len(closes), 1)
            self.assertEqual(closes[0]['status'], 0)


def case(action, mode, phase, state):
    def test(self):
        self.exercise(action, mode, phase, state)
    return test


for _action in ('compress', 'convert', 'resize', 'stripmeta'):
    for _mode in ('create', 'overwrite'):
        setattr(CancellationTests, f'test_{_action}_{_mode}_confirmed_false_batch',
                case(_action, _mode, 'healthy', None))
        for _state in ('cancelled', 'gone'):
            setattr(CancellationTests, f'test_{_action}_{_mode}_between_items_{_state}',
                    case(_action, _mode, 'between', _state))
        for _state in ('cancelled', 'gone', 'query_failed', 'owner_failed', 'malformed'):
            setattr(CancellationTests, f'test_{_action}_{_mode}_publication_{_state}',
                    case(_action, _mode, 'publication', _state))
        for _phase in ('before', 'input', 'producer', 'metadata'):
            if _action == 'convert' and _mode == 'create' and _phase == 'metadata':
                continue  # This action/mode intentionally performs no metadata preparation.
            for _state in ('cancelled', 'gone'):
                setattr(CancellationTests, f'test_{_action}_{_mode}_{_phase}_{_state}',
                        case(_action, _mode, _phase, _state))
