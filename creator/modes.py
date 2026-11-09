"""User-facing modes orchestrate the existing creator project/plan/render engine."""
import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
import cli
from transcript_text import document, semantic_topics
from planning import local_plan, sentences, duplicate, overlaps, validate_plan, revision, constraints


class ProgressLog:
    """Keep JSON stdout clean while showing progress and retaining diagnostics."""
    encoding='utf-8'
    def __init__(self, log, console): self.log,self.console=log,console
    def write(self,text):
        self.log.write(text); self.console.write(text); self.flush(); return len(text)
    def flush(self): self.log.flush(); self.console.flush()
    def isatty(self): return False


def duration_arg(text):
    if re.fullmatch(r'\d+(?:\.\d+)?',text): value=float(text)
    else:
        m=re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?',text)
        if not m or not any(m.groups()): raise argparse.ArgumentTypeError('Use positive seconds or 1m30s')
        value=int(m[1] or 0)*3600+int(m[2] or 0)*60+float(m[3] or 0)
    if value<=0: raise argparse.ArgumentTypeError('Target must be positive')
    return value


def parser():
    p=argparse.ArgumentParser(description='Save edited videos beside footage. --project creates a full YouTube/Shorts/Highlights bundle.')
    p.add_argument('mode',choices=['highlights','youtube','shorts','project','transcribe'])
    p.add_argument('sources',nargs='+',help='Local video paths (quote spaces); download URLs with npm run download first')
    p.add_argument('--profile',choices=list(cli.PROFILES),default='build-in-public')
    p.add_argument('--target',type=duration_arg,help='Approximate target seconds or 1m30s; complete ideas take priority')
    p.add_argument('--count',type=int,default=3,help='Maximum Shorts count (1..100)')
    p.add_argument('--ai',action='store_true',help='Opt into configured LLM for editorial selection')
    p.add_argument('--output',help='Output directory; default source directory (or named project folder with --project)')
    p.add_argument('--project',action='store_true',help='Create a full project containing all three editing modes')
    p.add_argument('--cache-dir',help='Override internal cache/workspace directory for single-mode edits')
    p.add_argument('--preview',action='store_true',help='Render a lower-resolution preview instead of the default final video')
    p.add_argument('--approve',action='store_true',help='Explicitly approve the already-previewed mode plan and export final')
    p.add_argument('--instructions',default='',help='Creative brief for optional AI or agent; local planner records but does not interpret prose')
    p.add_argument('--platforms',help='Comma-separated export profile names; default youtube or shorts by mode')
    p.add_argument('--transcript',help='Import source-keyed word JSON; avoid ASR for corrected/cached transcripts')
    p.add_argument('--provider',choices=['local','scribe'],default='local')
    p.add_argument('--allow-upload',action='store_true',help='Consent to Scribe audio upload')
    p.add_argument('--captions',action='store_true',help='Burn captions; default on for Shorts')
    p.add_argument('--separate',action='store_true',help='Highlights: export each selected idea as its own clip')
    p.add_argument('--constraints',help='JSON include/exclude source timestamp ranges')
    p.add_argument('--json',action='store_true',help='Machine-readable result; default is a readable completion message')
    p.add_argument('--section-gap',type=duration_arg,help='Deprecated: ignored; pauses no longer force topic sections')
    p.add_argument('--section-length',type=duration_arg,help='Deprecated: ignored; duration no longer forces topic sections')
    return p


