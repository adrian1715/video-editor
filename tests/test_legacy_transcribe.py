"""Exercise the real Node legacy entry function with simulated ASR/FFmpeg only."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r'''
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { main } = require('./transcribe');
const root = process.argv[1];
const argv = JSON.parse(process.argv[2]);
const failure = process.argv[3] === 'failure';
let work;
const dependencies = {
  lib: { os: { tmpdir: () => root, cpus: () => [1, 2] }, findWhisper: () => 'mock-whisper',
    probe: () => ({ hasAudio: true, duration: 3 }),
    runFfmpeg: async (args) => { fs.writeFileSync(args.at(-1), 'test audio'); } },
  ensureModel: async () => 'mock-model.bin',
  runWhisper: async (_, options) => {
    work = options.outDir;
    assert.notEqual(work, path.dirname(path.resolve(argv[0])));
    if (failure) throw new Error('simulated whisper failure');
    return { language: 'pt', segments: [{ start: 0, end: 2, text: 'Olá mundo.' }] };
  },
};
main(argv, dependencies).then(files => {
  assert.equal(fs.existsSync(work), false);
  console.log(JSON.stringify(files));
}).catch(error => {
  console.log(JSON.stringify({ error: error.message, work, retained: work && fs.existsSync(work) }));
});
'''

class LegacyDestinationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.source=self.root/'footage with spaces.mp4'; self.source.write_bytes(b'original')
    def tearDown(self): self.temp.cleanup()
    def invoke(self,*args,failure=False):
        result=subprocess.run(['node','-e',SCRIPT,str(self.root),json.dumps([str(self.source),*args]),'failure' if failure else ''],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout.splitlines()[-1])
    def test_default_beside_source_and_only_exports(self):
        files=self.invoke()
        self.assertEqual(Path(files['txt']).parent,self.source.parent/'footage with spaces-transcript')
        self.assertEqual(Path(files['txt']).name,'transcript.txt')
        self.assertEqual(sorted(p.name for p in Path(files['txt']).parent.iterdir()),['meta.json','transcript.srt','transcript.txt'])
        self.assertIn('Olá mundo.',Path(files['txt']).read_text(encoding='utf-8'))
        self.assertIn('00:00:00,000 --> 00:00:02,000',Path(files['srt']).read_text())
        self.assertEqual(self.source.read_bytes(),b'original')
        self.assertFalse((self.root/'audio.wav').exists())
    def test_custom_destination_and_matching_suffixes(self):
        dest=self.root/'custom notes'
        first=self.invoke('--output',str(dest)); second=self.invoke('--output',str(dest))
        self.assertEqual(Path(first['txt']).parent.parent,dest)
        for extension in ['txt','srt','meta']:
            self.assertNotEqual(first[extension],second[extension])
        self.assertEqual(Path(second['meta']).parent.name,'footage with spaces-transcript-1')
        self.assertEqual(Path(second['meta']).name,'meta.json')
    def test_missing_output_rejected_before_work(self):
        result=self.invoke('--output')
        self.assertIn('--output requires',result['error'])
        self.assertIsNone(result.get('work'))
    def test_failure_retains_temporary_evidence(self):
        result=self.invoke(failure=True)
        self.assertIn('Temporary files retained',result['error'])
        self.assertTrue(result['retained'])
        self.assertFalse(list(self.root.glob('*-transcript.txt')))
    def test_existing_sidecar_reserves_whole_new_set(self):
        (self.root/'footage with spaces-transcript').write_text('existing')
        files=self.invoke()
        self.assertEqual(Path(files['txt']).parent.name,'footage with spaces-transcript-1')
        self.assertEqual((self.root/'footage with spaces-transcript').read_text(),'existing')

if __name__=='__main__': unittest.main()
