import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import modes
import cli
from test_planning import project

class ModesTests(unittest.TestCase):
    def test_readable_preview_completion(self):
        result={'preview':True,'mode':'highlights','outputs':['output/path with spaces'], 'project':'output/project','log':'output/run.log'}
        text=modes.completion_message(result,['highlights',"John's $video.mp4",'--preview','--target','60'])
        self.assertIn('Preview ready',text)
        self.assertIn('preview.mp4',text)
        self.assertIn("'John''s $video.mp4'",text)
        self.assertIn("'--approve'",text)
        self.assertNotIn("'--preview'",text)
    def test_final_completion_does_not_request_another_export(self):
        result={'preview':False,'mode':'youtube','outputs':['output/job'], 'project':'output/project','log':'output/run.log'}
        text=modes.completion_message(result,['youtube','input.mp4','--approve'])
        self.assertIn('Final video ready',text)
        self.assertIn('final.mp4',text)
        self.assertNotIn('npm run',text)
    def test_json_output_is_explicit(self):
        self.assertFalse(modes.parser().parse_args(['highlights','input.mp4']).json)
        self.assertTrue(modes.parser().parse_args(['highlights','input.mp4','--json']).json)
    def test_parser_spaces_and_options(self):
        args=modes.parser().parse_args(['shorts','my video.mp4','--target','1m30s','--output','my output','--profile','personal-essays','--count','2','--preview'])
        self.assertEqual(args.target,90); self.assertEqual(args.sources,['my video.mp4'])
    def test_invalid_options(self):
        with self.assertRaises(SystemExit): modes.parser().parse_args(['youtube','a','--unknown'])
        with self.assertRaises(SystemExit): modes.parser().parse_args(['youtube','a','--target','-1'])
    def test_mode_strategies_are_different(self):
        p=project(); rules={'include':[],'exclude':[]}
        highlights=modes.strategy(p,'highlights',2,rules)
        youtube=modes.strategy(p,'youtube',None,rules)
        self.assertGreater(len(youtube['ranges']),len(highlights['ranges']))
        clips=modes.shorts_plans(p,2,3,rules)
        self.assertGreaterEqual(len(clips),2)
    def test_music_preservation(self):
        p=project(); p['profile']='music'
        self.assertIsNone(modes.strategy(p,'youtube',None,{}))
    def test_failure_preserves_state_and_retry_uses_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source with spaces.mp4'; source.touch()
            output=root/'organized output'; p=project(); p['sources']['s0']['file']=str(source)
            cli.save(output/'data',p)
            args=modes.parser().parse_args(['youtube',str(source),'--output',str(output)])
            args._bundle_root=str(output)
            # No installed ASR/model required: simulate failure in transcription adapter.
            with patch.object(modes,'invoke',side_effect=ValueError('ASR interrupted')):
                with self.assertRaisesRegex(ValueError,'diagnostics retained'): modes.execute_mode(args)
            self.assertTrue((output/'data/project.json').exists())
            self.assertIn('ASR interrupted',next((output/'reports').glob('*.log')).read_text())
            self.assertFalse((root/'edit').exists())
            def invoke(command,*args): return {}
            with patch.object(modes,'invoke',side_effect=invoke), patch.object(cli,'render',side_effect=KeyboardInterrupt()):
                with self.assertRaisesRegex(ValueError,'diagnostics retained'): modes.execute_mode(args)
            self.assertTrue((output/'data/project.json').exists())
    def test_approve_without_preview_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'s.mp4'; source.touch()
            p=project(); p['sources']['s0']['file']=str(source); cli.save(root/'data',p)
            args=modes.parser().parse_args(['youtube',str(source),'--output',directory,'--approve'])
            args._bundle_root=directory
            with patch.object(modes,'invoke',return_value={}):
                with self.assertRaisesRegex(ValueError,'matching preview'): modes.execute_mode(args)
    def test_flat_destination_cache_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); source=folder/'video.mp4'; source.write_bytes(b'original')
            args=modes.parser().parse_args(['highlights',str(source),'--cache-dir',str(folder/'cache')])
            self.assertNotEqual(modes.workspace(args,[str(source)]),folder)
            a=modes.publish_file(source,folder,'video-highlights')
            b=modes.publish_file(source,folder,'video-highlights')
            self.assertNotEqual(a,b); self.assertEqual(source.read_bytes(),b'original')
    def test_project_requests_all_modes(self):
        args=modes.parser().parse_args(['highlights','video.mp4','--project'])
        result={'outputs':[],'video_files':[],'mode_projects':[],'log':'log'}
        with patch.object(modes,'execute_mode',return_value=result) as run:
            modes.execute(args)
        self.assertEqual([c.args[0].mode for c in run.call_args_list],['youtube','highlights','shorts'])

if __name__=='__main__': unittest.main()
