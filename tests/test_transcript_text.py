from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import cli
import modes
from transcript_text import document, section_words, validate_topics, topic_sections, semantic_topics
import io
import json

def source():
    return {'file':'video.mp4','transcript':{'words':[
        {'start':0,'end':1,'text':'Olá.'}, {'start':1.2,'end':2,'text':'First idea.'},
        {'start':8,'end':9,'text':'Second idea.'}, {'start':9,'end':10,'text':'Unfinished ending'}]}}

class TranscriptTests(unittest.TestCase):
    def long_words(self):
        return [{'start':i,'end':i+.8,'text':'continuing.'} for i in range(300)]
    def test_long_single_topic_with_pauses_does_not_fragment(self):
        items=[{'start':i*44,'end':i*44+4,'text':f'Continuing explanation {i}.'} for i in range(62)]
        groups=section_words(items)
        self.assertEqual(len(groups),1)
        text,count=document({'file':'44min.mp4','transcript':{'words':items}})
        self.assertEqual(count,1); self.assertNotIn('Section 1',text)
        self.assertIn('Continuing explanation 61.',text)
    def test_explicit_topic_marker_and_subject_title(self):
        items=self.long_words(); items[150]['text']='Next topic is gardening.'
        topics=topic_sections(items)
        self.assertEqual(len(topics),2)
        self.assertEqual(topics[1]['title'],'Gardening')
        groups=section_words(items)
        self.assertEqual([w for g in groups for w in g],items)
    def test_short_topic_fragment_is_merged(self):
        items=self.long_words()
        self.assertEqual(validate_topics(items,[{'word_index':0,'title':'Main topic'},{'word_index':298,'title':'Tiny aside'}]),[])
    def test_mid_sentence_or_out_of_bounds_topics_rejected(self):
        items=self.long_words(); items[149]['text']='not finished'
        for index in [150,500]:
            with self.assertRaises(ValueError): validate_topics(items,[{'word_index':0,'title':'Main'},{'word_index':index,'title':'Second'}])
    def test_semantic_titles_are_validated_and_text_stays_local(self):
        items=self.long_words()
        data={'sections':[{'word_index':0,'title':'Programming','reason':'...'}, {'word_index':150,'title':'Gardening','reason':'Clear change'}]}
        response={'choices':[{'message':{'content':json.dumps(data)}}]}
        with patch.dict('os.environ',{'LLM_URL':'http://localhost/v1/chat/completions'}), patch('transcript_text.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result=semantic_topics({'file':'private-source.mp4','transcript':{'words':items}})
        self.assertEqual(result[1]['title'],'Gardening')
        self.assertNotIn('private-source.mp4',request.call_args.args[0].data.decode())
        text,count=document({'file':'video','transcript':{'words':items}},topics=result)
        self.assertIn('Programming [',text); self.assertIn('Gardening [',text)
        self.assertEqual(count,2)
    def test_pause_sections_keep_every_word_and_unfinished_ending(self):
        src=source(); groups=section_words(src['transcript']['words'])
        self.assertEqual(len(groups),1)
        self.assertEqual([w for group in groups for w in group],src['transcript']['words'])
        text,count=document(src)
        self.assertEqual(count,1); self.assertIn('Olá.',text)
        self.assertIn('Unfinished ending',text); self.assertIn('00:00:08',text)
    def test_soft_length_breaks_after_sentence(self):
        src=source(); groups=section_words(src['transcript']['words'],gap=100,length=1)
        self.assertEqual(len(groups),1)
    def test_no_invented_sections_for_short_continuous_speech(self):
        text,count=document(source(),gap=100,length=100)
        self.assertEqual(count,1)
    def test_empty_speech_has_clear_error(self):
        with self.assertRaisesRegex(ValueError,'No timed speech'): document({'file':'video','transcript':{'words':[]}})
    def test_transcribe_only_exports_text_and_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); video=root/'video with spaces.mp4'; video.touch()
            args=modes.parser().parse_args(['transcribe',str(video),'--cache-dir',str(root/'cache')])
            folder=modes.workspace(args,[str(video)])/'data'
            src=source(); src.update(file=str(video),metadata={'format':{'duration':'12'}})
            p={'sources':{'s0':src},'profile':'build-in-public','settings':{'layout':'fit','caption':'tech'},'audio':[],
               'ranges':[{'source':'s0','start':0,'end':12}]}
            cli.save(folder,p)
            with patch.object(modes,'invoke',return_value={}), patch.object(cli,'render') as render:
                result=modes.execute(args); again=modes.execute(args)
            render.assert_not_called()
            file=Path(result['transcript_files'][0]); self.assertEqual(file.parent,video.parent)
            self.assertNotEqual(result['transcript_files'],again['transcript_files'])
            self.assertIn('Transcript ready.',modes.completion_message(result,[]))
            self.assertIn('Unfinished ending',file.read_text(encoding='utf-8'))
    def test_editing_options_rejected(self):
        args=modes.parser().parse_args(['transcribe','file.mp4','--project'])
        with self.assertRaisesRegex(ValueError,'full text only'): modes.execute(args)

if __name__=='__main__': unittest.main()
