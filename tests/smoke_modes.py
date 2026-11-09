"""Real CLI/FFmpeg synthetic end-to-end checks for all primary modes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli

root=Path(tempfile.mkdtemp(prefix='video-editor-modes-'))
source=root/'footage with spaces.mp4'
cli.run([cli.FF,'-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=4',
         '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
transcript=root/'words.json'
cli.write(transcript,{'s0':{'words':[{'start':.1,'end':.8,'text':'The problem.'},{'start':1.1,'end':1.8,'text':'A clear solution.'},
                                  {'start':2.1,'end':2.8,'text':'A surprising lesson.'},{'start':3.1,'end':3.8,'text':'The final result.'}]}})
def invoke(args):
    proc=subprocess.run(['node',str(cli.ROOT/'auto-edit.js'),*args,'--json'],capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    return json.loads(proc.stdout)
for mode in ['highlights','youtube','shorts']:
    out=root/f'{mode} organized'
    args=[mode,str(source),'--output',str(out),'--cache-dir',str(root/'cache'),'--transcript',str(transcript),'--target','1.6']
    if mode=='shorts': args+=['--count','2']
    first=invoke(args+['--preview'])
    for project in first['mode_projects']:
        p=cli.read(Path(project)/'project.json')
        p['exports']['youtube']=[320,180]; p['exports']['shorts']=[180,320]
        cli.save(Path(project),p)
    # Re-preview customized mode projects, then approve the exact revision.
    second=invoke(args+['--preview'])
    # Retry without re-importing: cached fingerprint avoids ASR/model access.
    retry_args=args.copy(); position=retry_args.index('--transcript'); del retry_args[position:position+2]
    final=invoke(retry_args+['--approve'])
    assert len(final['outputs'])==(2 if mode=='shorts' else 1)
    for output,video_file in zip(final['outputs'],final['video_files']):
        folder=Path(output); assert Path(video_file).exists()
        qa=cli.read(folder/'qa.json'); assert not qa['errors']
        video=next(s for s in qa['metadata']['streams'] if s['codec_type']=='video')
        assert video['height']>video['width'] if mode=='shorts' else video['width']>video['height']
        assert cli.read(folder/'manifest.json')['file']==video_file
        assert Path(video_file).parent==out
    assert not (source.parent/'edit').exists()
    workspace=Path(final['project'])
    assert (workspace/'reports').exists() and (workspace/'temporary').exists()
    assert not (out/'data').exists()
    assert len(list((workspace/'data/mode-cache').glob('*.json')))>=1
single=invoke(['highlights',str(source),'--cache-dir',str(root/'cache'),'--transcript',str(transcript),'--target','1.6'])
assert Path(single['video_files'][0]).parent==source.parent
assert not single['preview']
again=invoke(['highlights',str(source),'--cache-dir',str(root/'cache'),'--target','1.6'])
assert single['video_files'][0]!=again['video_files'][0]
bundle=invoke(['project',str(source),'--transcript',str(transcript),'--target','1.6','--count','2'])
assert len(bundle['video_files'])==4
for name in ['data','highlights','youtube','shorts','assets','temporary','reports']:
    assert (source.parent/(source.stem+'-edited-project')/name).is_dir()
for file in bundle['video_files']: assert Path(file).is_file()
text=invoke(['transcribe',str(source),'--cache-dir',str(root/'cache'),'--transcript',str(transcript)])
txt=Path(text['transcript_files'][0])
assert txt.parent==source.parent and txt.suffix=='.txt'
assert 'The problem.' in txt.read_text(encoding='utf-8')
assert 'The final result.' in txt.read_text(encoding='utf-8')
print('PASS all 3 modes, flat defaults, non-overwriting reruns, project bundle defaults, overrides, cached state, preview/approval and QA. Fixtures: '+str(root))
