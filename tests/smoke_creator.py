"""Synthetic integration; never calls transcription or AI services."""
import sys
import json
import subprocess
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli

folder=Path('output/synthetic-demo').resolve()
folder.mkdir(parents=True,exist_ok=True)
source=folder/'source with spaces.mp4'
cli.run([cli.FF,'-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=2',
         '-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
p={'version':1,'sources':{'s0':{'file':str(source),'metadata':cli.probe(source),
   'transcript':{'words':[{'start':.1,'end':.8,'text':'Olá mundo.'}]}}},
   'ranges':[{'source':'s0','start':0,'end':1},{'source':'s0','start':1,'end':2}],
   'settings':{'layout':'fit','caption':'tech','captions':True,'lufs':-14},
   'exports':{'youtube':[320,180],'shorts':[180,320]},'audio':[{'file':str(source),'gain':.1}]}
cli.save(folder,p)
for platform in p['exports']:
    out=cli.render(folder,p,platform)
    assert cli.qa(out)['decoded']
print('PASS: landscape, vertical, captions, audio mixing, concat, QA and manifests')

# Exercise the actual CLI contract, including reviewed candidate exports.
project_folder=folder/f'acceptance-{time.time_ns()}'
def invoke(*args, success=True):
    r=subprocess.run([sys.executable,str(Path(cli.__file__)),*args,'--project',str(project_folder),'--json'],capture_output=True,text=True,encoding='utf-8')
    assert (r.returncode==0)==success, r.stderr
    return json.loads(r.stdout if success else r.stderr)
invoke('init','--sources',str(source),str(source))
transcripts=folder/'fixture-words.json'
cli.write(transcripts,{'s0':{'words':[{'start':.1,'end':.8,'text':'First idea.'},{'start':1.1,'end':1.8,'text':'Different lesson.'}]}})
invoke('analyze','--transcript',str(transcripts))
patch=folder/'smoke-patch.json'
cli.write(patch,{'settings':{'captions':True},'exports':{'youtube':[320,180],'shorts':[180,320]}})
invoke('revise','--patch',str(patch))
versions=invoke('history')['versions']
proposal=invoke('plan','--target','.8')['plan_file']
invoke('validate-plan','--plan-file',proposal)
invoke('apply-plan','--plan-file',proposal)
assert 'error' in invoke('export',success=False)
invoke('frames')
invoke('repurpose','--count','2','--target','.8')
for index in ['1','2']:
    preview=invoke('preview','--clip',index,'--platforms','shorts')['files'][0]
    assert cli.qa(preview)['decoded']
    invoke('approve','--clip',index)
    final=invoke('export','--clip',index,'--platforms','shorts')['files'][0]
    meta=cli.probe(final)
    vd=float(next(s for s in meta['streams'] if s['codec_type']=='video')['duration'])
    ad=float(next(s for s in meta['streams'] if s['codec_type']=='audio')['duration'])
    assert abs(vd-ad)<.15, (vd,ad)
    assert not cli.read(Path(final).parent/'qa.json')['errors']
invoke('rollback','--version',versions[0])
assert len(invoke('inspect')['project']['sources'])==2
print('PASS: CLI multi-source import, transcript import, deep patch, plan validation/apply, approval gates, contact sheet, two clip previews/exports, stream duration sync, rollback')
