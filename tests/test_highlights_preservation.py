import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli
import modes

def project():
    return {'sources':{'s0':{'file':'source.mp4','metadata':{'format':{'duration':'4'},'streams':[
        {'codec_type':'video','width':640,'height':360,'avg_frame_rate':'24/1'},
        {'codec_type':'audio','sample_rate':'44100','channels':1}]}}},
        'ranges':[{'source':'s0','start':0,'end':1}], 'exports':{'youtube':[1920,1080]},
        'settings':{'layout':'fit','caption':'tech','lufs':-14}, 'audio':[]}

class PreservationTests(unittest.TestCase):
    def test_highlights_overrides_old_cached_processing(self):
        p=project(); p['audio']=[{'file':'music.wav'}]
        args=modes.parser().parse_args(['highlights','source.mp4'])
        modes.highlights_defaults(p,args)
        self.assertIsNone(p['settings']['lufs']); self.assertEqual(p['audio'],[])
        self.assertTrue(p['settings']['preserve_source']); self.assertFalse(p['settings']['captions'])
        args.platforms='shorts'; modes.highlights_defaults(p,args)
        self.assertFalse(p['settings']['preserve_source'])
    def test_no_audio_filters_and_single_aac_encode(self):
        p=project(); modes.highlights_defaults(p,modes.parser().parse_args(['highlights','source.mp4']))
        with tempfile.TemporaryDirectory() as folder, patch.object(cli,'run',return_value='') as run, patch.object(cli,'qa',return_value={'errors':[]}):
            cli.render(Path(folder),p,'youtube')
        commands=[call.args[0] for call in run.call_args_list]
        text=str(commands)
        self.assertNotIn('loudnorm',text); self.assertNotIn('afade',text)
        self.assertNotIn('sidechaincompress',text)
        self.assertEqual(sum('aac' in cmd for cmd in commands),1)
        self.assertIn('pcm_s16le',text)
        self.assertIn('scale=640:360',text)
        self.assertEqual(commands[0][commands[0].index('-r')+1],'24/1')

if __name__=='__main__': unittest.main()
