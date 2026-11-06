"""Pinned Spectrogram Diffusion CPU audition, isolated dependencies/model cache."""
import os
os.environ.update(HF_HOME='/work/models/hf',TMPDIR='/work/tmp',TRANSFORMERS_CACHE='/work/models/hf/transformers')
from pathlib import Path
import json,time,resource
import torch
import numpy as np
import soundfile as sf
from diffusers import SpectrogramDiffusionPipeline, MidiProcessor
import diffusers.pipelines
from diffusers.pipelines.deprecated import spectrogram_diffusion
# Upstream checkpoint predates the pipeline's move to deprecated/.
diffusers.pipelines.spectrogram_diffusion = spectrogram_diffusion
from compare28 import sources,stem_score,write_midi,ROOT,OUT,run
from music21 import stream

torch.set_num_threads(2)
folder=OUT/'spectrogram-diffusion';folder.mkdir(parents=True,exist_ok=True)
start=time.monotonic()
from huggingface_hub import hf_hub_download
from diffusers import OnnxRuntimeModel
melgan_path=hf_hub_download('google/music-spectrogram-diffusion','melgan/model.onnx',cache_dir='/work/models/hf')
melgan=OnnxRuntimeModel.from_pretrained(str(Path(melgan_path).parent),provider='CPUExecutionProvider')
pipeline=SpectrogramDiffusionPipeline.from_pretrained('google/music-spectrogram-diffusion',cache_dir='/work/models/hf',torch_dtype=torch.float32,melgan=melgan)
pipeline.to('cpu');processor=MidiProcessor()
print('loaded',time.monotonic()-start,flush=True)
for name,source,plan,players in sources():
 score=stream.Score()
 for player in players:
  events=[]
  for e in player['events']:
   if e['at']*60/plan['tempo']>=40:continue
   e=dict(e);e['duration']=min(e['duration'],40*plan['tempo']/60-e['at']);events.append(e)
  if events:score.insert(0,stem_score(events,player['instrument'],40*plan['tempo']/60).parts[0])
 mid=folder/f'{name}.mid';write_midi(score,mid,plan['tempo'])
 inputs=processor(str(mid));start=time.monotonic()
 with torch.no_grad():output=pipeline(input_tokens=inputs,num_inference_steps=100,generator=torch.Generator().manual_seed(28)).audios
 elapsed=time.monotonic()-start
 wav=folder/f'{name}.wav';sf.write(wav,np.asarray(output).squeeze(),16000)
 run(['ffmpeg','-v','error','-i',wav,'-t','40','-af','loudnorm=I=-20:TP=-1.5:LRA=50','-codec:a','libmp3lame','-q:a','2',folder/f'{name}.mp3'],folder/'render.log')
 (folder/f'{name}.json').write_text(json.dumps(dict(wall_seconds=elapsed,seconds_per_audio_minute=elapsed*1.5,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,steps=100,seed=28,device='cpu',sample_rate=16000),indent=2))
 print(name,elapsed,flush=True)
