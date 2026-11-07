"""Manual, local-only benchmark. Supply approved audio; no transcript text printed.

python tests/benchmark_asr.py --audio output/asr-smoke/speech.wav
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import asr
from faster_whisper import WhisperModel

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audio',required=True)
args=parser.parse_args()
report={}
configs={'previous':{'cpu_threads':4,'beam_size':5,'vad_filter':False},
         'fast':{'cpu_threads':asr.options()['threads'],'beam_size':1,'vad_filter':True}}
for name,settings in configs.items():
    print(f'Benchmarking {name}...',file=sys.stderr,flush=True)
    model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=settings['cpu_threads'],local_files_only=True)
    times=[]; counts=[]
    for iteration in range(3):
        started=time.perf_counter()
        segments,_=model.transcribe(args.audio,word_timestamps=True,beam_size=settings['beam_size'],vad_filter=settings['vad_filter'])
        count=sum(len(seg.words or []) for seg in segments)
        elapsed=time.perf_counter()-started
        if iteration:
            times.append(elapsed); counts.append(count)
    report[name]={'seconds':times,'median_seconds':statistics.median(times),'word_counts':counts,'settings':settings}
    del model
report['speedup']=report['previous']['median_seconds']/report['fast']['median_seconds']
print(json.dumps(report,indent=2))
