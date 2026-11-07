import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import io
import contextlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli
import planning as plan

def project():
    tokens=[(0,1,'First'),(1,2,'idea.'),(3,4,'First'),(4,5,'idea.'),(8,9,'Porque'),(9,10,'aprendi.'),(12,13,'Fragment')]
    return {'version':1,'profile':'build-in-public','brand':{'private':'secret'},
        'sources':{'s0':{'file':'private-file.mp4','metadata':{'format':{'duration':'14'}},
        'transcript':{'words':[{'start':a,'end':b,'text':t} for a,b,t in tokens]}}},
        'ranges':[{'source':'s0','start':0,'end':14}],
        'settings':{'caption':'tech','layout':'fit','lufs':-14,'captions':True},'audio':[], 'exports':{'youtube':[320,180]}}

class PlanningTests(unittest.TestCase):
    def test_plan_selects_instead_of_full_source(self):
        p=project(); result=plan.local_plan(p,4)
        self.assertEqual(sum(r['end']-r['start'] for r in result['ranges']),4)
        self.assertTrue(plan.validate_plan(p,result)['valid'])
    def test_duplicate_and_incomplete_tail_removed(self):
        result=plan.local_plan(project(),60)
        self.assertEqual(len(result['ranges']),2)
        self.assertLess(max(r['end'] for r in result['ranges']),13)
    def test_include_exclude(self):
        rules={'include':[{'source':'s0','start':8,'end':10}], 'exclude':[{'source':'s0','start':0,'end':5}]}
        result=plan.local_plan(project(),1,rules)
        self.assertEqual(result['ranges'][0]['start'],8)
        plan.validate_plan(project(),result)
    def test_constraints_conflict_rejected(self):
        r={'source':'s0','start':0,'end':2}
        with self.assertRaises(ValueError): plan.local_plan(project(),10,{'include':[r],'exclude':[r]})
    def test_recursive_merge_preserves_settings(self):
        p=project(); changed=plan.merge(p,{'settings':{'caption':'shorts'}})
        self.assertEqual(changed['settings']['lufs'],-14)
        self.assertEqual(p['settings']['caption'],'tech')
    def test_unknown_patch_rejected(self):
        with self.assertRaises(ValueError): plan.merge(project(),{'settings':{'shell':'rm'}})
    def test_semantic_context_excludes_private_project_data(self):
        text=json.dumps(plan.semantic_context(project(),'brief',60,{}))
        self.assertNotIn('private-file',text); self.assertNotIn('secret',text)
        self.assertNotIn('metadata',text)
    def test_stale_plan_rejected(self):
        p=project(); proposed=plan.local_plan(p)
        p['settings']['caption']='shorts'
        with self.assertRaises(ValueError): plan.validate_plan(p,proposed)
    def test_word_midpoint_and_sentence_fragment_rejected(self):
        for a,b in [(0.5,2),(1,2),(0,1)]:
            proposed=plan.local_plan(project())
            proposed['ranges']=[{'source':'s0','start':a,'end':b,'reason':'test'}]
            with self.assertRaises(ValueError): plan.validate_plan(project(),proposed)
    def test_unknown_commands_rejected(self):
        proposed=plan.local_plan(project()); proposed['shell']='echo hello'
        with self.assertRaises(ValueError): plan.validate_plan(project(),proposed)
    def test_caption_pause_split(self):
        p=project(); p['settings']['caption']='cinematic'
        cues=cli.caption_cues(p)
        self.assertTrue(all(b-a<=2 for a,b,t in cues))
    def test_optional_settings_merge(self):
        p=project(); del p['settings']['captions']
        self.assertTrue(plan.merge(p,{'settings':{'captions':True}})['settings']['captions'])
    def test_unsafe_export_name_rejected(self):
        p=project(); p['exports']['../source']=[320,180]
        with self.assertRaises(ValueError): cli.validate(p)
    def test_overlapping_plan_rejected(self):
        p=project(); proposed=plan.local_plan(p); proposed['ranges']*=2
        with self.assertRaises(ValueError): plan.validate_plan(p,proposed)
    def test_semantic_adapter_validates_and_minimizes_request(self):
        with tempfile.TemporaryDirectory() as d:
            cli.save(Path(d),project())
            body={'choices':[{'message':{'content':json.dumps({'ranges':[{'source':'s0','start':0,'end':2,'reason':'Complete hook'}]})}}]}
            response=io.BytesIO(json.dumps(body).encode())
            with patch.dict(cli.os.environ,{'LLM_URL':'http://localhost/v1/chat/completions'}), patch.object(sys,'argv',['cli.py','plan','--project',d,'--semantic']), patch.object(cli.urllib.request,'urlopen',return_value=response) as request, contextlib.redirect_stdout(io.StringIO()) as output:
                cli.main()
            result=json.loads(output.getvalue())
            self.assertTrue(result['valid'])
            sent=json.loads(request.call_args.args[0].data)
            self.assertNotIn('private-file',json.dumps(sent))
            self.assertNotIn('secret',json.dumps(sent))
    def test_malformed_words_rejected(self):
        p=project(); p['sources']['s0']['transcript']['words'][0]['end']=float('nan')
        with self.assertRaises(ValueError): cli.validate(p)
    def test_nonfinite_audio_rejected(self):
        p=project(); p['audio']=[{'file':__file__,'gain':float('nan')}]
        with self.assertRaises(ValueError): cli.validate(p)
    def test_candidate_rebase_rejected(self):
        p=project(); candidate=plan.local_plan(p,2); p['ranges']=candidate['ranges']
        with self.assertRaises(ValueError): plan.validate_plan(p,candidate)
    def test_cli_json_plan_apply_rollback(self):
        script=Path(cli.__file__)
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); cli.save(folder,project())
            def invoke(*args):
                r=subprocess.run([sys.executable,str(script),*args,'--project',d,'--json'],capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(r.returncode,0,r.stderr)
                return json.loads(r.stdout)
            old=invoke('history')['versions'][0]
            proposal=invoke('plan','--target','4')['plan_file']
            invoke('validate-plan','--plan-file',proposal)
            invoke('apply-plan','--plan-file',proposal)
            self.assertEqual(len(invoke('inspect')['project']['ranges']),2)
            invoke('rollback','--version',old)
            self.assertEqual(invoke('inspect')['project']['ranges'][0]['end'],14)

if __name__=='__main__': unittest.main()
