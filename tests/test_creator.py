import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli

class ProjectTests(unittest.TestCase):
    def test_zero_duration_asr_words_keep_text(self):
        class ProviderFloat(float): pass
        result=cli.normalize_asr_words([{'start':0,'end':0,'text':'First'}, {'start':ProviderFloat(0),'end':ProviderFloat(1),'text':'idea'}, {'start':1,'end':1,'text':'.'}])
        self.assertEqual(len(result),1)
        self.assertIs(type(result[0]['start']),float)
        self.assertEqual(result[0]['text'],'First idea .')
        self.assertGreater(result[0]['end'],result[0]['start'])
    def test_local_setup_uses_editor_interpreter(self):
        with patch.object(sys,'argv',['cli.py','install-asr']), patch.object(cli.subprocess,'run') as install:
            cli.main()
        install.assert_called_once_with([sys.executable,'-m','pip','install','-r',str(cli.ROOT/'requirements-local.txt')],check=True)
    def project(self):
        return {'sources':{'s0':{'metadata':{'format':{'duration':'5'}}, 'transcript':{'words':[{'start':1,'end':2,'text':'Olá mundo'}]}}},
                'ranges':[{'source':'s0','start':0,'end':3}], 'settings':{'layout':'fit','caption':'tech'},'audio':[]}
    def test_invalid_range(self):
        p=self.project(); p['ranges'][0]['end']=10
        with self.assertRaises(ValueError): cli.validate(p)
    def test_nonfinite_range(self):
        p=self.project(); p['ranges'][0]['end']=float('nan')
        with self.assertRaises(ValueError): cli.validate(p)
    def test_caption_offset(self):
        p=self.project(); p['ranges']*=2
        self.assertEqual([x[0] for x in cli.caption_cues(p)],[1,4])
    def test_unicode_history(self):
        with tempfile.TemporaryDirectory() as d:
            cli.save(Path(d),self.project())
            self.assertEqual(cli.read(Path(d)/'project.json'),self.project())
            self.assertEqual(len(list((Path(d)/'history').glob('*.json'))),1)
    def test_missing_audio_asset(self):
        p=self.project(); p['audio']=[{'file':'missing.wav'}]
        with self.assertRaises(ValueError): cli.validate(p)
    def test_platforms(self):
        for size in cli.PLATFORMS.values():
            self.assertTrue(all(n>0 and n%2==0 for n in size))
    def test_stamp(self):
        self.assertEqual(cli.stamp(61.123),'00:01:01,123')

if __name__=='__main__': unittest.main()
