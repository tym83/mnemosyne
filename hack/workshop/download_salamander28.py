from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from urllib.parse import quote
import json,shutil
root=Path('/work/task28/salamander');root.mkdir(exist_ok=True)
tree=json.load(urlopen('https://api.github.com/repos/sfzinstruments/SalamanderGrandPiano/git/trees/master?recursive=1'))
(root/'revision.json').write_text(json.dumps({'revision':tree['sha']}))
def get(item):
 if item['type']!='blob':return
 p=root/item['path']
 if p.exists():return
 if shutil.disk_usage('/work').free<2_000_000_000:raise RuntimeError('Disk reserve')
 p.parent.mkdir(parents=True,exist_ok=True)
 with urlopen('https://raw.githubusercontent.com/sfzinstruments/SalamanderGrandPiano/'+tree['sha']+'/'+quote(item['path']),timeout=120) as r,p.with_suffix(p.suffix+'.partial').open('wb') as f:shutil.copyfileobj(r,f)
 p.with_suffix(p.suffix+'.partial').rename(p)
with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(get,tree['tree']))
print('complete',sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),flush=True)
