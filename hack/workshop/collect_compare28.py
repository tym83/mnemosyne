"""Collect only audition deliverables, provenance, and small diagnostics."""
from pathlib import Path
import json,shutil,statistics,hashlib,re
ROOT=Path('/work/task28');source=ROOT/'compare';out=ROOT/'public';out.mkdir(exist_ok=True)
summary=[]
for name in ('before','after-b','after-a-b','sso','vsco','vpo','musescore','salamander','spectrogram-diffusion'):
 folder=source/name
 if not folder.exists():continue
 dest=out/name;dest.mkdir(exist_ok=True)
 for p in folder.glob('*'):
  if p.is_file() and p.suffix in ('.json','.mp3','.mid') and p.stat().st_size:shutil.copy2(p,dest/p.name)
 for clip in ('symphony','tintinnabuli'):
  report=folder/f'{clip}.json'
  if not report.exists():continue
  d=json.loads(report.read_text());summary.append({'candidate':name,'excerpt':clip,**{k:d.get(k) for k in ('wall_seconds','seconds_per_audio_minute','peak_rss_kib','children_peak_rss_kib')}})
  if name not in ('after-b','after-a-b'):continue
  files=sorted(folder.glob(f'{clip}-*/*.performance.json'))
  notes=[]
  trace=dest/(clip+'-performance');trace.mkdir(exist_ok=True)
  for p in files:
   shutil.copy2(p,trace/p.name)
   if p.with_suffix('').with_suffix('.mid').exists():pass
   for part in json.loads(p.read_text()):notes.extend(part['notes'])
  if notes:
   metric={'notes':len(notes),'timing_delta_std_ms':statistics.pstdev(x['timing_ms'] for x in notes),'timing_delta_range_ms':[min(x['timing_ms'] for x in notes),max(x['timing_ms'] for x in notes)],'velocity_delta_std':statistics.pstdev(x['played_velocity']-x['score_velocity'] for x in notes),'velocity_delta_range':[min(x['played_velocity']-x['score_velocity'] for x in notes),max(x['played_velocity']-x['score_velocity'] for x in notes)],'breath_breaks':sum(x['breath_breaks'] for x in notes),'measurement_scope':'audio-only schedule before MIDI tick quantization (960 ticks/quarter)'}
   (dest/f'{clip}-performance.json').write_text(json.dumps(metric,indent=2))
(out/'comparison.json').write_text(json.dumps(summary,indent=2))
shutil.copy2(ROOT/'measurements'/'measurements.json',out/'measurements.json')
licenses=out/'licenses';licenses.mkdir(exist_ok=True)
for name,path in {'vsco-LICENSE':ROOT/'vsco/LICENSE','vsco-revision.json':ROOT/'vsco/revision.json','sso-LICENSE':Path('/work/samples/instrumentarium/sso/LICENSE'),'sso-README.md':Path('/work/samples/instrumentarium/sso/README.md'),'salamander-LICENSE':ROOT/'salamander/LICENSE','salamander-README.md':ROOT/'salamander/README.md','salamander-revision.json':ROOT/'salamander/revision.json','musescore-LICENSE.md':ROOT/'musescore-license.md','vpo-archive-sha256.txt':ROOT/'vpo/archive-sha256.txt'}.items():
 if path.exists():shutil.copy2(path,licenses/name)
for p in (ROOT/'vpo/Virtual-Playing-Orchestra3/Documentation').glob('*'):
 if p.is_file() and 'licens' in p.name.lower():shutil.copy2(p,licenses/('vpo-'+p.name))
inventory={}
for name,bank in [('vsco',ROOT/'vsco'),('sso',Path('/work/samples/instrumentarium/sso')),('vpo',ROOT/'vpo/Virtual-Playing-Orchestra3')]:
 files=list(bank.rglob('*.sfz'));matches=[]
 for p in files:
  text=p.read_text(errors='replace')
  if re.search(r'\btrigger\s*=\s*release(?:_key)?\b',text):matches.append(str(p.relative_to(bank)))
 inventory[name]={'sfz_definitions':len(files),'release_definition_files':matches,'scope':'textual inventory; per-render JSON records actually loaded regions'}
(out/'library-inventory.json').write_text(json.dumps(inventory,indent=2))
logs=out/'logs';logs.mkdir(exist_ok=True)
for p in ROOT.glob('*.log'):
 if p.stat().st_size<2_000_000:shutil.copy2(p,logs/p.name)
for p in ROOT.glob('*.exit'):shutil.copy2(p,logs/p.name)
shutil.copy2(ROOT/'neural-requirements.txt',out/'neural-requirements.txt')
manifest={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='sha256.json'}
(out/'sha256.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(summary,indent=2))