def completion_message(result, argv):
    """Give humans a playable file and an exact next step; JSON remains opt-in."""
    if result['mode']=='transcribe':
        return '\n'.join(['Transcript ready.']+[f'Text: {file}' for file in result['transcript_files']]+[f'Processing state and log: {result["log"]}'])
    label='Preview' if result['preview'] else 'Final video'
    lines=[f'{label} ready ({result["mode"]}).']
    filename='preview.mp4' if result['preview'] else 'final.mp4'
    for index,folder in enumerate(result['outputs']):
        file=Path(result['video_files'][index]) if result.get('video_files') else Path(folder)/filename
        lines.append(f'Video: {file}')
        report=Path(folder)/'qa.json'
        if report.exists():
            qa=cli.read(report)
            seconds=round(float(qa['metadata']['format']['duration']))
            lines.append(f'Length: {seconds//60}m {seconds%60:02d}s | Technical QA errors: {len(qa["errors"])}')
    lines.append(f'Processing state and reports: {result["project"]}')
    if result['preview']:
        tokens=[token for token in argv if token not in ['--preview','--approve','--json']]
        # PowerShell single-quoted literals preserve spaces, apostrophes and $.
        quote=lambda value: "'"+value.replace("'","''")+"'"
        command='npm run edit -- '+' '.join(quote(t) for t in tokens+['--approve'])
        lines.extend(['Open the video file above to review your edit.',
                      'To render the full-resolution final video after reviewing:',command])
    lines.append(f'Log: {result["log"]}')
    return '\n'.join(lines)


def cache_home():
    if os.name=='nt': return Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'VideoEditor'/'Cache'
    return Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'video-editor'


def workspace(args,sources):
    identity=hashlib.sha256(json.dumps(sources).encode()).hexdigest()[:10]
    if getattr(args,'_bundle_root',None): return Path(args._bundle_root)
    if args.project or args.mode=='project':
        return Path(args.output).resolve() if args.output else Path(sources[0]).parent/(Path(sources[0]).stem+'-edited-project')
    return (Path(args.cache_dir).resolve() if args.cache_dir else cache_home())/(Path(sources[0]).stem+'-'+identity)


def publish_file(source,directory,stem):
    """Exclusive creation protects source footage and all earlier edits."""
    directory.mkdir(parents=True,exist_ok=True)
    index=0
    while True:
        target=directory/(stem+(f'-{index}' if index else '')+'.mp4')
        try:
            with target.open('xb') as out, Path(source).open('rb') as src: shutil.copyfileobj(src,out)
            return target
        except FileExistsError: index+=1


def execute(args):
    if args.mode=='transcribe' and (args.project or args.preview or args.approve or args.platforms or args.captions or args.separate or args.target or args.constraints):
        raise ValueError('Transcribe exports full text only. Omit video-editing/project flags; use --output, --provider or --ai for topic sectioning.')
    if not (args.project or args.mode=='project'): return execute_mode(args)
    if args.separate: raise ValueError('--separate is single-mode Highlights only; project bundles already contain all modes')
    root=workspace(args,[str(Path(f).resolve()) for f in args.sources])
    results=[]
    for mode in ['youtube','highlights','shorts']:
        child=copy.copy(args); child.mode=mode; child._bundle_root=str(root)
        results.append(execute_mode(child))
    return {'mode':'project','project':str(root),'outputs':[p for r in results for p in r['outputs']],
            'video_files':[p for r in results for p in r['video_files']],
            'mode_projects':[p for r in results for p in r['mode_projects']],
            'preview':args.preview,'log':results[-1]['log']}


def strategy(p,mode,target,rules):
    if mode=='highlights':
        # Pareto is a selection heuristic. A practical default budget, never a quota.
        budget=target or max(15,min(600,sum(cli.duration(v['metadata']) for v in p['sources'].values())*.2))
        return local_plan(p,budget,rules)
    if p['profile']=='music' and mode=='youtube':
        if rules.get('include') or rules.get('exclude'): raise ValueError('Music preservation requires manual ranges for timestamp constraints')
        return None
    pool=[r for r in sentences(p) if not any(overlaps(r,x) for x in rules.get('exclude',[]))]
    selected=[]
    for r in pool:
        required=any(overlaps(r,x) for x in rules.get('include',[]))
        if required or not any(duplicate(r['text'],x['text']) for x in selected): selected.append(r)
    if not selected: raise ValueError('No complete sentences. Import/correct a transcript or use manual creator ranges.')
    if target:
        return local_plan(p,target,rules)
    plan={'schema_version':1,'base_revision':revision(p),'constraints':rules,
          'ranges':[{**r,'reason':'YouTube: chronological complete idea, repeated explanation removed, inter-sentence gap trimmed'} for r in selected]}
    validate_plan(p,plan)
    return plan


