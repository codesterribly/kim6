"""Generated video names retain the pre-encoding candidate at publication."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def dispatcher_functions(*names):
    source = (ROOT / 'src/bin/kim_all').read_text()
    return '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^\}', source,
                               re.M | re.S).group() for name in names)


class VideoOutputNumbering(unittest.TestCase):
    def publish(self, occupied=0, *, race=False, symlink=False, failure=False,
                cancelled=False, prefix=False, vacate_base=False, late_collisions=0):
        with tempfile.TemporaryDirectory(prefix='kim6-numbering-') as tmp:
            root = Path(tmp)
            stem = 'custom-clip' if prefix else 'clip_audio'
            def target(number):
                return root / (stem + (f'_{number}' if number else '') + '.mp3')
            for n in range(occupied): target(n).write_bytes(b'previous output')
            if symlink: target(occupied).symlink_to(root / 'missing')
            selected = occupied + int(symlink)
            stage = root / 'stage.mp3'; stage.write_bytes(b'new output')
            source = root / 'clip.mp4'; source.write_bytes(b'original')
            script = dispatcher_functions(
                'kim6_known_affix_key', 'kim6_affix_value', 'affixed_filename',
                'owned_stage_file', 'commit_tmp_to_target',
                'video_utility_target', 'video_utility_publish')
            script = script.replace('commit_tmp_to_target() {', 'exclusive_commit() {') + '''
KIMDIR="$1"
preview_guard() { return 0; }
publication_record_output() { :; }
commit_tmp_to_target() {
  printf '%s\n' "$2" >> "$KIMDIR/attempts"
  exclusive_commit "$@"
}
video_utility_target "$1/clip.mp4" audio mp3 "$2"
target="$VIDEO_UTILITY_TARGET"
number="$VIDEO_UTILITY_NEXT_NUMBER"
[ "$3" != race ] || printf contender > "$target"
[ "$6" != yes ] || rm -- "$1/$7.mp3"
for ((n=1; n<=$8; n++)); do printf contender > "$1/${7}_$n.mp3"; done
cancelled="$5"
progress_cancelled() { [ "$cancelled" = yes ]; }
'''
            # Inject failures at the publication operation, without touching originals.
            if failure:
                script += 'commit_tmp_to_target() { printf "%s\\n" "$2" >> "$KIMDIR/attempts"; return 1; }\n'
            # The current interface is intentionally exercised through its caller
            # sequence: choose, stage/produce, then publish the selected name.
            script += '''
video_utility_publish ref "$1/stage.mp3" "$1/clip.mp4" audio mp3 "$target" "$number" "$2"
'''
            result = subprocess.run(['bash', '-c', script, 'numbering', tmp,
                                     '-' if prefix else '_', 'race' if race else '',
                                     '', 'yes' if cancelled else 'no',
                                     'yes' if vacate_base else 'no', stem, str(late_collisions)],
                                    env={**os.environ, 'KIM_NAME_AFFIX_POSITION': 'prefix' if prefix else 'suffix',
                                         'KIM_AFFIX_AUDIO': 'custom' if prefix else 'audio'},
                                    capture_output=True, text=True, timeout=30)
            if failure or cancelled:
                self.assertEqual(result.returncode, 130 if cancelled else 1, result.stderr)
                self.assertTrue(stage.exists())
                self.assertFalse(target(selected).exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target(selected + int(race) + late_collisions).read_bytes(), b'new output')
                self.assertFalse(stage.exists())
                if race: self.assertEqual(target(selected).read_bytes(), b'contender')
            for n in range(int(vacate_base), occupied):
                self.assertEqual(target(n).read_bytes(), b'previous output')
            if vacate_base: self.assertFalse(target(0).exists())
            attempts = (root / 'attempts').read_text().splitlines() if (root / 'attempts').exists() else []
            self.assertEqual(len(attempts), 0 if cancelled else 2 if race else 1)
            if attempts: self.assertEqual(attempts[0], str(target(selected)))
            if symlink: self.assertTrue(target(occupied).is_symlink())
            self.assertEqual(source.read_bytes(), b'original')

    def test_selected_target_survives_more_than_1000_existing_names(self):
        self.publish(1004)

    def test_available_base_and_existing_numbered_names(self):
        for occupied in (0, 1, 5):
            with self.subTest(occupied=occupied): self.publish(occupied)

    def test_raced_target_and_symlink_are_preserved(self):
        self.publish(5, race=True, symlink=True)

    def test_custom_prefix_and_joiner_survive_race(self):
        self.publish(3, prefix=True, race=True)

    def test_selected_name_is_kept_when_a_lower_number_becomes_free(self):
        self.publish(3, vacate_base=True)

    def test_more_than_1000_collisions_appear_during_processing(self):
        self.publish(race=True, late_collisions=1004)

    def test_noncollision_failure_does_not_retry(self):
        self.publish(failure=True)

    def test_cancellation_preserves_stage_and_destinations(self):
        self.publish(3, cancelled=True)


if __name__ == '__main__':
    unittest.main()
