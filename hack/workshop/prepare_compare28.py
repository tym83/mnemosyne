"""Install audition candidates in studio-0 with a disk reserve; no /tmp writes."""
from pathlib import Path
from urllib.request import urlopen,Request
import hashlib,json,shutil,subprocess,zipfile,os
ROOT=Path('/work/task28');ROOT.mkdir(exist_ok=True)
TMP=Path('/work/tmp/compare28-downloads');TMP.mkdir(parents=True,exist_ok=True)
os.environ['TMPDIR']='/work/tmp'

def get(url,path):
 path=Path(path)
 if path.exists():return
 if shutil.disk_usage('/work').free<1_000_000_000:raise RuntimeError('1 GB disk reserve reached')
 path.parent.mkdir(parents=True,exist_ok=True)
 with urlopen(Request(url,headers={'User-Agent':'Mnemosyne-audition/28'}),timeout=120) as r,path.with_suffix(path.suffix+'.partial').open('wb') as out:shutil.copyfileobj(r,out)
 path.with_suffix(path.suffix+'.partial').rename(path)

bank=ROOT/'vsco';bank.mkdir(exist_ok=True)
if not (bank/'revision.json').exists():
 tree=json.load(urlopen('https://api.github.com/repos/sgossner/VSCO-2-CE/git/trees/SFZ?recursive=1'))
 (bank/'revision.json').write_text(json.dumps({'revision':tree['sha']}))
subprocess.run(['/work/venv/bin/python',str(ROOT/'complete_vsco28.py')],check=True)
subprocess.run(['/work/venv/bin/python',str(ROOT/'download_salamander28.py')],check=True)
get('https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3',ROOT/'musescore.sf3')
get('https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General_License.md',ROOT/'musescore-license.md')
vpo=ROOT/'vpo';vpo.mkdir(exist_ok=True)
if not (vpo/'installed.json').exists():
 downloads={'waves':'https://drive.usercontent.google.com/download?id=17bY90ybtA5CyNJMnQ4KK9i5YO3tCN7HR&export=download&confirm=t','scripts':'https://virtualplaying.com/go/virtual-playing-orchestra-v3-3-standard-scripts/'}
 hashes={}
 for name,url in downloads.items():
  archive=TMP/(name+'.zip');get(url,archive)
  with zipfile.ZipFile(archive) as z:
   needed=sum(x.file_size for x in z.infolist())
   if shutil.disk_usage('/work').free<needed+1_000_000_000:raise RuntimeError('Insufficient extraction space')
   for entry in z.infolist():
    if not (vpo/entry.filename).resolve().is_relative_to(vpo.resolve()):raise ValueError('Unsafe ZIP path')
   if z.testzip():raise ValueError('Corrupt ZIP')
   z.extractall(vpo)
  hashes[name]=hashlib.sha256(archive.read_bytes()).hexdigest()
  archive.unlink() # Only this run's temporary download, never works or samples.
 (vpo/'installed.json').write_text(json.dumps(hashes,indent=2))
print('Candidates ready; free bytes:',shutil.disk_usage('/work').free,flush=True)
