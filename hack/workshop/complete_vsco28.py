"""Fetch definitions for all articulations and samples used by this comparison."""
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import json,shutil,re
root=Path('/work/task28/vsco');rev=json.loads((root/'revision.json').read_text())['revision']
tree=json.load(urlopen(f'https://api.github.com/repos/sgossner/VSCO-2-CE/git/trees/{rev}?recursive=1'))['tree']
def get(rel):
 p=root/rel
 if p.exists():return
 old=Path('/work/samples/vsco-schools')/rel
 p.parent.mkdir(parents=True,exist_ok=True)
 if old.exists():p.symlink_to(old);return
 if shutil.disk_usage('/work').free<2_000_000_000:raise RuntimeError('Disk reserve')
 with urlopen('https://raw.githubusercontent.com/sgossner/VSCO-2-CE/'+rev+'/'+quote(rel),timeout=120) as r,p.with_suffix(p.suffix+'.partial').open('wb') as f:shutil.copyfileobj(r,f)
 p.with_suffix(p.suffix+'.partial').rename(p)
with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(get,[x['path'] for x in tree if x['path'].endswith('.sfz') or x['path']=='LICENSE']))
from compare28 import VSCO
needed=[]
for name in VSCO.values():
 text=(root/(name+'.sfz')).read_text();text=re.sub('//[^\n]*','',text)
 default=re.search(r'default_path=([^\r\n]+)',text)
 default=default[1].strip().replace('\\','/') if default else ''
 for match in re.finditer(r'\bsample\s*=\s*(.*?)(?=\s+\w+\s*=|\r?\n|$)',text):needed.append(default+match[1].strip().replace('\\','/'))
with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(get,sorted(set(needed))))
print('complete',len(set(needed)),flush=True)