def highlights_defaults(edit, args):
    """Highlights changes the timeline, not the sound or visual treatment."""
    edit['settings']['lufs']=None
    edit['settings']['preserve_audio']=True
    edit['settings']['preserve_source']=not bool(args.platforms)
    edit['audio']=[]
    edit['settings']['captions']=bool(args.captions)
    return edit


def shorts_plans(p,target,count,rules):
    # Adjacent sentences preserve local context rather than compiling unrelated moments.
    pool=sentences(p); plans=[]; used=[]
    for i,r in enumerate(pool):
        if len(plans)>=count: break
        if any(overlaps(r,x) for x in used) or any(overlaps(r,x) for x in rules.get('exclude',[])): continue
        group=[r]
        for nxt in pool[i+1:]:
            if nxt['source']!=r['source'] or nxt['start']-group[-1]['end']>3 or nxt['end']-r['start']>target: break
            if any(overlaps(nxt,x) for x in rules.get('exclude',[])) or any(overlaps(nxt,x) for x in used): break
            group.append(nxt)
        clip={'source':r['source'],'start':r['start'],'end':group[-1]['end'],
              'text':' '.join(x['text'] for x in group),'reason':'Shorts: adjacent complete ideas retain context; hook/payoff need creative review'}
        if any(duplicate(clip['text'],x['ranges'][0]['text']) for x in plans): continue
        # Include constraints apply across the collection, not to every short.
        plan={'schema_version':1,'base_revision':revision(p),'constraints':{'exclude':rules.get('exclude',[])},'ranges':[clip]}
        validate_plan(p,plan); plans.append(plan); used.append(clip)
    for required in rules.get('include',[]):
        if not any(x['source']==required['source'] and x['start']<=required['start'] and x['end']>=required['end'] for x in used):
            raise ValueError('Shorts count/target cannot satisfy includes; increase budget or choose a manual plan')
    if not plans: raise ValueError('No Shorts candidates available')
    return plans


def invoke(command,folder,*args):
    original=sys.argv
    try:
        sys.argv=['creator',command,'--project',str(folder),*args]
        with contextlib.redirect_stdout(io.StringIO()) as output: cli.main()
        return json.loads(output.getvalue() or '{}')
    finally: sys.argv=original


