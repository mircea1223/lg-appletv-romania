"""Portable profile checks; no Apple files, network, or TV access."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_patch
import c2_profile
import prepare_bundle


class ProfileTests(unittest.TestCase):
    def test_uid_profiles_are_exact_and_unique(self):
        profiles = json.loads((ROOT / 'developer_mode_profiles.json').read_text())['profiles']
        identities = [tuple(p[k] for k in ('modelName','firmwareVersion','sdkVersion')) for p in profiles]
        self.assertEqual(len(set(identities)), len(profiles))
        self.assertEqual(len(profiles), 2)

    def test_c2_transaction_protects_native_inputs_and_image(self):
        source = (ROOT / 'tools/overlay_transaction.js').read_text()
        result = prepare_bundle.adapt_c2_transaction(source, build_patch)
        for digest in list(c2_profile.PROTECTED.values()) + [c2_profile.IMAGE_SHA]:
            self.assertIn(digest, result)
        for digest in build_patch.PROTECTED_FILES.values():
            self.assertNotIn(digest, result)
        self.assertIn('function rollback(', result)

    @unittest.skipUnless(shutil.which('node'), 'Node required for guard execution')
    def test_both_overlay_guards_fail_closed(self):
        source = (ROOT / 'tools/overlay_transaction.js').read_text()
        for profile in ('c3', 'c2'):
            with self.subTest(profile=profile):
                text = prepare_bundle.adapt_c2_transaction(source, build_patch) if profile == 'c2' else source
                guard = text[text.index('function guardOverlay()'):text.index('function target(')]
                upper = c2_profile.UPPER if profile == 'c2' else '/media/data/data/com.apple.appletv'
                row = '1 2 0:64 / ' + c2_profile.UPPER + ' rw,relatime - overlay overlay rw,lowerdir=' + c2_profile.LOWER + ',upperdir=' + upper + ',workdir=' + c2_profile.WORK
                cases = [(row, True), (row.replace('upperdir=', 'wrong='), False),
                         (row.replace(' rw,relatime ', ' ro,relatime '), False),
                         (row+'\n'+row, False)]
                if profile == 'c2':
                    cases += [(row.replace('lowerdir=', 'wrong='), False),
                              (row.replace('workdir=', 'wrong='), False)]
                script = '''const vm=require('vm'); const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
                for(const [row,accepted] of input.cases){
                  const ctx={app:input.app,fs:{readFileSync:()=>row},directory:()=>({gid:5000,mode:0o775}),assert:(v,m)=>{if(!v)throw Error(m)}};
                  vm.createContext(ctx);vm.runInContext(input.guard,ctx);let ok=true;
                  try{ctx.guardOverlay()}catch(e){ok=false}
                  if(ok!==accepted)throw Error('Guard accepted wrong mount or rejected valid mount');
                }'''
                subprocess.run(['node','-e',script],input=json.dumps({'guard':guard,'app':c2_profile.UPPER,'cases':cases}),text=True,check=True,capture_output=True)

    def test_builder_rejects_other_profile_native_inputs(self):
        # A bounded synthetic source must fail before producing any patch output.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            (source / 'res').mkdir(parents=True)
            js = {name: name.encode() for name in build_patch.ORIGINAL_JS}
            for name, data in js.items():
                (source / 'res' / name).write_bytes(data)
            (source / 'AppleTV').write_bytes(b'wrong native binary')
            with patch.dict(build_patch.ORIGINAL_JS, {name:build_patch.sha256(data) for name,data in js.items()}):
                for profile in (None, 'c2'):
                    with self.subTest(profile=profile), self.assertRaises(build_patch.PatchError):
                        build_patch.build(source, root/'output', profile)
                    self.assertFalse((root/'output').exists())


if __name__ == '__main__':
    unittest.main()
