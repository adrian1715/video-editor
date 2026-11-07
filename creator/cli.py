"""Persistent creator projects. Standard library only; FFmpeg is the renderer."""
import argparse
import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
from planning import merge, words, local_plan, validate_plan, revision, semantic_context, constraints, finite

ROOT = Path(__file__).resolve().parent.parent
FF = os.environ.get('FFMPEG', 'ffmpeg')
PROBE = os.environ.get('FFPROBE', 'ffprobe')
PROFILES = {
    'build-in-public': {'caption': 'tech', 'layout': 'fit', 'lufs': -14},
    'personal-essays': {'caption': 'cinematic', 'layout': 'fit', 'lufs': -16},
    'music': {'caption': 'cinematic', 'layout': 'fit', 'lufs': None},
    'creative-storytelling': {'caption': 'cinematic', 'layout': 'fit', 'lufs': -16},
    'social-shorts': {'caption': 'shorts', 'layout': 'fit', 'lufs': -14},
}
PLATFORMS = {'youtube': [1920, 1080], 'shorts': [1080, 1920],
             'instagram': [1080, 1920], 'tiktok': [1080, 1920],
             'x': [1280, 720], 'linkedin': [1920, 1080], 'square': [1080, 1080]}
STYLES = {'tech': {'words': 3, 'size': 22, 'margin': 85, 'bold': 1},
          'cinematic': {'words': 8, 'size': 18, 'margin': 65, 'bold': 0},
          'shorts': {'words': 2, 'size': 26, 'margin': 90, 'bold': 1}}
RUN_LOG = None

def run(args):
    r = subprocess.run([str(a) for a in args], capture_output=True, encoding='utf-8', errors='replace')
    if RUN_LOG:
        with Path(RUN_LOG).open('a',encoding='utf-8') as log:
            log.write(json.dumps({'argv':[str(a) for a in args],'returncode':r.returncode})+'\n'+r.stdout+r.stderr+'\n')
    if r.returncode:
        raise ValueError(r.stderr[-4000:] or r.stdout[-4000:])
    return r.stdout

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)

def probe(path):
    return json.loads(run([PROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path]))

def duration(meta):
    return float(meta['format']['duration'])

def normalize_asr_words(items):
    """Attach zero-duration ASR markers to adjacent timed words, retaining text."""
    result=[]; pending=[]
    for item in items:
        word=dict(item)
        # Whisper can expose NumPy scalar timestamps; normalize provider types
        # before the strict JSON-number validator runs.
        word['start']=float(word['start']); word['end']=float(word['end'])
        if word['end']<=word['start']:
            if result: result[-1]['text'] += ' '+word['text'].strip()
            else: pending.append(word['text'].strip())
            continue
        if pending:
            word['text']=' '.join(pending)+' '+word['text'].strip(); pending=[]
        result.append(word)
    if pending: raise ValueError('ASR returned text without any usable word timestamps')
    return result

