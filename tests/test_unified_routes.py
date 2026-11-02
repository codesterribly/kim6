"""Every installed menu action has a concrete route and packaged UI helpers."""
from pathlib import Path
import re
import shlex
import unittest
ROOT=Path(__file__).resolve().parents[1]


class RouteTests(unittest.TestCase):
    def test_all_current_desktop_routes_and_translation_hooks(self):
        dispatcher=(ROOT/'src/bin/kim_all').read_text()
        for path in sorted((ROOT/'src').glob('kim_*.desktop.in')):
            sections=re.split(r'\n(?=\[Desktop Action )',path.read_text())
            declared=next(line.split('=',1)[1].strip(';').split(';') for line in sections[0].splitlines() if line.startswith('Actions='))
            actual=[]
            for section in sections[1:]:
                action=section.split(']',1)[0].removeprefix('[Desktop Action ');actual.append(action)
                if action=='_SEPARATOR_': continue
                lines=section.splitlines(); command=next(line[5:] for line in lines if line.startswith('Exec='));args=shlex.split(command)
                self.assertEqual(args[0],'kim_all');route=args[1]
                self.assertRegex(dispatcher,r'(?m)^    '+re.escape(route)+r'\)')
                self.assertTrue(any(line.startswith('_Name=') for line in lines))
                if '%F' in args:self.assertEqual(args[-2:],['--','%F'])
                if route!='recipe':
                    handler='photo_date' if route=='capturedate' else route
                    self.assertTrue('action_'+handler+'() {' in dispatcher,handler)
            self.assertEqual(set(declared),set(actual),path.name)
            self.assertCountEqual([a for a in declared if a!='_SEPARATOR_'],[a for a in actual if a!='_SEPARATOR_'],path.name)

    def test_date_menu_directions_have_distinct_installed_handlers(self):
        text=(ROOT/'src/kim_metadata.desktop.in').read_text()
        for title,command in [
            ('Set Photo Capture Date…','capturedate --interactive'),
            ('Adjust Photo Capture Date…','timeshift --interactive'),
            ('Set File Date from Photo Capture Date…','datesync --direction exif-to-file --interactive'),
            ('Set Photo Capture Date from File Date…','datesync --direction file-to-exif --interactive')]:
            self.assertIn('_Name='+title,text); self.assertIn('Exec=kim_all '+command+' -- %F',text)
        self.assertIn('image/*;',text);self.assertIn('application/x-photoshop;',text)

    def test_shared_helpers_are_all_installed_and_uninstalled(self):
        install=(ROOT/'install.sh').read_text();uninstall=(ROOT/'uninstall.sh').read_text()
        for name in ('kim_ui','kim_date_tools','kim_date_dialog','kim_filename','kim_job','kim_job_process','kim_action_dialog'):
            relative='bin/'+name+'.py'
            self.assertIn(relative,uninstall);self.assertGreaterEqual(install.count(relative),4,name)


if __name__=='__main__':unittest.main()
