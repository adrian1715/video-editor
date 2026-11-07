"""Local speech runtime configuration and model reuse. Imports AI libraries lazily."""
import os


def options():
    preset=os.environ.get('WHISPER_PRESET','fast')
    device=os.environ.get('WHISPER_DEVICE','auto')
    vad=os.environ.get('WHISPER_VAD','1')
    if preset not in ['fast','accurate']: raise ValueError('WHISPER_PRESET must be fast or accurate')
    if device not in ['auto','cpu','cuda']: raise ValueError('WHISPER_DEVICE must be auto, cpu or cuda')
    if vad not in ['0','1']: raise ValueError('WHISPER_VAD must be 0 or 1')
    try: threads=int(os.environ.get('WHISPER_THREADS',str(min(8,os.cpu_count() or 4))))
    except ValueError: raise ValueError('WHISPER_THREADS must be an integer')
    if not 1<=threads<=128: raise ValueError('WHISPER_THREADS must be 1..128')
    return {'model':os.environ.get('WHISPER_MODEL','small'),'device':device,
            'threads':threads,'beam_size':1 if preset=='fast' else 5,'vad':vad=='1','preset':preset}


class LocalTranscriber:
    def __init__(self):
        from faster_whisper import WhisperModel
        import ctranslate2
        self.settings=options()
        device=self.settings['device']
        if device=='auto': device='cuda' if ctranslate2.get_cuda_device_count()>0 else 'cpu'
        self.settings['resolved_device']=device
        self.model=WhisperModel(self.settings['model'],device=device,
            compute_type='float16' if device=='cuda' else 'int8',cpu_threads=self.settings['threads'])

    def transcribe(self,file):
        segments,_=self.model.transcribe(file,word_timestamps=True,
            beam_size=self.settings['beam_size'],vad_filter=self.settings['vad'])
        # Original source times are restored by faster-whisper after VAD.
        return [{'start':float(w.start),'end':float(w.end),'text':w.word,'type':'word'}
                for segment in segments for w in (segment.words or [])]