def validate(p):
    if not isinstance(p, dict) or not isinstance(p.get('sources'), dict) or not p['sources']:
        raise ValueError('Project needs a nonempty sources object')
    if not isinstance(p.get('settings'),dict) or not isinstance(p.get('ranges'),list):
        raise ValueError('Project settings/ranges have invalid types')
    for source in p['sources'].values():
        words(source)
        if not finite(duration(source['metadata'])) or duration(source['metadata'])<=0:
            raise ValueError('Source duration must be finite and positive')
    if 'exports' in p:
        if not isinstance(p['exports'],dict): raise ValueError('exports must be an object')
        for name, dimensions in p['exports'].items():
            if not re.fullmatch(r'[a-zA-Z0-9_-]+',name): raise ValueError('Unsafe export profile name')
            if not isinstance(dimensions,list) or len(dimensions)!=2 or not all(type(x)==int and 16<=x<=7680 and x%2==0 for x in dimensions):
                raise ValueError('Export dimensions must be even integers between 16 and 7680')
    if not p.get('ranges'):
        raise ValueError('EDL requires at least one range')
    for r in p['ranges']:
        if not isinstance(r,dict) or not all(k in r for k in ['source','start','end']): raise ValueError('Invalid range object')
        if r['source'] not in p['sources']:
            raise ValueError('Unknown EDL source')
        a, b = r['start'], r['end']
        if not all(finite(x) for x in [a, b]) or not 0 <= a < b <= duration(p['sources'][r['source']]['metadata']) + .001:
            raise ValueError('EDL range outside source duration')
    if p['settings']['layout'] not in ['fit', 'crop']:
        raise ValueError('layout must be fit or crop')
    if p['settings']['caption'] not in STYLES:
        raise ValueError('Unknown caption style')
    fps = p['settings'].get('fps', 30)
    if not finite(fps) or not 1 <= fps <= 120:
        raise ValueError('fps must be between 1 and 120')
    lufs = p['settings'].get('lufs')
    if lufs is not None and (not finite(lufs) or not -40 <= lufs <= -5):
        raise ValueError('lufs must be null or between -40 and -5')
    if 'captions' in p['settings'] and type(p['settings']['captions']) != bool:
        raise ValueError('captions must be boolean')
    for name in ['preserve_audio','preserve_source']:
        if name in p['settings'] and type(p['settings'][name]) != bool:
            raise ValueError(name+' must be boolean')
    if not isinstance(p.get('audio',[]),list): raise ValueError('audio must be an array')
    for track in p.get('audio', []):
        if not isinstance(track,dict) or not isinstance(track.get('file'),str): raise ValueError('Invalid audio track')
        if not Path(track['file']).is_file() or not finite(track.get('start',0)) or track.get('start', 0) < 0 or not finite(track.get('gain',1)) or not 0 <= track.get('gain', 1) <= 10:
            raise ValueError('Invalid audio asset, start, or gain')

def save(folder, p):
    validate(p)
    write(folder / 'history' / f'{time.time_ns()}.json', p)
    write(folder / 'project.json', p)

def caption_cues(p):
    cues, offset = [], 0
    size = STYLES[p['settings']['caption']]['words']
    for r in p['ranges']:
        words = p['sources'][r['source']].get('transcript', {}).get('words', [])
        words = [w for w in words if w.get('type', 'word') == 'word' and r['start'] <= w['start'] < w['end'] <= r['end']]
        groups, chunk = [], []
        for word in words:
            if chunk and (word['start']-chunk[-1]['end']>.5 or len(chunk)>=size):
                groups.append(chunk); chunk=[]
            chunk.append(word)
        if chunk: groups.append(chunk)
        for chunk in groups:
            cues.append((chunk[0]['start']-r['start']+offset, chunk[-1]['end']-r['start']+offset, ' '.join(w['text'] for w in chunk)))
        offset += r['end']-r['start']
    return cues

