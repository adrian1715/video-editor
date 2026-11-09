"""Readable, chronological transcript export; never summarizes or omits speech."""
import re
import json
import os
import urllib.request
from planning import words

MIN_WORDS=80
MIN_SECONDS=60


def substantial(items):
    return len(items)>=MIN_WORDS and items[-1]['end']-items[0]['start']>=MIN_SECONDS


def topic_sections(items):
    """Conservative offline boundaries: explicit topic transitions, not silence."""
    starts=[0]; titles={}
    pattern=re.compile(r'(?:moving on to|next topic is|turning to|mudando de assunto para|o próximo assunto é|agora vamos falar sobre)\s+(.+)',re.I)
    for i in range(len(items)):
        if i and not re.search(r'[.!?]["\u201d]*$',items[i-1]['text'].strip()): continue
        phrase=[]
        for w in items[i:i+24]:
            phrase.append(w['text'].strip())
            if re.search(r'[.!?]$',w['text'].strip()): break
        match=pattern.match(' '.join(phrase))
        if not match or not substantial(items[starts[-1]:i]) or not substantial(items[i:]): continue
        title=match[1].strip().rstrip('.!?')
        if not title or len(title)>100: continue
        starts.append(i); titles[i]=title[0].upper()+title[1:]
    return [{'word_index':i,'title':titles.get(i)} for i in starts] if len(starts)>1 else []


def validate_topics(items, topics):
    if not isinstance(topics,list): raise ValueError('Topic sections must be an array')
    if not topics: return []
    last=-1
    for section in topics:
        if not isinstance(section,dict) or set(section)-{'word_index','title','reason'}: raise ValueError('Invalid topic section fields')
        index=section.get('word_index')
        if type(index)!=int or not last<index<len(items): raise ValueError('Topic word indices must be ordered and in bounds')
        if section.get('title') is not None and (not isinstance(section['title'],str) or not section['title'].strip() or len(section['title'])>100 or '\n' in section['title']): raise ValueError('Invalid topic title')
        if index and not re.search(r'[.!?]["\u201d]*$',items[index-1]['text'].strip()): raise ValueError('Topic boundary must follow a complete sentence')
        last=index
    if topics[0]['word_index']!=0: raise ValueError('First topic must start at word index 0')
    # Drop fragmentation rather than inventing extra topics. No transcript text changes.
    retained=[topics[0]]
    for section in topics[1:]:
        index=section['word_index']
        if substantial(items[retained[-1]['word_index']:index]) and substantial(items[index:]): retained.append(section)
    return retained if len(retained)>1 else []


def semantic_topics(source):
    items=words(source)
    endpoint=os.environ.get('LLM_URL')
    if not endpoint: raise ValueError('Topic AI needs LLM_URL and LLM_MODEL. Omit --ai for conservative local sectioning.')
    prompt=('Return JSON {"sections":[{"word_index":0,"title":"Main topic","reason":"topic evidence"}]}. '
            'Read the whole English or Brazilian Portuguese transcript. Divide ONLY at clear sustained changes of main topic. '
            'Do not split pauses, examples, tangents, speaker changes, or a continuing discussion. No section count/duration quota. '
            'Return sections:[] when no meaningful topic distinction exists. Prefer a few broad sections, never short fragments. '
            'Titles must concisely name the main topic in the transcript language, not quote its first words. '
            'Use only supplied word indices at sentence starts; never rewrite, summarize or return transcript text.')
    # Index-addressed words only; source paths and project metadata stay local.
    payload={'model':os.environ.get('LLM_MODEL','local'),'temperature':0,'messages':[
        {'role':'system','content':prompt},
        {'role':'user','content':json.dumps([{'word_index':i,'text':w['text']} for i,w in enumerate(items)],ensure_ascii=False)}]}
    request=urllib.request.Request(endpoint,json.dumps(payload).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+os.environ.get('LLM_API_KEY','')})
    with urllib.request.urlopen(request,timeout=180) as response: result=json.load(response)
    data=json.loads(result['choices'][0]['message']['content'])
    if not isinstance(data,dict) or set(data)!={'sections'}: raise ValueError('Topic AI must return only a sections array')
    return validate_topics(items,data['sections'])


def timestamp(seconds):
    value=int(seconds)
    return f'{value//3600:02}:{value//60%60:02}:{value%60:02}'


def section_words(items, gap=None, length=None, topics=None):
    markers=validate_topics(items,topic_sections(items) if topics is None else topics)
    starts=[s['word_index'] for s in markers] or [0]
    return [items[a:b] for a,b in zip(starts,starts[1:]+[len(items)])] if items else []


def document(source, gap=None, length=None, topics=None):
    items=words(source)
    if not items: raise ValueError('No timed speech words available to export')
    markers=validate_topics(items,topic_sections(items) if topics is None else topics)
    sections=section_words(items,topics=markers)
    lines=['Transcript',f'Source: {source["file"]}',
           'Full transcript. Topic headings appear only where distinct sustained topics are identified.','']
    for index,section in enumerate(sections,1):
        if len(sections)>1:
            title=markers[index-1].get('title') or 'Opening discussion'
            lines += [f'{title} [{timestamp(section[0]["start"])} - {timestamp(section[-1]["end"])}]','']
        paragraph=[]; start=None; previous=None
        for word in section:
            if paragraph and (word['start']-previous['end']>=1.0 or (len(paragraph)>=45 and re.search(r'[.!?]$',previous['text'].strip()))):
                lines += [f'[{timestamp(start)}] '+clean(paragraph),'']; paragraph=[]; start=None
            if start is None: start=word['start']
            paragraph.append(word['text'].strip()); previous=word
        if paragraph: lines += [f'[{timestamp(start)}] '+clean(paragraph),'']
    return '\n'.join(lines),len(sections)


def clean(tokens):
    return re.sub(r'\s+([,.;:!?])',r'\1',' '.join(tokens))
