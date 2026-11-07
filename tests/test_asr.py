import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'creator'))
import asr
import cli

class ASRTests(unittest.TestCase):
    def test_fast_defaults_and_accurate_override(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(asr.options()['beam_size'],1)
            self.assertTrue(asr.options()['vad'])
        with patch.dict(os.environ,{'WHISPER_PRESET':'accurate','WHISPER_VAD':'0'}):
            self.assertEqual(asr.options()['beam_size'],5)
            self.assertFalse(asr.options()['vad'])
    def test_invalid_settings(self):
        for setting,value in [('WHISPER_PRESET','bad'),('WHISPER_THREADS','0'),('WHISPER_DEVICE','intel'),('WHISPER_VAD','maybe')]:
            with patch.dict(os.environ,{setting:value}):
                with self.assertRaises(ValueError): asr.options()
    def test_reuses_model_and_simple_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); file=folder/'source.mp4'; file.touch()
            source={'file':str(file),'metadata':{'format':{'duration':'3'}}}
            p={'sources':{'s0':source.copy(),'s1':source.copy()},'ranges':[{'source':'s0','start':0,'end':3}], 'settings':{'caption':'tech','layout':'fit'},'audio':[]}
            cli.save(folder,p)
            runtime=MagicMock(); runtime.settings={'preset':'fast'}
            runtime.transcribe.return_value=[{'start':0,'end':1,'text':'Hello.'}]
            with patch.object(asr,'LocalTranscriber',return_value=runtime) as factory, patch.object(sys,'argv',['cli','transcribe','--project',directory]), contextlib.redirect_stderr(io.StringIO()) as log, contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            factory.assert_called_once(); self.assertEqual(runtime.transcribe.call_count,2)
            self.assertEqual(log.getvalue().splitlines(),['Transcribing...','Transcription concluded.']*2)
    def test_vad_keeps_original_timestamps(self):
        model=MagicMock()
        word=types.SimpleNamespace(start=12.5,end=13.5,word='Hello')
        model.transcribe.return_value=([types.SimpleNamespace(words=[word])],None)
        instance=object.__new__(asr.LocalTranscriber); instance.model=model; instance.settings={'beam_size':1,'vad':True}
        self.assertEqual(instance.transcribe('file')[0]['start'],12.5)
        model.transcribe.assert_called_once_with('file',word_timestamps=True,beam_size=1,vad_filter=True)
