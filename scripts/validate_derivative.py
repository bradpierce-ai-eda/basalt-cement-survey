#!/usr/bin/env python3
"""Actual-file conservation, scholarly metadata, references and immutable-PDF checks."""
from pathlib import Path
import json,re,hashlib,sys,argparse,tempfile,subprocess,shutil,unicodedata,xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import yaml,bibtexparser,pymupdf
from pypdf import PdfReader

def need(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def norm(s):return ' '.join(unicodedata.normalize('NFC',s).replace('\u2060','').split())
def load_json(s):
 def pairs(xs):
  need(len(xs)==len({k for k,_ in xs}),'duplicate JSON metadata key')
  return dict(xs)
 return json.loads(s,object_pairs_hook=pairs)
def markdown_expected(blocks):
 out=[]
 for i,b in enumerate(blocks):
  if b['type']=='table':
   rows=b['rows'];cell=lambda row:'| '+' | '.join(x.replace('|','\\|').replace('\n','<br>')for x in row)+' |'
   out.extend([cell(rows[0]),cell(['---']*len(rows[0]))]+[cell(row)for row in rows[1:]])
  elif b['type']=='figure':out.append('!['+b['alt']+']('+b['asset']+')')
  else:out.append(('# 'if i==0 else '#'*min(b['level']+1,6)+' 'if b['type']=='heading'else '')+b['text'])
 return '\n\n'.join(out)+'\n'
class UniqueYaml(yaml.SafeLoader):pass
def unique(loader,node,deep=False):
 keys=[loader.construct_object(k,deep=deep)for k,_ in node.value];need(len(keys)==len(set(keys)),'duplicate CFF field');return yaml.SafeLoader.construct_mapping(loader,node,deep=deep)
UniqueYaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique)
def validate(root,pdf=True,rebuild=True,manifest=True):
 root=Path(root);a=load_json((root/'source/paper.json').read_text());inv=load_json((root/'source/invariants.json').read_text());bs=a['blocks'];results={}
 need(sha(json.dumps(bs,ensure_ascii=False,sort_keys=True).encode())==inv['canonical_blocks_sha256'],'canonical source block hash')
 meta={k:v for k,v in a.items()if k not in ['blocks','references']};need(meta==inv['metadata'],'frozen complete authority metadata');need(load_json((root/'metadata.json').read_text())==meta,'complete public metadata')
 soup=BeautifulSoup((root/'index.html').read_text(),'html.parser');nodes=soup.select('[data-block]');need(len(nodes)==inv['block_count'],'all HTML blocks')
 for i,(b,n)in enumerate(zip(bs,nodes)):
  need(n['data-block']==str(i),'HTML ordered block '+str(i))
  if b['type']=='table':
   need([[c.get_text()for c in row.find_all(['td','th'],recursive=False)]for row in n.find_all('tr')]==b['rows'],'all HTML table cells '+str(i));need(all(c.get('scope')=='col'for c in n.find_all('th')),'column scopes')
  elif b['type']=='figure':need(n.img['alt']==b['alt']and n.img['src']==b['asset'],'figure meaning and asset '+str(i))
  else:need(n.get_text()==b['text'],'HTML full text '+str(i))
 need(sum(b['type']=='table'for b in bs)==inv['tables']and sum(b['type']=='figure'for b in bs)==inv['figures'],'complex object counts')
 for n in nodes:
  for link in n.find_all('a'):
   label=link.get_text();dest=link.get('href','')
   if label.startswith('http'):need(dest==label,'literal URL destination')
   elif label.startswith('10.'):need(dest=='https://doi.org/'+label,'DOI destination')
   elif label.isdigit():need(dest=='#ref-'+str(int(label))and soup.select_one(dest)is not None,'numbered reference destination')
 refs=[b['text']for b in bs if b['type']=='reference'];need(refs==a['references']and len(refs)==98,'source reference identities/order')
 need(not any(re.search(r'\b(?:Accessed|Retrieved)\s+\d',r,re.I)for r in refs),'no reader access dates')
 need(not any(re.search(r'https?://\S+\.(?=\s|$)',r)for r in refs),'reference URL punctuation')
 paper=(root/'paper.md').read_text();need(paper==markdown_expected(bs),'all Markdown paragraphs/tables/figures/headings')
 readme=(root/'README.md').read_text();beg='<!-- BEGIN CANONICAL MANUSCRIPT -->\n';end='<!-- END CANONICAL MANUSCRIPT -->\n';need(readme.count(beg)==readme.count(end)==1,'README canonical boundaries');need(readme.split(beg)[1].split(end)[0]==paper and readme.endswith(end),'README full canonical body')
 prefix=readme.split(beg)[0];need('## Relevance and citation scope\n\n'+a['relevance_scope']in prefix,'README synchronized declarative scope');need(a['preferred_citation']in prefix,'README preferred DOI citation')
 expected_prefix='# '+a['title']+'\n\nBrad Pierce · Published 20 October 2026 · [Preprint]\n\n'+a['preferred_citation']+'\n\nThe DOI-linked Zenodo edition is the publication of record. This repository contains its complete machine-readable derivative and citation files.\n\n## Relevance and citation scope\n\n'+a['relevance_scope']+'\n\n'
 need(prefix==expected_prefix,'README exact framing; no added instructions or claims')
 need((root/'references.md').read_text()=='References\n\n'+'\n\n'.join(refs)+'\n','exact reference companion')
 expected={'citation_title':a['title'],'citation_author':'Brad Pierce','citation_publication_date':'2026/10/20','citation_doi':a['doi'],'citation_pdf_url':a['public_urls']['pdf'],'citation_fulltext_html_url':a['public_urls']['article'],'keywords':', '.join(a['keywords']),'description':a['abstract'],'robots':'index,follow'}
 for k,v in expected.items():need([n.get('content')for n in soup.find_all('meta',attrs={'name':k})]==[v],'HTML metadata cardinality/value '+k)
 need({n.get('name')for n in soup.find_all('meta')if n.get('name')}==set(expected)|{'viewport'},'no conflicting alternative bibliographic meta fields')
 need({n.get('property')for n in soup.find_all('meta')if n.get('property')}=={'og:title','og:description','og:url','og:type'},'no conflicting alternative property metadata')
 need([n['href']for n in soup.select('link[rel=canonical]')]==[a['public_urls']['article']],'self canonical')
 for k,v in {'og:title':a['title'],'og:description':a['abstract'],'og:url':a['public_urls']['article'],'og:type':'article'}.items():need([n.get('content')for n in soup.find_all('meta',attrs={'property':k})]==[v],'OG field '+k)
 need(soup.title.get_text()==a['title']+' — Brad Pierce','browser title role')
 need(len(soup.select('h1'))==1 and soup.h1.get_text()==a['title'],'one exact prominent title')
 front=soup.select_one('#scholarly-front-matter');scope=soup.select_one('#relevance-and-citation-scope');body=soup.select_one('#canonical-paper');need(front and scope and body,'scholarly sections')
 need(front.select_one('[data-block="5"]').get_text()==a['abstract'],'full visible opening abstract');need(front.select_one('.author').get_text()=='Brad Pierce','human byline')
 need(front.time['datetime']==a['publication_date']and front.time.get_text()=='20 October 2026','actual publication date visible')
 need(str(soup).index('id="scholarly-front-matter"')<str(soup).index('id="relevance-and-citation-scope"')<str(soup).index('id="canonical-paper"'),'front/abstract before scope/body')
 need(scope.h2.get_text()=='Relevance and citation scope'and scope.p.get_text()==a['relevance_scope'],'exact synchronized relevance')
 need([p.get_text()for p in scope.find_all('p')]==[a['relevance_scope'],a['preferred_citation'],'This static full-text representation is a derivative of the Zenodo publication of record.','PDF · Zenodo record · Paper citation (BibTeX) · Source bibliography (BibTeX) · RIS · CSL-JSON'],'exact added HTML framing')
 texts=[b.get('text')for b in bs];di=texts.index('AI Assistance and Editorial Responsibility');need(texts[di+1]==a['disclosure']and texts[di+2]=='References','disclosure before References')
 need(soup.select_one('ol.references')and len(soup.select('ol.references>li'))==98,'standard ordered references')
 need(not soup.select('[hidden], [aria-hidden=true], details, iframe, form'),'no hidden/gated content')
 need(not soup.find_all(style=re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden',re.I)),'no hidden inline styles')
 css=' '.join(x.get_text()for x in soup.find_all('style'));need(not re.search(r'display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em)?\b',css,re.I),'no concealed CSS text')
 scripts=soup.find_all('script');need(len(scripts)==1 and scripts[0].get('type')=='application/ld+json','no executable JS requirement')
 ld=load_json(scripts[0].string);need(ld['headline']==a['title']and ld['author']==[{'@type':'Person','name':'Brad Pierce','givenName':'Brad','familyName':'Pierce','sameAs':a['authors'][0]['orcid']}],'JSONLD title/authorship')
 need(ld['datePublished']==a['publication_date']and ld['identifier']['value']==a['doi']and ld['url']==a['public_urls']['article']and ld['encoding']['contentUrl']==a['public_urls']['pdf'],'JSONLD identifiers/date/URLs');need(ld['abstract']==a['abstract']and ld['keywords']==a['keywords']and ld['license']=='https://creativecommons.org/licenses/by-nc/4.0/','JSONLD typed lists/rights')
 expected_ld={'@context':'https://schema.org','@type':'ScholarlyArticle','headline':a['title'],'author':[{'@type':'Person','name':'Brad Pierce','givenName':'Brad','familyName':'Pierce','sameAs':a['authors'][0]['orcid']}],'datePublished':a['publication_date'],'identifier':{'@type':'PropertyValue','propertyID':'DOI','value':a['doi']},'url':a['public_urls']['article'],'sameAs':[a['doi_url'],a['zenodo_record']],'encoding':{'@type':'MediaObject','contentUrl':a['public_urls']['pdf'],'encodingFormat':'application/pdf'},'abstract':a['abstract'],'keywords':a['keywords'],'license':'https://creativecommons.org/licenses/by-nc/4.0/','isAccessibleForFree':True,'inLanguage':'en','publisher':{'@type':'Organization','name':'Zenodo'}}
 need(ld==expected_ld,'complete JSONLD semantics and field set')
 cff=yaml.load((root/'CITATION.cff').read_text(),Loader=UniqueYaml);pc=cff['preferred-citation'];human=[{'family-names':'Pierce','given-names':'Brad','orcid':a['authors'][0]['orcid']}]
 need(set(cff)=={'cff-version','message','type','title','authors','doi','date-released','url','abstract','keywords','license','preferred-citation'}and set(pc)=={'type','status','title','authors','doi','date-published','year','url','publisher','notes'},'CFF schema-compatible field set')
 for x in [cff,pc]:need(x['title']==a['title']and x['doi']==a['doi']and x['authors']==human and x['url']==a['zenodo_record'],'CFF actual/preferred identity')
 need(cff['date-released']==pc['date-published']==a['publication_date']and cff['keywords']==a['keywords']and cff['license']==a['license']and cff['abstract']==a['abstract'],'CFF date/list/rights');need(pc.get('status')=='preprint'and pc['type']=='generic','CFF published preprint type')
 need(cff['cff-version']=='1.2.0'and cff['type']=='dataset'and cff['message']=='Bibliographic identity of the DOI-linked Zenodo preprint, the publication of record.','CFF top-level representation and declarative message')
 need(pc['year']==2026 and pc['publisher']=={'name':'Zenodo'}and pc['notes']=='Published preprint; the version DOI identifies the publication of record.','CFF preferred full publication semantics')
 own=bibtexparser.loads((root/'citation.bib').read_text()).entries;need(len(own)==1,'own citation count');b=own[0]
 own_names=re.findall(r'[,\{]\s*([A-Za-z][\w-]*)\s*=',(root/'citation.bib').read_text());need(len(own_names)==len({n.lower()for n in own_names}),'duplicate own BibTeX field')
 for k,v in {'author':'Pierce, Brad','title':a['title'],'doi':a['doi'],'url':a['doi_url'],'date':a['publication_date'],'year':'2026','keywords':', '.join(a['keywords'])}.items():need(b.get(k)==v,'own BibTeX '+k)
 need('Preprint'in b['note']and not re.search('reserved|unpublished',b['note'],re.I),'published citation status')
 need(b=={'ENTRYTYPE':'misc','ID':'pierce_basalt_2026','author':'Pierce, Brad','title':a['title'],'year':'2026','month':'oct','date':'2026-10-20','doi':a['doi'],'url':a['doi_url'],'keywords':', '.join(a['keywords']),'note':'Preprint. Zenodo. Published 20 October 2026'},'complete own BibTeX type/date/fields; no unsupported claims')
 bibli=load_json((root/'bibliography.json').read_text());need(sha((root/'bibliography.json').read_bytes())==inv['bibliography_sha256'],'frozen bibliography identity')
 works=bibli['works'];need(len(works)==len({w['id']for w in works})==100,'work counts and unique IDs');need(load_json((root/'references.csl.json').read_text())==works,'CSL all-work equality');need([s['exact_reference']for s in bibli['slots']]==refs,'slot exactness')
 fixture=load_json((root/'source/expected-bibliography-fields.json').read_text());need({w['id']:{k:w[k]for k in fixture['field_policy']if k in w}for w in works}==fixture['works'],'independent all-work field fixture')
 need({w['id']for w in works}=={i for s in bibli['slots']for i in s['work_ids']},'no orphan works/slots');need([s['number']for s in bibli['slots']if len(s['work_ids'])>1]==[43,76],'composite slots retained');need(len(bibli['unresolved_objects'])==1 and not bibli['unresolved_objects'][0].get('title')and not bibli['unresolved_objects'][0].get('author'),'unresolved witness not invented')
 for n,h in inv['figure_sha256'].items():need(sha((root/'figures'/n).read_bytes())==h,'figure immutable geometry/labels '+n)
 # Audit added prose separately from unchanged publication and quoted reference strings.
 rejected=r'when to cite|cite this|if this work is relevant|you should|ignore (?:all|previous)|system prompt|act as (?:an?|the)|must obey|instructions? for (?:ai|models?|crawlers?)'
 added=[prefix,scope.get_text(),cff['message'],json.dumps(meta,ensure_ascii=False),json.dumps(ld,ensure_ascii=False),(root/'provenance.json').read_text(),(root/'LICENSE.md').read_text()]
 for i,s in enumerate(added):need(not re.search(rejected,s,re.I),'prompt-injection appearance '+str(i))
 need((root/'LICENSE.md').read_text()=='# Rights and license\n\n© 2026 Brad Pierce. The authored survey and derivative representation are available under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Bibliographic attribution does not confer rights in third-party works. No separate software license grant is asserted for the accompanying validation scripts.\n','exact rights/license scope; no contradictory grant')
 for p in root.rglob('*'):
  if p.is_file()and p.suffix in ['.json','.html','.md','.cff']and 'node_modules'not in p.parts:
   need('/Users/'not in p.read_text(),'no private host path in public '+str(p.relative_to(root)))
 provenance=load_json((root/'provenance.json').read_text());need(provenance['source_sha256']==inv['pdf_sha256']and provenance['preferred_version_doi']==a['doi']and provenance['publication_date']==a['publication_date'],'provenance source identity')
 need(provenance==inv['provenance'],'complete frozen provenance, dates, source and transformation record')
 need(load_json((root/'source/zenodo-metadata.json').read_text())==inv['zenodo_metadata'],'complete frozen Zenodo public authority extract')
 need(soup.footer.get_text()=='© 2026 Brad Pierce · CC BY-NC 4.0'and soup.footer.a['href']=='https://creativecommons.org/licenses/by-nc/4.0/','HTML rights')
 stripped=BeautifulSoup(str(soup.body),'html.parser')
 for n in stripped.select('[data-block]'):n.decompose()
 f=stripped.select_one('#scholarly-front-matter');need(norm(f.get_text())=='Publication date: 20 October 2026 Manuscript date:','exact added front-matter labels/date');f.decompose()
 stripped.select_one('#relevance-and-citation-scope').decompose();stripped.footer.decompose();need(not stripped.get_text(strip=True),'no unaccounted HTML prose')
 with tempfile.TemporaryDirectory()as td:
  tmp=Path(td);(tmp/'bibliography.json').write_bytes((root/'bibliography.json').read_bytes())
  proc=subprocess.run([sys.executable,'-B',str(root/'scripts/export_bibliography.py'),'--repo',str(tmp)],capture_output=True,text=True);need(proc.returncode==0,'offline bibliography export')
  for name in ['references.bib','references.ris','references.csl.json','references.md']:need((tmp/name).read_bytes()==(root/name).read_bytes(),'frozen bibliography deterministic '+name)
 sitemap=ET.parse(root/'sitemap.xml');need([x.text for x in sitemap.iter()if x.tag.endswith('loc')]==[a['public_urls']['article'],a['public_urls']['pdf']],'paper sitemap')
 need((root/'robots.txt').read_text()=='User-agent: *\nAllow: /\nSitemap: '+a['public_urls']['article']+'sitemap.xml\n','paper robots')
 if manifest:
  actual={p.relative_to(root).as_posix()for p in root.rglob('*')if p.is_file()and not any(x in p.relative_to(root).parts for x in ['.git','node_modules','.venv','__pycache__'])}
  need(actual==set(inv['public_paths']),'exact intended public file set');need(not any(p.suffix in ['.pyc','.pyo']for p in root.rglob('*')if p.is_file()and'node_modules'not in p.parts),'no bytecode in release tree')
  lines=(root/'checksums.sha256').read_text().splitlines();entries=[x.split('  ',1)for x in lines];need(len(entries)==len({x[1]for x in entries}),'manifest duplicate paths');need({x[1]for x in entries}==actual-{'checksums.sha256'},'exact manifest coverage')
  for h,n in entries:need(sha((root/n).read_bytes())==h,'manifest bytes '+n)
 results.update({'full_text':'348 ordered blocks, all table cells and figure meanings conserved','bibliography':'98 slots / 100 identified works / 1 unresolved supporting object','metadata':'complete typed actual/preferred citation fields checked','framing':'declarative synchronized scope; no invented paper prose','manifest':'exact paths and hashes'if manifest else 'omitted by test option'})
 if rebuild:
  with tempfile.TemporaryDirectory()as td:
   tmp=Path(td)/'repo';shutil.copytree(root,tmp,ignore=shutil.ignore_patterns('node_modules','__pycache__','.git'))
   proc=subprocess.run([sys.executable,'-B',str(tmp/'scripts/build_derivative.py'),'--repo',str(tmp)],capture_output=True,text=True);need(proc.returncode==0,'clean deterministic build '+proc.stderr)
   need(all((tmp/p).read_bytes()==(root/p).read_bytes()for p in inv['public_paths']),'clean rebuild byte identity')
  results['clean_rebuild']='PASS'
 if pdf:
  p=root/'basalt-cement-survey.pdf';need(p.stat().st_size==inv['pdf_bytes']<5_000_000 and sha(p.read_bytes())==inv['pdf_sha256'],'immutable deposited PDF bytes')
  d=pymupdf.open(p);r=PdfReader(p);need(len(d)==inv['pdf_pages']==49,'PDF pages');need(d.metadata['title']==a['title']and d.metadata['author']=='Brad Pierce','PDF title/author');need(not any(f[2]=='Type3'for page in d for f in page.get_fonts()),'actual Type3 tuple check');need(sum(len(page.get_images())for page in d)==0,'all explanatory diagrams vector')
  need([x[1]for x in d.get_toc()]==[b['text']for b in bs if b['type']=='heading'],'PDF complete bookmark identity')
  probe=lambda s:re.sub(r'\s+','',unicodedata.normalize('NFC',s).replace('\u2060',''))
  engines={'pymupdf':'\n'.join('\n'.join(b[4]for b in page.get_text('blocks',sort=False)if b[1]<740)for page in d)}
  pop=shutil.which('pdftotext');need(pop is not None,'Poppler pdftotext required')
  for engine in ['pypdf','poppler']:
   pages=[]
   for pi,page in enumerate(r.pages):
    s=(page.extract_text()or'')if engine=='pypdf'else subprocess.run([pop,'-f',str(pi+1),'-l',str(pi+1),'-raw',str(p),'-'],capture_output=True,text=True,check=True).stdout
    if pi==0:s=re.sub(r'© 2026 Brad Pierce · CC BY-NC 4\.0[ \t\r\n]*1[ \t\r\n\f]*$','',s)
    else:s=re.sub(r'^\s*'+str(pi+1)+r'\s*\n','',s)
    pages.append(s.replace('© 2026 Brad Pierce · CC BY-NC 4.0',''))
   engines[engine]='\n'.join(pages)
  vals=[b['text']for b in bs if'text'in b]+[c for b in bs if b['type']=='table'for row in b['rows']for c in row]
  for engine,text in engines.items():
   stripped=probe(text)
   for i,v in enumerate(vals):need(probe(v)in stripped,'PDF complete text/cell '+engine+' '+str(i))
   need('\ufffd'not in text,'PDF replacement glyph '+engine)
  results['pdf']={'status':'PASS','sha256':inv['pdf_sha256'],'pages':49,'extractors':list(engines),'text_cells_each':len(vals),'visual_review_basis':'Exact unchanged publication bytes; historical all-page render evidence retained privately. No PDF/UA certification asserted.'}
 return results
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--fast',action='store_true');args=parser.parse_args()
 try:print(json.dumps({'status':'PASS','results':validate(args.repo,pdf=not args.fast,rebuild=not args.fast)},ensure_ascii=False,indent=2))
 except Exception as ex:print(json.dumps({'status':'FAIL','error':str(ex)},ensure_ascii=False));sys.exit(1)
