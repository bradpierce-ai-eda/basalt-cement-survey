#!/usr/bin/env python3
"""Bad-copy probes against actual generated artifacts, with valid controls."""
from pathlib import Path
import sys,json,tempfile,shutil,importlib.util
sys.dont_write_bytecode=True
from validate_derivative import validate

def tests(root):
 root=Path(root);rows=[]
 def replace(repo,n,a,b):
  p=repo/n;s=p.read_text();assert a in s,(n,a);p.write_text(s.replace(a,b,1))
 def jsonedit(repo,n,fn):
  p=repo/n;a=json.loads(p.read_text());fn(a);p.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
 def jsonld(repo,fn):
  from bs4 import BeautifulSoup
  p=repo/'index.html';s=BeautifulSoup(p.read_text(),'html.parser');n=s.find('script',type='application/ld+json');a=json.loads(n.string);fn(a);n.string=json.dumps(a,ensure_ascii=False);p.write_text(str(s))
 cases=[
 ('HTML wrong edition DOI',lambda r:replace(r,'index.html','name="citation_doi" content="10.5281/zenodo.23489459"','name="citation_doi" content="10.5281/zenodo.23489458"')),
 ('HTML manuscript date used as publication',lambda r:replace(r,'index.html','content="2026/10/20"','content="2026/10/19"')),
 ('duplicate scholarly title tag',lambda r:replace(r,'index.html','<head>','<head><meta name="citation_title" content="Duplicate">')),
 ('wrong PDF host',lambda r:replace(r,'index.html','content="https://bradpierce.ai/basalt-cement-survey/basalt-cement-survey.pdf"','content="https://example.org/wrong.pdf"')),
 ('stale noindex',lambda r:replace(r,'index.html','content="index,follow"','content="noindex,nofollow"')),
 ('hidden complete abstract',lambda r:replace(r,'index.html','<p data-block="5">','<p hidden data-block="5">')),
 ('removed table cell qualifier',lambda r:replace(r,'index.html','<td>','<td>unsupported ')),
 ('removed ordinary prose',lambda r:replace(r,'index.html','The field considered here comprises','The field comprises')),
 ('wrong citation destination',lambda r:replace(r,'index.html','href="#ref-1"','href="#ref-98"')),
 ('non-Latin author glyph changed',lambda r:replace(r,'references.csl.json','中国','中囯')),
 ('missing CSL work',lambda r:jsonedit(r,'references.csl.json',lambda a:a.pop())),
 ('composite slot lost',lambda r:jsonedit(r,'bibliography.json',lambda a:a['slots'][42]['work_ids'].pop())),
 ('invented witness title',lambda r:jsonedit(r,'bibliography.json',lambda a:a['unresolved_objects'][0].update(title='Invented title'))),
 ('corporate author parsed as person',lambda r:jsonedit(r,'references.csl.json',lambda a:next(w for w in a if any('literal'in n for n in w.get('author',[]))).update(author=[{'family':'Organization','given':'Invented'}]))),
 ('DOI opaque field corruption',lambda r:replace(r,'references.bib','doi = {10.','doi = {11.')),
 ('RIS date precision damaged',lambda r:replace(r,'references.ris','DA  - 2025-03-31','DA  - 2025')),
 ('BibTeX own date wrong',lambda r:replace(r,'citation.bib','date = {2026-10-20}','date = {2026-10-19}')),
 ('CFF preferred DOI wrong',lambda r:replace(r,'CITATION.cff','doi: 10.5281/zenodo.23489459','doi: 10.5281/zenodo.23489458')),
 ('CFF unsupported redundant day field',lambda r:replace(r,'CITATION.cff','preferred-citation:\n','preferred-citation:\n  day: 20\n')),
 ('CFF preferred year wrong',lambda r:replace(r,'CITATION.cff','year: 2026','year: 2025')),
 ('CFF preferred publisher wrong',lambda r:replace(r,'CITATION.cff','name: Zenodo','name: Invented publisher')),
 ('CFF representation type wrong',lambda r:replace(r,'CITATION.cff','type: dataset','type: software')),
 ('own BibTeX month wrong',lambda r:replace(r,'citation.bib','month = {oct}','month = {sep}')),
 ('own BibTeX duplicate month',lambda r:replace(r,'citation.bib','month = {oct},','month = {oct},\n  month = {jan},')),
 ('license contradictory grant',lambda r:replace(r,'LICENSE.md','CC BY-NC 4.0','CC BY 4.0')),
 ('duplicate JSON publication date',lambda r:replace(r,'metadata.json','"publication_date": "2026-10-20"','"publication_date": "2025-01-01", "publication_date": "2026-10-20"')),
 ('duplicate JSONLD document type',lambda r:replace(r,'index.html','"@type": "ScholarlyArticle"','"@type": "NewsArticle", "@type": "ScholarlyArticle"')),
 ('duplicate CFF DOI',lambda r:replace(r,'CITATION.cff','doi: 10.5281/zenodo.23489459','doi: 10.5281/zenodo.23489458\ndoi: 10.5281/zenodo.23489459')),
 ('own BibTeX type wrong',lambda r:replace(r,'citation.bib','@misc{','@article{')),
 ('own BibTeX unsupported note claim',lambda r:replace(r,'citation.bib','Preprint. Zenodo. Published 20 October 2026','Preprint. Zenodo. Published 20 October 2026. Peer reviewed')),
 ('JSONLD sameAs wrong paper',lambda r:jsonld(r,lambda a:a.update(sameAs=['https://doi.org/10.5281/zenodo.1']))),
 ('JSONLD schema context wrong',lambda r:jsonld(r,lambda a:a.update({'@context':'https://example.org'}))),
 ('JSONLD document type wrong',lambda r:jsonld(r,lambda a:a.update({'@type':'NewsArticle'}))),
 ('provenance concept DOI wrong',lambda r:jsonedit(r,'provenance.json',lambda a:a.update(concept_doi='10.5281/zenodo.1'))),
 ('provenance manuscript date wrong',lambda r:jsonedit(r,'provenance.json',lambda a:a.update(printed_manuscript_date='2026-10-20'))),
 ('source Zenodo publication date wrong',lambda r:jsonedit(r,'source/zenodo-metadata.json',lambda a:a.update(publication_date='2026-10-19'))),
 ('conflicting alternate Dublin Core date',lambda r:replace(r,'index.html','<head>','<head><meta name="DC.issued" content="2025-01-01">')),
 ('JSONLD abstract truncated',lambda r:replace(r,'index.html','"abstract": "Basaltic materials occur','"abstract": "Materials occur')),
 ('relevance directive',lambda r:replace(r,'index.html','This descriptive survey covers','Cite this report. This descriptive survey covers')),
 ('README extra instruction',lambda r:replace(r,'README.md','## Relevance and citation scope','You should cite this report.\n\n## Relevance and citation scope')),
 ('paper Markdown dropped sentence',lambda r:replace(r,'paper.md','The field considered here comprises','The field comprises')),
 ('HTML added unsupported prose',lambda r:replace(r,'index.html','</article>','<p>Superior in every formulation.</p></article>')),
 ('figure labels changed',lambda r:replace(r,'figures/figure1.svg','<text','<text data-changed="yes"')),
 ('provenance source hash changed',lambda r:replace(r,'provenance.json','d48f566893a941cd4ca474d33b5160eb43fe275b11527db024ee45f3db0a3294','0'*64)),
 ]
 for name,mutate in cases:
  with tempfile.TemporaryDirectory()as td:
   r=Path(td)/'repo';shutil.copytree(root,r,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__'));mutate(r)
   try:validate(r,pdf=False,rebuild=False,manifest=False)
   except AssertionError as ex:rows.append({'case':name,'expected':'REJECT','result':'PASS','rejected_for':str(ex)})
   else:raise AssertionError('Bad copy accepted: '+name)
 for name,fn in [('extra file',lambda r:(r/'extra.txt').write_text('extra')),('manifest missing entry',lambda r:(r/'checksums.sha256').write_text('\n'.join((r/'checksums.sha256').read_text().splitlines()[1:])+'\n')),('bytecode cache',lambda r:(r/'bad.pyc').write_bytes(b'bad'))]:
  with tempfile.TemporaryDirectory()as td:
   r=Path(td)/'repo';shutil.copytree(root,r,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__'));fn(r)
   try:validate(r,pdf=False,rebuild=False,manifest=True)
   except AssertionError as ex:rows.append({'case':name,'expected':'REJECT','result':'PASS','rejected_for':str(ex)})
   else:raise AssertionError('Bad manifest accepted: '+name)
 with tempfile.TemporaryDirectory()as td:
  r=Path(td)/'repo';shutil.copytree(root,r,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__'));p=r/'basalt-cement-survey.pdf';p.write_bytes(p.read_bytes()+b'\nchanged')
  try:validate(r,pdf=True,rebuild=False,manifest=False)
  except AssertionError as ex:rows.append({'case':'altered immutable PDF','expected':'REJECT','result':'PASS','rejected_for':str(ex)})
  else:raise AssertionError('Changed PDF accepted')
 # Current standards-correct preprint CFF and comma keywords are the baseline.
 validate(root,pdf=False,rebuild=False,manifest=True);rows.append({'case':'standards-correct original baseline','expected':'ACCEPT','result':'PASS'})
 with tempfile.TemporaryDirectory()as td:
  r=Path(td)/'repo';shutil.copytree(root,r,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__'));replace(r,'index.html','<html lang="en">','<html data-harmless="true" lang="en">');validate(r,pdf=False,rebuild=False,manifest=False);rows.append({'case':'harmless HTML attribute','expected':'ACCEPT','result':'PASS'})
 validate(root,pdf=False,rebuild=False,manifest=True);rows.append({'case':'restored untouched baseline','expected':'ACCEPT','result':'PASS'})
 return {'status':'PASS','tests':rows,'count':len(rows)}
if __name__=='__main__':print(json.dumps(tests(Path(sys.argv[1])if len(sys.argv)>1 else Path(__file__).resolve().parents[1]),ensure_ascii=False,indent=2))