def stamp(t):
    ms = round(t*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def render(folder, p, platform, preview=False):
    validate(p)
    w, h = p['exports'].get(platform, PLATFORMS.get(platform, [0, 0]))
    preserve_audio=p['settings'].get('preserve_audio',False)
    native=p['settings'].get('preserve_source',False)
    first=p['sources'][p['ranges'][0]['source']]['metadata']
    first_video=next(s for s in first['streams'] if s['codec_type']=='video')
    first_audio=next((s for s in first['streams'] if s['codec_type']=='audio'),{})
    rate=str(p['settings'].get('fps',30))
    if native:
        w,h=int(first_video['width']),int(first_video['height'])
        if any(abs(float(s.get('rotation',0)))%180==90 for s in first_video.get('side_data_list',[])): w,h=h,w
        w,h=w//2*2,h//2*2
        rate=first_video.get('avg_frame_rate','0/0')
        if rate in ['0/0','0','']: rate=first_video.get('r_frame_rate','30')
    if not all(isinstance(x, int) and x > 0 and x % 2 == 0 for x in [w, h]):
        raise ValueError('Export dimensions must be positive even integers')
    if preview:
        w, h = w//4*2, h//4*2
    job = folder / 'renders' / f'{platform}-{time.time_ns()}'
    job.mkdir(parents=True)
    parts = []
    for i, r in enumerate(p['ranges']):
        src = p['sources'][r['source']]
        d = r['end']-r['start']
        scale = f'scale={w}:{h}:force_original_aspect_ratio=' + ('increase' if p['settings']['layout'] == 'crop' else 'decrease')
        scale += f',crop={w}:{h}' if p['settings']['layout'] == 'crop' else f',pad={w}:{h}:(ow-iw)/2:(oh-ih)/2'
        args = [FF, '-y', '-v', 'error', '-ss', str(r['start']), '-i', src['file']]
        audio = any(s['codec_type'] == 'audio' for s in src['metadata']['streams'])
        if not audio:
            args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        # MOV supports PCM and precise video timebases; Matroska's millisecond
        # timestamps introduce avoidable rounding when rejoining short cuts.
        part = job / f'{i}.mov' if preserve_audio else job / f'{i}.mp4'
        args += ['-t', str(d), '-map', '0:v:0', '-map', '0:a:0' if audio else '1:a:0', '-vf', scale+',setsar=1',
                 '-r', str(rate), '-c:v', 'libx264', '-preset', 'ultrafast' if preview else 'fast',
                 '-crf', '24' if preview else '20', '-pix_fmt', 'yuv420p']
        if preserve_audio:
            args += ['-c:a','pcm_s16le','-ar',str(first_audio.get('sample_rate',48000)),'-ac',str(first_audio.get('channels',2))]
        else:
            args += ['-af', f'aresample=48000,afade=t=in:d=0.03,afade=t=out:st={max(0,d-.03)}:d=0.03','-c:a','aac','-ac','2']
        run_args=args+[part]
        run(run_args)
        parts.append(part)
    (job/'concat.txt').write_text(''.join(f"file '{x.name}'\n" for x in parts), encoding='utf-8')
    base = job/('base.mov' if preserve_audio else 'base.mp4')
    run([FF, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', job/'concat.txt', '-c', 'copy', base])
    cues = caption_cues(p)
    (job/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{t}' for i,(a,b,t) in enumerate(cues)), encoding='utf-8')
    args = [FF, '-y', '-v', 'error', '-i', base]
    filters, mix = [], '[0:a]'
    tracks = [] if preserve_audio else p.get('audio', [])
    for i, track in enumerate(tracks, 1):
        args += ['-i', track['file']]
        delay = round(track.get('start', 0)*1000)
        filters.append(f'[{i}:a]volume={track.get("gain",1)},adelay={delay}:all=1,apad[t{i}]')
    if tracks:
        labels = ''.join(f'[t{i}]' for i in range(1,len(tracks)+1))
        filters += [f'{labels}amix=inputs={len(tracks)}:normalize=0[bed]', '[0:a]asplit[voice][side]',
                    '[bed][side]sidechaincompress=threshold=0.03:ratio=8[duck]', '[voice][duck]amix=inputs=2:normalize=0:duration=first[mix]']
        mix = '[mix]'
    if preserve_audio:
        args += ['-map','0:v','-map','0:a']
    else:
        lufs = p['settings'].get('lufs')
        filters.append(f'{mix}'+(f'loudnorm=I={lufs}:TP=-1:LRA=11' if lufs is not None else 'anull')+'[audio]')
        args += ['-filter_complex', ';'.join(filters), '-map', '0:v', '-map', '[audio]']
    if p['settings'].get('captions'):
        if not cues:
            raise ValueError('Captions requested but no word transcript exists')
        style = STYLES[p['settings']['caption']]
        # Relative subtitle filename avoids Windows drive/FFmpeg escaping issues.
        sub = str((job/'captions.srt').resolve()).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
        args += ['-vf', f"subtitles='{sub}':force_style='FontSize={style['size']},MarginV={style['margin']},Bold={style['bold']}'", '-c:v', 'libx264']
    else:
        args += ['-c:v', 'copy']
    out = job/'final.mp4'
    run(args+['-c:a', 'aac', '-b:a','192k','-movflags', '+faststart', out])
    report = qa(out, w, h, sum(r['end']-r['start'] for r in p['ranges']))
    write(job/'qa.json', report)
    write(job/'manifest.json', {'platform': platform, 'file': str(out), 'project': p, 'qa': report})
    return out

def qa(file, width=None, height=None, expected=None):
    meta = probe(file)
    errors, warnings = [], []
    streams = meta['streams']
    video = next((s for s in streams if s['codec_type']=='video'), None)
    if not video:
        errors.append('Missing video')
    if not any(s['codec_type']=='audio' for s in streams):
        errors.append('Missing audio')
    if video and width and (video['width'], video['height']) != (width, height):
        errors.append('Resolution mismatch')
    if expected and abs(duration(meta)-expected) > .25:
        errors.append('Duration mismatch')
    run([FF, '-v', 'error', '-i', file, '-f', 'null', '-'])
    warnings.append('Creative review, black-frame analysis, clipping and loudness measurement not performed')
    return {'errors': errors, 'warnings': warnings, 'decoded': True, 'fully_verified': False, 'metadata': meta}

def main():
    parser = argparse.ArgumentParser(description='Persistent creator editor; legacy npm commands remain available')
    parser.add_argument('command', choices=['install-asr','test','doctor','init','inspect','frames','validate-plan','apply-plan','approve','analyze','transcribe','plan','repurpose','render','preview','export','qa','profiles','revise','feedback','history','rollback'])
    default_cache=(Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'VideoEditor'/'Cache' if os.name=='nt' else Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'video-editor')
    parser.add_argument('--project', default=str(default_cache/'advanced-project'))
    parser.add_argument('--sources', nargs='+')
    parser.add_argument('--profile', choices=list(PROFILES), default='build-in-public')
    parser.add_argument('--platforms', default='youtube')
    parser.add_argument('--instructions', default='Select complete, meaningful ideas. Preserve context.')
    parser.add_argument('--semantic', action='store_true', help='Upload transcript text to configured LLM')
    parser.add_argument('--transcript', help='Import source-keyed word transcript JSON')
    parser.add_argument('--patch', help='JSON object patch: merge objects recursively; replace arrays')
    parser.add_argument('--version', help='History filename to restore')
    parser.add_argument('--file', help='Output file to QA')
    parser.add_argument('--provider', choices=['local','scribe'], default='local')
    parser.add_argument('--allow-upload', action='store_true')
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--target', type=float, default=60, help='Desired duration in seconds; complete/required ideas may exceed it')
    parser.add_argument('--constraints', help='JSON include/exclude source ranges')
    parser.add_argument('--plan-file', help='Structured editing plan JSON')
    parser.add_argument('--clip', type=int, help='1-based candidate index; export only this approved candidate')
    parser.add_argument('--source', default='s0')
    parser.add_argument('--decision', choices=['accepted','rejected','note'], default='note')
    parser.add_argument('--json', action='store_true', help='JSON result on stdout; progress on stderr')
    args = parser.parse_args()
    if args.command == 'install-asr':
        subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements-local.txt')],check=True)
        return
    if args.command == 'test':
        for directory in ['tests', 'video-use/tests']:
            subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/directory),'-v'], check=True)
        return
    folder = Path(args.project).resolve()
    def emit(data):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.command == 'doctor':
        import importlib.util
        print(json.dumps({**{tool: bool(shutil.which(tool)) for tool in [FF, PROBE]},
                          'python':sys.executable,'local_asr_installed':importlib.util.find_spec('faster_whisper') is not None,
                          'local_asr_setup':'npm run setup:local','model':os.environ.get('WHISPER_MODEL','small')}, indent=2)); return
    if args.command == 'profiles':
        print(json.dumps({'content': PROFILES, 'platforms': PLATFORMS, 'captions': STYLES}, indent=2)); return
    if args.command == 'init':
        if (folder/'project.json').exists():
            raise ValueError('Project exists; choose another directory')
        sources = {f's{i}': {'file': str(Path(f).resolve()), 'metadata': probe(f)} for i,f in enumerate(args.sources or [])}
        if any(not any(s['codec_type']=='video' for s in v['metadata']['streams']) for v in sources.values()):
            raise ValueError('All sources must contain video streams')
        p = {'version':1, 'sources':sources, 'ranges':[{'source': k,'start':0,'end':duration(v['metadata'])} for k,v in sources.items()],
             'profile':args.profile, 'brand':{'motto':'Underdogs Win.'}, 'settings':PROFILES[args.profile].copy(), 'exports':PLATFORMS.copy(), 'audio':[]}
        save(folder,p); emit({'project':str(folder),'revision':revision(p)}); return
    if args.command == 'qa':
        report = qa(args.file); write(folder/'qa.json',report); print(json.dumps(report,indent=2)); return
    p = read(folder/'project.json')
    validate(p)
    if args.command == 'inspect':
        emit({'schema_version':1,'revision':revision(p),'project':p}); return
    if args.command == 'frames':
        if args.source not in p['sources']: raise ValueError('Unknown source')
        source=p['sources'][args.source]
        job=folder/'inspection'/str(time.time_ns()); job.mkdir(parents=True)
        file=job/'contact-sheet.jpg'
        run([FF,'-y','-v','error','-i',source['file'],'-vf',f'fps=8/{duration(source["metadata"])},scale=320:-2,tile=4x2','-frames:v','1',file])
        emit({'file':str(file),'source':args.source,'interval_seconds':duration(source['metadata'])/8}); return
    if args.command in ['validate-plan','apply-plan']:
        if not args.plan_file: raise ValueError('--plan-file required')
        plan=read(args.plan_file); result=validate_plan(p,plan)
        if args.command=='apply-plan':
            p['ranges']=plan['ranges']; save(folder,p)
        emit({**result,'revision':revision(p),'applied':args.command=='apply-plan'}); return
    if args.command == 'approve':
        approved=p
        if args.clip is not None:
            candidates=read(folder/'candidates.json')
            if not 1<=args.clip<=len(candidates): raise ValueError('Invalid --clip index')
            validate_plan(p,candidates[args.clip-1]); approved=copy.deepcopy(p); approved['ranges']=candidates[args.clip-1]['ranges']
        write(folder/f'approval-{args.clip or "master"}.json',{'revision':revision(approved),'time':time.time()})
        emit({'approved_revision':revision(approved)}); return
    if args.command == 'transcribe':
        if args.provider == 'scribe' and not args.allow_upload:
            raise ValueError('Scribe uploads audio and costs credits; pass --allow-upload to consent')
        local_transcriber=None
        for key, source in p['sources'].items():
            stat = Path(source['file']).stat()
            fingerprint = [stat.st_size, stat.st_mtime_ns]
            if source.get('fingerprint') == fingerprint and source.get('transcript'):
                print(f'Using cached transcript: {key}',file=sys.stderr,flush=True)
                continue
            print('Transcribing...',file=sys.stderr,flush=True)
            started=time.perf_counter()
            if args.provider == 'local':
                try:
                    from asr import LocalTranscriber
                    if local_transcriber is None: local_transcriber=LocalTranscriber()
                except ImportError:
                    raise ValueError(f'Local transcription dependency missing in {sys.executable}. Run npm run setup:local to install faster-whisper into this exact interpreter, then retry your edit. Details: {sys.exc_info()[1]}')
                source['transcript'] = {'words':normalize_asr_words(local_transcriber.transcribe(source['file']))}
                source['asr_settings']=local_transcriber.settings.copy()
            else:
                sys.path.insert(0,str(ROOT/'video-use/helpers'))
                from transcribe import transcribe_one, load_api_key
                cache = folder/'asr'/key/str(stat.st_mtime_ns)
                import contextlib
                with contextlib.redirect_stdout(sys.stderr):
                    source['transcript'] = read(transcribe_one(Path(source['file']),cache,load_api_key(),verbose=False))
            source['fingerprint'] = fingerprint
            source['transcription_seconds']=round(time.perf_counter()-started,3)
            save(folder,p)
            print('Transcription concluded.',file=sys.stderr,flush=True)
        emit({'revision':revision(p),'transcribed':True}); return
    if args.command == 'repurpose':
        if not 1<=args.count<=100: raise ValueError('--count must be 1..100')
        rules=constraints(p,read(args.constraints) if args.constraints else None)
        candidates=[]
        for i in range(args.count):
            try: plan=local_plan(p,args.target,rules)
            except ValueError:
                if not candidates: raise
                break
            validate_plan(p,plan); candidates.append(plan)
            rules={'include':[], 'exclude':rules.get('exclude',[])+plan['ranges']}
        write(folder/'candidates.json',candidates)
        emit({'file':str(folder/'candidates.json'),'count':len(candidates),'review_required':True}); return
    if args.command == 'history':
        emit({'versions':[x.name for x in sorted((folder/'history').glob('*.json'))]}); return
    if args.command == 'rollback':
        if not args.version or Path(args.version).name != args.version:
            raise ValueError('Supply a history filename')
        restored=read(folder/'history'/args.version); save(folder,restored); emit({'revision':revision(restored)}); return
    if args.command == 'feedback':
        file = folder/'preferences.json'; prefs = read(file) if file.exists() else []
        prefs.append({'time':time.time(), 'profile':p['profile'], 'feedback':args.instructions,'decision':args.decision,'revision':revision(p)})
        write(file,prefs); emit({'recorded':prefs[-1]}); return
    if args.command == 'revise':
        patch = read(args.patch)
        if not isinstance(patch, dict) or set(patch)-set(p):
            raise ValueError('Patch must contain known project fields')
        p=merge(p,patch); save(folder,p); emit({'revision':revision(p)}); return
    if args.command == 'analyze':
        if args.transcript:
            for k,v in read(args.transcript).items():
                p['sources'][k]['transcript'] = v
        save(folder,p); emit(p['sources']); return
    if args.command == 'plan':
        rules=constraints(p,read(args.constraints) if args.constraints else None)
        if not args.semantic:
            plan=local_plan(p,args.target,rules); result=validate_plan(p,plan)
            file=folder/'plans'/f'{time.time_ns()}.json'; write(file,plan)
            emit({'plan_file':str(file),**result}); return
        endpoint = os.environ.get('LLM_URL')
        if not endpoint:
            raise ValueError('Set LLM_URL to a chat-completions endpoint; no fallback upload')
        payload = {'model':os.environ.get('LLM_MODEL','local'), 'temperature':0,
                   'messages':[{'role':'system','content':'Return JSON {"ranges":[{"source":"s0","start":0,"end":1,"reason":"..."}]}. Use only supplied sources and word boundaries. Understand English and Brazilian Portuguese. Preserve complete ideas and context. No commands.'},
                               {'role':'user','content':json.dumps(semantic_context(p,args.instructions,args.target,rules),ensure_ascii=False)}]}
        request = urllib.request.Request(endpoint,json.dumps(payload).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+os.environ.get('LLM_API_KEY','')})
        with urllib.request.urlopen(request,timeout=120) as response:
            result = json.load(response)
        plan=json.loads(result['choices'][0]['message']['content'])
        plan={**plan,'base_revision':revision(p),'constraints':rules,'schema_version':1}
        checked=validate_plan(p,plan); file=folder/'plans'/f'{time.time_ns()}.json'; write(file,plan)
        emit({'plan_file':str(file),**checked}); return
    if args.clip is not None:
        candidates=read(folder/'candidates.json')
        if not 1<=args.clip<=len(candidates): raise ValueError('Invalid --clip index')
        candidate=candidates[args.clip-1]; validate_plan(p,candidate)
        p=copy.deepcopy(p); p['ranges']=candidate['ranges']
    if args.command in ['render','export']:
        approval_file=folder/f'approval-{args.clip or "master"}.json'
        approval=read(approval_file) if approval_file.exists() else {}
        if approval.get('revision') != revision(p): raise ValueError('Approve current edit before final render (preview then approve)')
    results=[]
    for platform in args.platforms.split(','):
        if platform not in p['exports']:
            raise ValueError('Unknown platform '+platform)
        results.append(str(render(folder,p,platform,args.command=='preview')))
    emit({'files':results,'preview':args.command=='preview'})

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr); sys.exit(1)
