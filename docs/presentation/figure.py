"""Source-derived calibration illustration; no specimen/physical-truth claim."""
from pathlib import Path
import json,html
P=Path(__file__).resolve().parent
j=json.loads((P/'journey.json').read_text());r=json.loads((P/'changed.json').read_text())['pairs'][0];z=next(a for a in r['comparison']['axes']if a['axis']=='Z');steps=[float(z[k]['micrometres'])for k in ['source','export']];assert steps==[1.5,3]and j['shape']==[3,8,12]
INK='#222c31';PAPER='#f4f2ed';GREEN='#245b57';RED='#922f21';MUTED='#52605a'
def render(phone):
 W,H=(375,1150)if phone else(1200,680);a=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc"><title id="title">Same synthetic array, different recorded Z spacing</title><desc id="desc">All three synthetic planes have identical samples in source and changed export. Recorded Z spacing doubles from 1.5 to 3 micrometres. Rulers use a common zero-to-six micrometre scale; zero is chosen for relative centers. Thumbnail height does not depict plane thickness. Reticle compares metadata; fixture generation separately checks pixel equality.</desc><rect width="100%" height="100%" fill="{PAPER}"/><g font-family="Arial, Helvetica, sans-serif">']
 def t(x,y,s,size=16,color=INK):a.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{html.escape(str(s))}</text>')
 t(24 if phone else 28,35,'Reticle / Calibration across an export',13,GREEN)
 if phone:
  t(24,83,'Same array.',30);t(24,121,'Different Z spacing.',28);t(24,158,'Three planes. All 288 samples retained.',14)
 else:
  t(28,83,'Same array. Different recorded spacing.',36);t(28,119,'Reticle checks metadata. The synthetic fixture separately confirms all 288 samples are identical.',17)
 for case,step in enumerate(steps):
  x=20 if phone else 28+case*594;y=(190+case*380)if phone else 155;w=335 if phone else 550;h=350 if phone else 400;scale=32 if phone else 40;zero=y+(305 if phone else 345);axis=x+(38 if phone else 62);imgx=x+(66 if phone else 96);cell=4 if phone else 7
  a.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fffefa" stroke="#a5afaa"/>');t(x+16,y+30,'Source OME-TIFF'if case==0 else'Changed OME-TIFF',16,GREEN if case==0 else RED);t(x+16,y+63,f'Recorded Z step: {step:g} µm',21 if phone else 25)
  t(x+5,y+90,'Z (µm)',11,MUTED)
  a.append(f'<g data-case="{case}" data-scale="{scale}" data-zero="{zero}"><line x1="{axis}" y1="{zero-6*scale}" x2="{axis}" y2="{zero}" stroke="{MUTED}"/>')
  for v in [0,1.5,3,4.5,6]:
   yy=zero-v*scale;a.append(f'<line x1="{axis-5}" y1="{yy}" x2="{axis+5}" y2="{yy}" stroke="{MUTED}"/>');t(x+5,yy+4,f'{v:g}',10,MUTED)
  for plane,values in enumerate(j['pixels']):
   center=zero-plane*step*scale;top=center-8*cell/2
   a.append(f'<g data-plane="{plane}" data-z="{plane*step:g}" data-center="{center}">')
   for iy,row in enumerate(values):
    for ix,value in enumerate(row):
     shade=round(value*255/287);a.append(f'<rect data-value="{value}" x="{imgx+ix*cell}" y="{top+iy*cell}" width="{cell}" height="{cell}" fill="rgb({shade},{shade},{shade})"/>')
   a.append(f'<rect x="{imgx}" y="{top}" width="{12*cell}" height="{8*cell}" fill="none" stroke="{INK}"/>');t(imgx+12*cell+14,center-3,f'Plane {plane}',14 if phone else 18);t(imgx+12*cell+14,center+17,f'relative Z = {plane*step:g} µm',12 if phone else 16,MUTED);a.append('</g>')
  a.append('</g>');t(x+16,y+h-11,'Relative Z: zero chosen. No slice thickness depicted.',11 if phone else 12,MUTED)
 if phone:
  for yy,s in [(987,'X control: 0.25 µm = 250 nm.'),(1015,'Equivalent units → agreement, exit 0.'),(1053,'Ordinary TIFF: Z lost, mapping unverified.'),(1081,'The mixed batch retains all pairs, exit 2.'),(1122,'Synthetic metadata evidence, not calibration truth.')]:t(24,yy,s,12 if yy==1122 else 14,GREEN if yy==1015 else MUTED)
 else:
  t(28,598,'Equivalent-unit control: 0.25 µm = 250 nm → verified agreement (exit 0).',20,GREEN);t(28,633,'Ordinary TIFF loses Z: mapping unverified (exit 2). The mixed batch retains every result.',17);t(28,664,'Common 0–6 µm rulers. Synthetic relative coordinates and grayscale previews; no physical calibration or pixel-check claim by Reticle.',13,MUTED)
 a.append('</g></svg>');return ''.join(a)
for phone in [False,True]:
 name='spacing-mobile'if phone else'spacing';svg=render(phone);(P/(name+'.svg')).write_text(svg);(P/(name+'.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reticle calibration evidence</title><style>body{margin:0}svg{display:block;width:100%;height:auto}</style>'+svg)