def execute_mode(args):
    sources=[str(Path(f).resolve()) for f in args.sources]
    if not 1<=args.count<=100: raise ValueError('--count must be 1..100')
    if args.preview and args.approve: raise ValueError('Choose --preview or --approve')
    if args.separate and args.mode!='highlights': raise ValueError('--separate is for highlights; Shorts already creates separate clips')
    if args.ai and args.mode=='shorts' and args.count!=1: raise ValueError('AI Shorts currently supports --count 1; use local multiple candidates or agent plans')
    for f in sources:
        if not Path(f).is_file(): raise ValueError(f'Source missing: {f}. For URLs use npm run download first.')
    root=workspace(args,sources)
    # Reuse existing source transcripts when upgrading output defaults. Originals
    # are retained; migration never deletes previous delivered edits.
    identity=hashlib.sha256(json.dumps(sources).encode()).hexdigest()[:10]
    old=cli.ROOT/'output'/'projects'/(Path(sources[0]).stem+'-'+identity)/'data'
    if not (root/'data').exists() and old.is_dir():
        shutil.copytree(old,root/'data')
    flat=not (args.project or getattr(args,'_bundle_root',None))
    requires_approval=args.approve
    final=not args.preview
    for name in ['data','highlights','youtube','shorts','assets','temporary','reports']: (root/name).mkdir(parents=True,exist_ok=True)
    log=root/'reports'/f'run-{time.time_ns()}.log'
    cli.RUN_LOG=log
    try:
        with log.open('a',encoding='utf-8') as diagnostics, contextlib.redirect_stderr(ProgressLog(diagnostics,sys.stderr)):
            diagnostics.write(f'mode={args.mode}; sources={sources}\n'); diagnostics.flush()
            folder=root/'data'
            if not (folder/'project.json').exists(): invoke('init',folder,'--sources',*sources,'--profile',args.profile)
            p=cli.read(folder/'project.json')
            if [v['file'] for v in p['sources'].values()]!=sources: raise ValueError('Output belongs to different sources; choose another --output')
            if p['profile']!=args.profile: raise ValueError('Existing output has a different profile; use that --profile or a new --output')
            if args.transcript:
                invoke('analyze',folder,'--transcript',args.transcript)
                imported=cli.read(folder/'project.json')
                for source in imported['sources'].values():
                    if source.get('transcript'):
                        stat=Path(source['file']).stat(); source['fingerprint']=[stat.st_size,stat.st_mtime_ns]
                cli.save(folder,imported)
            p=cli.read(folder/'project.json')
            if args.profile!='music' or args.mode!='youtube':
                invoke('transcribe',folder,'--provider',args.provider,*(['--allow-upload'] if args.allow_upload else []))
                p=cli.read(folder/'project.json')
            if args.mode=='transcribe':
                if args.section_gap or args.section_length:
                    print('Section gap/length options are deprecated and ignored; only topic transitions create sections.',file=sys.stderr)
                files=[]; sections=[]
                for source in p['sources'].values():
                    topics=semantic_topics(source) if args.ai else None
                    text,count=document(source,topics=topics)
                    original=Path(source['file'])
                    directory=Path(args.output).resolve() if args.output else original.parent
                    directory.mkdir(parents=True,exist_ok=True)
                    index=0
                    while True:
                        file=directory/(original.stem+'-transcript'+(f'-{index}' if index else '')+'.txt')
                        try:
                            with file.open('x',encoding='utf-8') as out: out.write(text)
                            break
                        except FileExistsError: index+=1
                    files.append(str(file)); sections.append(count)
                result={'mode':'transcribe','project':str(root),'transcript_files':files,'section_counts':sections,
                        'section_method':'semantic-model' if args.ai else 'conservative-explicit-transitions','log':str(log)}
                cli.write(root/'reports'/f'transcript-{time.time_ns()}.json',result)
                return result
            rules=constraints(p,cli.read(args.constraints) if args.constraints else None)
            # Mode settings are applied to a copy so workflows share cached sources but not timelines.
            working=copy.deepcopy(p)
            working['settings']['captions']=args.captions or args.mode=='shorts'
            request_key=hashlib.sha256(json.dumps({'base':revision(p),'mode':args.mode,'profile':args.profile,'target':args.target,'count':args.count,
                'ai':args.ai,'instructions':args.instructions,'constraints':rules,'captions':working['settings']['captions'],'separate':args.separate},sort_keys=True).encode()).hexdigest()[:20]
            cache=root/'data'/'mode-cache'/f'{request_key}.json'
            if cache.exists(): plans=cli.read(cache)
            elif args.ai:
                brief=f'Mode: {args.mode}. '+args.instructions
                result=invoke('plan',folder,'--semantic','--target',str(args.target or 60),'--instructions',brief,*(['--constraints',args.constraints] if args.constraints else []))
                plans=[cli.read(result['plan_file'])]
            elif args.mode=='shorts': plans=shorts_plans(p,args.target or 60,args.count,rules)
            else:
                planned=strategy(p,args.mode,args.target,rules)
                plans=[planned] if planned else [None]
            if args.separate and not cache.exists():
                plans=[{**plans[0],'ranges':[r],'constraints':{'exclude':rules.get('exclude',[])}} for r in plans[0]['ranges']]
            if not cache.exists(): cli.write(cache,plans)
            platforms=(args.platforms or ('shorts' if args.mode=='shorts' else 'youtube')).split(',')
            for platform in platforms:
                if platform not in p['exports']: raise ValueError('Unknown platform: '+platform)
            outputs=[]; video_files=[]; mode_projects=[]
            for i,plan in enumerate(plans,1):
                if plan: validate_plan(p,plan)
                edit=copy.deepcopy(working)
                if plan: edit['ranges']=plan['ranges']
                mode_project=root/'data'/'edits'/f'{args.mode}-{request_key}-{i}'
                if (mode_project/'project.json').exists(): edit=cli.read(mode_project/'project.json')
                else: cli.save(mode_project,edit)
                if args.mode=='highlights':
                    original=copy.deepcopy(edit)
                    highlights_defaults(edit,args)
                    if edit!=original: cli.save(mode_project,edit)
                cli.validate(edit)
                mode_projects.append(str(mode_project))
                key=hashlib.sha256((args.mode+str(i)+revision(edit)+json.dumps(platforms)).encode()).hexdigest()
                preview_record=root/'reports'/f'preview-{key}.json'
                if requires_approval and not preview_record.exists(): raise ValueError('No matching preview. Run the same command with --preview first; keep options identical.')
                saved_plan={'mode':args.mode,'instructions':args.instructions,'plan':plan,'project':edit}
                cli.write(root/'data'/'mode-plans'/f'{args.mode}-{i}-{time.time_ns()}.json',saved_plan)
                for platform in platforms:
                    # Renderer, QA, and manifest are shared with creator commands.
                    temporary=root/'temporary'/f'{args.mode}-{i}'
                    print(f'Rendering {args.mode} {"final video" if final else "preview"} ({i}/{len(plans)}, {platform})...',file=sys.stderr,flush=True)
                    out=cli.render(temporary,edit,platform,preview=not final)
                    job=out.parent
                    dest=root/args.mode/f'{i}-{platform}-{time.time_ns()}'
                    dest.mkdir()
                    if not flat: shutil.copy2(out,dest/('final.mp4' if final else 'preview.mp4'))
                    shutil.copy2(job/'captions.srt',dest/'captions.srt')
                    shutil.copy2(job/'qa.json',dest/'qa.json')
                    manifest=cli.read(job/'manifest.json'); manifest['temporary_file']=manifest['file']
                    if manifest['qa']['errors']: raise ValueError('Export QA failed: '+str(manifest['qa']['errors']))
                    if flat:
                        directory=Path(args.output).resolve() if args.output else Path(sources[0]).parent
                        stem=Path(sources[0]).stem+'-'+args.mode
                        if len(plans)>1: stem+=f'-{i:02}'
                        if len(platforms)>1 or args.platforms: stem+='-'+platform
                        if not final: stem+='-preview'
                        delivered=publish_file(out,directory,stem)
                    else: delivered=dest/('final.mp4' if final else 'preview.mp4')
                    manifest['file']=str(delivered)
                    manifest['mode']=args.mode; cli.write(dest/'manifest.json',manifest)
                    video_files.append(str(delivered)); outputs.append(str(dest))
                if not final: cli.write(preview_record,{'revision':revision(edit),'outputs':outputs})
            result={'mode':args.mode,'project':str(root),'mode_projects':mode_projects,'outputs':outputs,
                    'video_files':video_files,
                    'preview':not final,'log':str(log),
                    'review_required':'Mechanical sentence selection is not verified narrative/creative quality.'}
            cli.write(root/'reports'/f'result-{time.time_ns()}.json',result)
            return result
    except BaseException as error:
        with log.open('a',encoding='utf-8') as diagnostics: diagnostics.write(f'FAILED: {type(error).__name__}: {error}\n')
        raise ValueError(f'{error}\nProject state and diagnostics retained at {root}. Retry the same command after fixing the issue. Log: {log}') from error
    finally:
        cli.RUN_LOG=None


if __name__=='__main__':
    try:
        args=parser().parse_args()
        result=execute(args)
        print(json.dumps(result,ensure_ascii=False,indent=2) if args.json else completion_message(result,sys.argv[1:]))
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr); sys.exit(1)
