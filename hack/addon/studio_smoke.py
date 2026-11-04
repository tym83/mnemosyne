"""Run only in studio/CI: real school composition, weave, decode and export."""
import argparse
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.operator.worker import run
from mnemosyne.cli import export_local
from mnemosyne.restore import recover_works
from mnemosyne.state.collect import archive

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--render',action='store_true')
a=p.parse_args()
plan=json.loads((Path(__import__('mnemosyne').__file__).parent/'music/schools/plans/tempo_canon.json').read_text())
request={'mode':'chamber','render':a.render,'atelier':'technical-smoke','commissions':[
    {'idea':'Existing method study for technical verification', 'method':'tempo_canon repository study','plan':{**plan, 'seed':plan['seed']+i}} for i in range(3)]}
objects=json.loads(a.snapshot.read_text())
key=X25519PrivateKey.generate()
records,report=run(request,a.output/'night',key,objects)
if not report.get('archive_recovered'): raise RuntimeError(report)
export_local(a.output/'night/woven',a.output/'export')
recovered,restored,_=recover_works(a.output/'export',key)
assert recovered==archive(objects)
assert report['loss_tolerance_verified']
# Keep two of three completed carriers; restore from scores alone.
loss=a.output/'survivors'; loss.mkdir()
import shutil
for path in sorted((a.output/'night/woven').glob('*.musicxml'))[:2]: shutil.copyfile(path,loss/path.name)
assert recover_works(loss,key)[0]==archive(objects)
assert any(o['kind']=='Opus' for o in records)
print(json.dumps({'objects':len(restored),'records':len(records),'export_recovered':True,**report}),flush=True)
