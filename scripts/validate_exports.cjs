const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {Cite}=require('@citation-js/core');require('@citation-js/plugin-bibtex');require('@citation-js/plugin-csl');require('@citation-js/plugin-ris');
const root=path.resolve(process.argv[2]);
// This fixture is independently transcribed from input DOCX + approved ledger,
// never produced from the CSL being checked or from this consumer's own parser.
const fixture=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../source/expected-bibliography-fields.json'),'utf8'));
const trusted=fixture.works, norm=s=>String(s??'').normalize('NFC');
const name=a=>a.literal||[a.family,a.given].filter(Boolean).join(', ');
const note=a=>norm(Array.isArray(a.note)?a.note.join(' '):a.note||'');
let count=0,issues=[],limitations=[],formats=[];
const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
function check(file,id,field,actual,expected){count++;if(JSON.stringify(canonical(actual))!==JSON.stringify(canonical(expected)))issues.push({file,id,field,actual,expected});}
for(const file of ['references.bib','references.csl.json','references.ris']){
 let parsed;try{parsed=new Cite(fs.readFileSync(path.join(root,file),'utf8')).data;}catch(e){issues.push({file,error:e.message});continue;}
 const records=Object.fromEntries(parsed.map(a=>[a.id,a]));formats.push(file);
 check(file,'all','record count',parsed.length,Object.keys(trusted).length);
 check(file,'all','unique IDs',Object.keys(records).sort(),Object.keys(trusted).sort());
 for(const [id,w]of Object.entries(trusted)){
  const a=records[id];if(!a)continue;
  if(file==='references.csl.json'){
   for(const k of fixture.field_policy)check(file,id,k,a[k]??null,w[k]??null);
   continue;
  }
  check(file,id,'title',norm(a.title),norm(w.title));
  check(file,id,'DOI',a.DOI||null,w.DOI||null);check(file,id,'URL',a.URL||null,w.URL||null);
  check(file,id,'authors',(a.author||[]).map(name).map(norm),(w.author||[]).map(name).map(norm));
  check(file,id,'date',a.issued?.['date-parts']||null,w.issued?.['date-parts']||null);
  for(const k of ['container-title','volume','issue'])check(file,id,k,a[k]??null,w[k]??null);
  if(w.page)check(file,id,'page',norm(a.page).replace(/–/g,'-'),w.page.replace(/–/g,'-'));
  check(file,id,'source note preserved',note(a).includes(norm(w.note)),true);
  check(file,id,'explicit source type',note(a).includes('Source type: '+w.type+'.'),true);
  if(w['title-translation'])check(file,id,'adjacent translation retained in note',(note(a)+' '+norm(a.annote)).includes(w['title-translation']),true);
  if(w['article-locator']){
   // Citation.js maps BibLaTeX eid to number and RIS SP-only to page-first.
   const locator=file==='references.bib'?a.number:(a['page-first']||a.page);
   check(file,id,'article identifier',norm(locator),w['article-locator']);
   if(file==='references.ris')check(file,id,'identifier role note',note(a).includes('Article identifier: '+w['article-locator']),true);
  }
  if(w.number)check(file,id,'publication identifier retained',note(a).includes('Publication identifier: '+w.number),true);
  const expectedType=file==='references.bib'?
   (['article-journal','article-magazine'].includes(w.type)?'article-journal':w.type==='paper-conference'?'paper-conference':'document'):
   (['standard','dataset'].includes(w.type)?'document':w.type);
  check(file,id,'documented consumer type',a.type,expectedType);
 }
}
limitations.push('Classic BibTeX article maps magazines to article-journal; misc maps patents, standards, reports, theses, datasets and webpages to document. Explicit source-type notes preserve the richer CSL classification.');
limitations.push('RIS GEN is used for standards/datasets. Citation.js ignores M1 patent numbers in its mixed parser, so exact identifiers are also preserved and checked in parsed notes.');
limitations.push('CSL retains all18 fixture fields. Some Bib/RIS custom fields are represented by the complete checked source note rather than a native consumer field, including date qualifiers, institutional applicant roles and project periods.');
const meta=JSON.parse(fs.readFileSync(path.join(root,'source/paper.json'),'utf8'));
const own=new Cite(fs.readFileSync(path.join(root,'citation.bib'),'utf8')).data;
check('citation.bib','own','count',own.length,1);const ownRecord=own[0];
check('citation.bib','own','title',ownRecord.title,meta.title);
check('citation.bib','own','authors',(ownRecord.author||[]).map(name),['Pierce, Brad']);
check('citation.bib','own','date',ownRecord.issued?.['date-parts'],[[2026,10,20]]);
check('citation.bib','own','DOI',ownRecord.DOI,meta.doi);
check('citation.bib','own','URL',ownRecord.URL,meta.doi_url);
check('citation.bib','own','keywords',String(ownRecord.keyword).split(',').map(x=>x.trim()),meta.keywords);
check('citation.bib','own','published preprint status',/Preprint/.test(note(ownRecord))&&!/reserved|unpublished/i.test(note(ownRecord)),true);
check('citation.bib','own','exact publication note',note(ownRecord),'Preprint. Zenodo. Published 20 October 2026');
check('citation.bib','own','parsed generic document type',ownRecord.type,'document');
const ownRaw=fs.readFileSync(path.join(root,'citation.bib'),'utf8');
check('citation.bib','own','source BibTeX entry type',/^@misc\{/m.test(ownRaw),true);
check('citation.bib','own','source month field',/\bmonth\s*=\s*\{oct\}/.test(ownRaw),true);
const ownFieldNames=[...ownRaw.matchAll(/[,\{]\s*([A-Za-z][\w-]*)\s*=/g)].map(x=>x[1].toLowerCase());
check('citation.bib','own','no duplicate fields',ownFieldNames.length,new Set(ownFieldNames).size);
console.log(JSON.stringify({status:issues.length?'FAIL':'PASS',formats:formats.length,works:Object.keys(trusted).length,field_checks:count,limitations,issues},null,2));process.exitCode=issues.length?1:0;
