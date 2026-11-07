"""Verify cut-only audio levels/dimensions using synthetic media, not listening claims."""
import array
import math
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli
import modes

def rms(file,start):
    proc=subprocess.run([cli.FF,'-v','error','-ss',str(start),'-i',str(file),'-t','0.5','-vn','-f','f32le','-acodec','pcm_f32le','-'],capture_output=True)
    if proc.returncode: raise ValueError(proc.stderr.decode('utf-8',errors='replace'))
    data=proc.stdout
    samples=array.array('f'); samples.frombytes(data)
    return math.sqrt(sum(x*x for x in samples)/len(samples))

root=Path(tempfile.mkdtemp(prefix='highlights-preservation-'))
source=root/'quiet mono recording.mp4'
cli.run([cli.FF,'-y','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=4',
    '-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=4','-af','volume=0.1',
    '-c:v','libx264','-c:a','aac',source])
p={'sources':{'s0':{'file':str(source),'metadata':cli.probe(source)}},
    'ranges':[{'source':'s0','start':0,'end':1},{'source':'s0','start':2,'end':3}],
    'settings':{'layout':'fit','caption':'tech','lufs':-14},'exports':{'youtube':[1920,1080]},'audio':[]}
modes.highlights_defaults(p,modes.parser().parse_args(['highlights',str(source)]))
out=cli.render(root,p,'youtube'); metadata=cli.probe(out)
v=next(s for s in metadata['streams'] if s['codec_type']=='video')
a=next(s for s in metadata['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'])==(640,360)
assert abs(float(v['avg_frame_rate'].split('/')[0])/float(v['avg_frame_rate'].split('/')[1])-24)<.01
assert a['channels']==1 and a['sample_rate']=='44100'
assert abs(cli.duration(metadata)-2)<.15
for original,edited in [(.2,.2),(2.2,1.2)]:
    difference=20*math.log10(rms(out,edited)/rms(source,original))
    assert abs(difference)<.25, difference
print('PASS: cuts only, native resolution/FPS, mono 44.1 kHz preserved, interior audio level difference <0.25 dB. '+str(out))
