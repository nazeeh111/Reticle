"""Read recorded bytes; optionally re-inspect extracted TIFFs with trusted Reticle."""
from pathlib import Path
import json,hashlib,argparse,copy,tempfile,subprocess,sys,importlib.metadata
P=Path(__file__).resolve().parent
manifest=json.loads((P/'MANIFEST.json').read_text())
for n,h in manifest.items():
 if hashlib.sha256((P/n).read_bytes()).hexdigest()!=h:raise ValueError('Changed bundle member: '+n)
saved=json.loads((P/'comparison.json').read_text());pairs=json.loads((P/'pairs.json').read_text());statuses=[]
for pair,definition in zip(saved['pairs'],pairs):
 for k in ['source','export']:
  data=(P/definition[k]).read_bytes();identity=pair['receipt'][k];assert hashlib.sha256(data).hexdigest()==identity['sha256']and len(data)==identity['bytes']
 c=pair['comparison'];status=2 if not c['verified']or any(i['severity']=='error'for i in pair['issues'])else 1 if c['shape_changes']or any(a.get('required',True)and a['status']!='same'for a in c['axes'])else 0;statuses.append(status)
assert statuses==[1,0,2]
p=argparse.ArgumentParser();p.add_argument('--native',action='store_true',help='Requires matching trusted current-source Reticle and declared dependencies');args=p.parse_args();native=False
if args.native:
 import reticle
 expected=json.loads((P/'runtime.json').read_text());package=Path(reticle.__file__).parent
 for name,h in expected['reticle_source_sha256'].items():assert hashlib.sha256((package/name).read_bytes()).hexdigest()==h,'Different current-source runtime: '+name
 from reticle.cli import load_manifest
 from reticle.batch import compare_batch
 fresh=compare_batch(load_manifest(P/'pairs.json'))
 def without_locations(document):
  q=copy.deepcopy(document)
  for row in q['pairs']:
   for k in ['source','export']:row['receipt'][k].pop('path')
  return q
 assert without_locations(fresh)==without_locations(saved),'Fresh metadata differs'
 with tempfile.TemporaryDirectory(prefix='reticle-recipient-')as td:
  dest=Path(td)/'fresh.json';dest.write_text(json.dumps(fresh));r=subprocess.run([sys.executable,'-I','-B','-m','reticle','--recheck',str(dest)],cwd=td,capture_output=True,text=True);assert r.returncode==2 and r.stdout.startswith('Receipt matches current inputs and policy; aggregate exit 2.'),(r.stdout,r.stderr)
 native=True
print(json.dumps({'memberHashes':len(manifest),'recordedStatuses':statuses,'allSourceExportReceiptHashesMatchDeliveredInputs':True,'nativeFreshComparisonAndFreshReceiptRecheck':native,'scope':'Recorded byte consistency by default; optional current-source TIFF metadata recomputation. No pixel equality, physical truth or origin authentication claim.'}))
