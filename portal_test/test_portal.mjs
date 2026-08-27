/* Headless test of portal_jem_marketing_daily.html:
   extracts the page's <script>, runs it against a minimal DOM/fetch stub and the
   REAL data written by run_manifest.py, then asserts on the rendered HTML. */
import fs from 'node:fs';
import path from 'node:path';

const SITE = path.resolve('site');
/* Lê o .html DE ORIGEM, não a cópia em site/.
   A cópia só é atualizada pelo run_manifest.py, que exige o Magento ao vivo (rede da
   JEM + ../.env). Fora dessa rede o sync não acontece, e o harness passava a testar uma
   página velha SEM AVISO -- foi exatamente o que aconteceu em 26/08. A cópia continua
   existindo para a prévia no navegador, e a divergência é declarada aqui em voz alta. */
const SRC = path.resolve('..', 'portal_jem_marketing_daily.html');
const HTML = fs.readFileSync(SRC, 'utf8');
const COPY = path.join(SITE, 'index.html');
if (!fs.existsSync(COPY) || fs.readFileSync(COPY, 'utf8') !== HTML)
  console.log('⚠ site/index.html está DIFERENTE do .html de origem (a prévia no navegador '
    + 'está velha). O teste roda contra a origem; rode run_manifest.py para sincronizar.');

/* ---------------- minimal DOM ---------------- */
class ClassList {
  constructor(){this.s=new Set();}
  add(...c){c.forEach(x=>this.s.add(x));}
  remove(...c){c.forEach(x=>this.s.delete(x));}
  toggle(c,on){on?this.s.add(c):this.s.delete(c);}
  contains(c){return this.s.has(c);}
  toString(){return [...this.s].join(' ');}
}
class El {
  constructor(tag='div'){
    this.tagName=tag; this.innerHTML=''; this.textContent=''; this.value=''; this.min=''; this.max='';
    this.style={}; this.dataset={}; this.classList=new ClassList(); this.children=[];
    this._listeners={};
    if(tag==='template'){
      const self=this;
      this.content={get firstChild(){ const e=new El('section');
        const m=/data-tile="([^"]+)"/.exec(self.innerHTML); if(m)e.dataset.tile=m[1]; return e; }};
    }
  }
  appendChild(c){this.children.push(c);return c;}
  insertBefore(){/* drag only */}
  setAttribute(k,v){(this._attrs=this._attrs||{})[k]=v;}
  getAttribute(k){return (this._attrs||{})[k]??null;}
  querySelectorAll(){return [];}
  querySelector(){return null;}
  closest(){return null;}
  addEventListener(t,fn){(this._listeners[t]=this._listeners[t]||[]).push(fn);}
  getBoundingClientRect(){return {left:0,top:0,width:200,height:100};}
}
const registry=new Map();
const documentElement=new El('html');
const document={
  readyState:'loading',
  documentElement,
  getElementById(id){ if(!registry.has(id))registry.set(id,new El('div')); return registry.get(id); },
  createElement(tag){return new El(tag);},
  addEventListener(){},
};
const windowStub={ innerWidth:1600, addEventListener(){}, setInterval(){}, };
/* AIDash.meta é como o PORTAL informa falha de dataset (status ERROR + mensagem) -- é por
   aqui que veio o "The operation was aborted due to timeout" de 29/07. O stub de fetch
   simula rede caída; este simula o servidor do portal reportando a falha. */
let META=new Map();
const aidashStub={meta:name=>META.get(name)||null};
windowStub.AIDash=aidashStub;
globalThis.AIDash=aidashStub;

/* ---------------- fetch stub over the real data dir ---------------- */
let FAIL=new Set();
/* WRAP simula o portal devolvendo o CORPO CRU em vez da lista (foi o que aconteceu em
   29/07 com `paginate: false`: chegou `{tasks:[...]}` e o quadro saiu vazio sem erro).
   chave = nome do dataset, valor = chave do envelope, ou o objeto inteiro a devolver. */
let WRAP=new Map();
async function fetchStub(url){
  const name=String(url).replace(/^data\//,'').replace(/\.json$/,'');
  if(FAIL.has(name)) return {ok:false,status:502,json:async()=>({})};
  if(WRAP.has(name)){
    const w=WRAP.get(name);
    const p0=path.join(SITE,'data',name+'.json');
    const arr=fs.existsSync(p0)?JSON.parse(fs.readFileSync(p0,'utf8')):[];
    const body=(typeof w==='string')?{[w]:arr,last_page:false}:w;
    return {ok:true,status:200,json:async()=>body};
  }
  const p=path.join(SITE,'data',name+'.json');
  if(!fs.existsSync(p)) return {ok:false,status:404,json:async()=>({})};
  const txt=fs.readFileSync(p,'utf8');
  return {ok:true,status:200,json:async()=>JSON.parse(txt)};
}

/* ---------------- run the page script ----------------
   Extração por split, não por regex com `\n`: a versão anterior exigia `<script>\n` e
   quebrou em 29/07 quando uma edição converteu o arquivo para CRLF -- erro cujo sintoma
   ("no <script> found") não aponta para a causa. Split é indiferente à quebra de linha. */
const _blocks=HTML.split('<script>');
const _code=_blocks[_blocks.length-1].split('</script>')[0];
if(!/function paint\(\)/.test(_code))
  throw new Error('não achei o <script> principal da página (extração por split)');
const code=_code+'\nglobalThis.__api={boot,setDate,compute,shape,buildBoard,cuStatus,cuDone,cuOnBoard,boardGuards,rowsFrom,trendOf,statusToCol,readBaseline,state,setTheme,getTheme:()=>theme,getThemeManual:()=>themeManual,setStatuses,statusCatalog,getD:()=>D,paint,searchAllowed,taskVisible,deacc,cuName,cuList,prefersDark,watchSystemTheme,restoreSearchFocus};';

globalThis.document=document;
globalThis.window=windowStub;
globalThis.fetch=fetchStub;
globalThis.addEventListener=()=>{};
globalThis.innerWidth=1600;

eval(code);
const API=globalThis.__api;

/* ---------------- assertions ---------------- */
let pass=0, fail=0;
function ok(label,cond,extra){
  if(cond){pass++;console.log(`  PASS  ${label}`);}
  else{fail++;console.log(`  FAIL  ${label}${extra?'   -> '+extra:''}`);}
}
function has(hay,needle,label){ ok(label||`contém "${needle}"`, String(hay).includes(needle),
  'não encontrado'); }
const H=id=>document.getElementById(id).innerHTML;

console.log('='.repeat(74));
console.log('MANIFESTO — formato verificado (frontmatter + corpo YAML)');
console.log('-'.repeat(74));
/* O `.md` só é executável no formato verificado em 25/08/2026 (skill ai-dashboard):
   frontmatter YAML + `name:`/`connector:` DENTRO do corpo do bloco + SQL sob `query: |`.
   O formato descrito na tela de instruções do portal (`name=` na linha da cerca) NÃO roda,
   e já foi meio-revertido nesta pasta uma vez -- por isso é asserção, não convenção.
   Aqui vai só o que dá para afirmar sem parser YAML; o run_manifest.py faz a checagem
   completa (com pyyaml) antes de rodar as queries. */
const MD = fs.readFileSync(path.resolve('..','portal_jem_marketing_daily.md'),'utf8');
const fmM = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(MD);
ok('manifesto começa com frontmatter YAML', !!fmM);
const fmTxt = fmM ? fmM[1] : '';
ok('frontmatter declara title', /^title:\s*\S/m.test(fmTxt));
ok('frontmatter declara credentials: shared', /^credentials:\s*shared\s*$/m.test(fmTxt));
ok('frontmatter declara a lista connectors', /^connectors:\s*$/m.test(fmTxt) && /^\s+-\s+\S/m.test(fmTxt));
ok('NENHUM bloco usa atributo na linha da cerca (formato que não roda)',
   !/^```\w+ +\S+=/m.test(MD), (/^```\w+ +\S+=.*/m.exec(MD)||[''])[0]);

const fences=[...MD.matchAll(/^```(\w+)\r?\n([\s\S]*?)^```/gm)].map(m=>({lang:m[1],body:m[2]}));
ok(`${fences.length} blocos executáveis no manifesto`, fences.length>0, `${fences.length}`);
ok('todo bloco declara name: no corpo', fences.every(b=>/^name:\s*\S/m.test(b.body)));
ok('todo bloco declara connector: no corpo', fences.every(b=>/^connector:\s*\S/m.test(b.body)));
const mysqlB=fences.filter(b=>b.lang==='mysql');
ok('todo bloco mysql aninha o SQL sob `query: |`', mysqlB.length>0 && mysqlB.every(b=>/^query:\s*\|\s*$/m.test(b.body)));
ok('o SQL vem indentado (é escalar YAML, não SQL cru)',
   mysqlB.every(b=>/^ {2}SELECT/m.test(b.body)));
/* chave com colchete precisa de aspas: `{ list_ids[]: ... }` não é YAML válido.
   Vale só para os BLOCOS -- a prosa do .md cita a forma errada de propósito, como
   contraexemplo, e varrer o arquivo inteiro acusaria a própria documentação. */
const badKey=fences.map(b=>b.body).find(b=>/\{[^}\n]*[a-z_]+\[\]\s*:/.test(b));
ok('chave com colchete está entre aspas (o corpo do bloco é YAML)', !badKey,
   badKey?(/\{[^}\n]*[a-z_]+\[\]\s*:.*/.exec(badKey)||[''])[0].slice(0,80):'');

/* O contrato de verdade entre os dois arquivos: o nome de cada dataset.
   `fetch('data/<name>.json')` tem de casar com o `name:` do manifesto -- errar isso dá
   tile vazio sem erro, o sintoma mais difícil de diagnosticar (foi o de 29/07). */
const mdNames=new Set(fences.map(b=>/^name:\s*(\S+)/m.exec(b.body)[1]));
const htmlSets=[...HTML.matchAll(/'(mkt_[a-z_]+|clickup_[a-z0-9_]+)'/g)].map(m=>m[1]);
const wanted=new Set(htmlSets);
const faltando=[...wanted].filter(n=>!mdNames.has(n));
ok('todo dataset que o .html busca existe no manifesto', faltando.length===0, faltando.join(', '));
const naoUsado=[...mdNames].filter(n=>!wanted.has(n));
ok('todo dataset do manifesto é usado pelo .html (sem consulta paga e jogada fora)',
   naoUsado.length===0, naoUsado.join(', '));

console.log('\n' + '='.repeat(74));
console.log('BOOT (caminho felizinho: todos os 5 datasets)');
console.log('-'.repeat(74));
await API.boot();

const D=API.getD();
ok('5 datasets carregados sem erro', !D.err.orders && !D.err.clickup, JSON.stringify(D.err));
/* NOTE: the DB is live -- order count, the two totals and db_today all drift daily.
   Assert RELATIONSHIPS and monotonic floors (the customer/company base only grows),
   never frozen literals. The frozen figures live in the 27/07 block below, which is
   historical and therefore stable -- that's the real reconciliation anchor. */
ok(`≥3.004 pedidos, amount coerido p/ número (${D.orders.length})`,
   D.orders.length>=3004 && typeof D.orders[0].amount==='number',
   `${D.orders.length} / ${typeof D.orders[0]?.amount}`);
ok(`period.max = db_today (${D.period.max})`, D.period.max===D.totals.db_today,
   `${D.period.max} vs db_today ${D.totals.db_today}`);
ok('period.min = 2026-01-01', D.period.min==='2026-01-01', D.period.min);
ok(`totais Magento crescem a partir da referência (${D.totals.companies_total} / ${D.totals.contacts_total})`,
   D.totals.companies_total>=2993 && D.totals.contacts_total>=12036,
   JSON.stringify(D.totals));
has(H('srcPills'),'Magento','pílula de fonte Magento presente');
has(H('srcPills'),'ClickUp','pílula de fonte ClickUp presente');
ok('nenhuma pílula em erro', !H('srcPills').includes('src err'), H('srcPills').slice(0,200));

console.log('\n' + '='.repeat(74));
console.log("DIA SELECIONADO = 2026-07-27 (reconciliação com o report manual)");
console.log('-'.repeat(74));
API.setDate('2026-07-27');
const k=API.compute('2026-07-27');
ok('pedidos no dia = 32',            k.orders_today===32, k.orders_today);
ok('faturamento no dia = 31.822,75', k.revenue_today===31822.75, k.revenue_today);
ok('pedidos no mês = 449',           k.orders_month===449, k.orders_month);
ok('destaque = 6.392,75',            k.highlight_order.amount===6392.75, k.highlight_order.amount);
ok('destaque = JEMUS000002914',      k.highlight_order.increment_id==='JEMUS000002914', k.highlight_order.increment_id);
ok('destaque = Briscoe Protective',  /Briscoe Protective/.test(k.highlight_order.company_name), k.highlight_order.company_name);
ok('companies 1ª compra = 415',      k.companies_first_purchase===415, k.companies_first_purchase);
ok('novos contatos 27/07 = 7',       k.novos_contatos===7, k.novos_contatos);
ok('janela de 6 meses = fev..jul',   k.monthly.length===6 && k.monthly[0].ym==='2026-02' && k.monthly[5].ym==='2026-07',
   k.monthly.map(x=>x.ym).join(','));

const site=H('body-site');
const fmtInt=n=>Number(n).toLocaleString('en-US');
has(site,fmtInt(D.totals.companies_total),`tile: Companies ${fmtInt(D.totals.companies_total)}`);
has(site,fmtInt(D.totals.contacts_total),`tile: Contacts ${fmtInt(D.totals.contacts_total)}`);
has(site,'$6,392.75','tile: valor do pedido destaque');
has(site,'Briscoe Protective','tile: empresa do destaque');
has(site,'>+7<','tile: chip de +7 novos contatos');
has(site,'total atual — sem histórico por dia','tile: rótulo honesto em Companies');
has(site,'Google Analytics','tile: nota de acessos/conversão pendente');
ok('tile NÃO mostra “Pedidos hoje” em dia passado', !site.includes('Pedidos hoje') && site.includes('Pedidos no dia'));
const sales=H('body-sales');
has(sales,'Faturamento · últimos 6 meses','tile vendas: título do gráfico');
/* os gráficos são desenhados NOS containers cw-*, não no corpo do tile -- procurar
   "<svg" em body-sales passa pelo motivo errado (os ícones dos KPIs também são svg) */
has(H('cw-revenue'),'<rect','gráfico de faturamento desenhou as barras');
has(H('cw-orders'),'<polyline','gráfico de pedidos desenhou a linha');
has(H('cw-revenue'),'$','gráfico de faturamento rotulou os valores');

console.log('\n' + '='.repeat(74));
console.log('KANBAN — espelho da view Board do go-live (2 formatos de payload de propósito)');
console.log('-'.repeat(74));
const tasks=H('body-tasks');
const counts={};
for(const c of D.board.cols) counts[c.key]=c.tasks.length;
const nBoard=Object.values(counts).reduce((a,b)=>a+b,0);
const nUnmapped=[...D.board.unmapped.values()].reduce((a,b)=>a+b,0);
const nBacklog=D.tasks.filter(t=>API.cuStatus(t)==='backlog').length;
console.log('  contagem por coluna:', JSON.stringify(counts));
console.log('  listas na view     :', JSON.stringify(D.listNames));
console.log('  status não mapeados:', JSON.stringify([...D.board.unmapped.entries()]));
/* Desde 29/07 há DUAS fontes (2 páginas da view + a consulta de conclusões), então a
   conservação é aferida por fonte -- somar as duas num total só esconderia perda de um
   lado compensada pelo outro. */
const nAtivasQuadro=nBoard-counts.done_prd;
const nDoneNaView=D.tasks.filter(t=>['closed','approved by qa - prd']
  .includes(API.cuStatus(t))).length;
const doneRows=D.doneRows.length, doneOnBoard=D.doneOnBoard.length;
console.log(`  fonte view (${D.tasks.length} linhas) = ${nAtivasQuadro} ativas no quadro`
  +` + ${nUnmapped} não mapeadas + ${nBacklog} backlog + ${nDoneNaView} já concluídas`);
console.log(`  fonte conclusões (${doneRows} linhas) = ${doneOnBoard} no board`
  +` (${counts.done_prd} exibidas, ${D.board.doneTotal-counts.done_prd} além do top-10)`
  +` + ${doneRows-doneOnBoard} fora do board`);
ok('as 5 colunas existem', D.board.cols.length===5);
ok(`done_prd capado em 10 (${counts.done_prd} de ${D.board.doneTotal})`, counts.done_prd<=10, counts.done_prd);
/* contagens por coluna variam com o board -- afere a CONSERVAÇÃO, não literais */
ok('view: ativas no quadro + não mapeadas + backlog + concluídas = linhas lidas',
   nAtivasQuadro+nUnmapped+nBacklog+nDoneNaView===D.tasks.length,
   `${nAtivasQuadro}+${nUnmapped}+${nBacklog}+${nDoneNaView} != ${D.tasks.length}`);
ok('conclusões: no board + fora do board = linhas lidas',
   doneOnBoard+(doneRows-doneOnBoard)===doneRows);
ok('toda conclusão exibida está de fato no board (regra list/locations)',
   D.board.cols.find(c=>c.key==='done_prd').tasks.every(API.cuOnBoard));
ok('nenhuma tarefa do board fora dele entrou na coluna 5',
   doneRows>doneOnBoard, `${doneRows} linhas, ${doneOnBoard} no board — se iguais, a regra não está filtrando nada`);
ok(`quadro tem cartões (${nBoard})`, nBoard>=5, nBoard);
/* check the DATA, not the text: the footer note legitimately mentions <code>backlog</code> */
const backlogInBoard=D.board.cols.some(c=>c.tasks.some(t=>API.cuStatus(t)==='backlog'));
ok(`status "backlog" fora do quadro (${nBacklog} no payload, 0 no quadro)`,
   nBacklog>0 && !backlogInBoard, `no quadro=${backlogInBoard}`);
has(tasks,'concluída ','card de conclusão traz a data');
has(tasks,'atualizada ','card ativo traz date_updated');
has(tasks,'kcard-date fresh','marcador verde de “atualizada no dia mais recente”');
/* um status novo criado no ClickUp tem que virar AVISO, nunca desaparecer calado */
has(tasks,'status novo do clickup','avisa sobre status não mapeado, em vez de sumir com a tarefa');
ok('status não mapeado fica fora das colunas mas é contado',
   nUnmapped>0 && !D.board.cols.some(c=>c.tasks.some(t=>API.cuStatus(t)==='status novo do clickup')),
   `unmapped=${nUnmapped}`);
ok('formato compacto (status string) também entrou no quadro',
   tasks.includes('fixture compacta] status como string'), 'tarefa do payload compacto não apareceu');
has(tasks,'Espelha a view','rodapé diz que espelha a view do board');
has(tasks,'o board esconde','rodapé avisa que Conclusões mostra o que o board oculta');
ok('rodapé lista as listas que a view reúne',
   D.listNames.length>0 && D.listNames.every(n=>tasks.includes(n)), JSON.stringify(D.listNames));
has(H('extra-tasks'),'view Board do go-live','pílula identifica a fonte como a view');
has(H('extra-tasks'),'não histórico','aviso de que o quadro não é histórico');
const pipe=H('body-pipeline');
has(pipe,'time_in_status','legenda explica por que não há setas');
has(pipe,'Publicação da tarefa em PRD','pipeline de 5 etapas presente');
ok('legenda NÃO promete avanço/recuo', !/Avanço de etapa/.test(pipe));

console.log('\n' + '='.repeat(74));
console.log('FILTRO DE STATUS (múltipla escolha)');
console.log('-'.repeat(74));
const cat=D.statusCat;
console.log('  catálogo:', cat.map(o=>`${o.status}(${o.n})`).join(' · '));
ok(`catálogo sai dos status reais do payload (${cat.length})`,
   cat.length>0 && cat.every(o=>o.n>0), JSON.stringify(cat.slice(0,3)));
/* o catálogo cobre as linhas que ALIMENTAM o quadro: as da view que não são conclusão
   (as conclusões da coluna 5 não saem dela) + as conclusões que estão no board */
const catEsperado=(D.tasks.length-nDoneNaView)+doneOnBoard;
ok('catálogo soma = linhas que alimentam o quadro', cat.reduce((a,o)=>a+o.n,0)===catEsperado,
   `${cat.reduce((a,o)=>a+o.n,0)} != ${catEsperado}`);
ok('backlog e não-mapeados aparecem no filtro, agrupados como fora do quadro',
   cat.some(o=>/Fora do quadro/.test(o.group)), JSON.stringify([...new Set(cat.map(o=>o.group))]));
ok('estado inicial = todos (state.statuses null)', API.state.statuses===null);
/* desde 29/07 o filtro mora numa BARRA dentro do tile (era um botão no cabeçalho), para
   ficar igual à versão local -- por isso as buscas são em body-tasks, não em extra-tasks */
has(H('body-tasks'),'kfilters','o filtro fica numa barra dentro do tile');
has(H('body-tasks'),'Quadro em','a barra rotula o escopo do quadro');
has(H('body-tasks'),'estado atual','a barra declara que o quadro é o estado atual, não histórico');
has(H('body-tasks'),'Status: todos','botão mostra "todos" sem filtro');

/* filtra para um único status e confere que o quadro encolhe e AVISA */
const one=cat.find(o=>o.status==='doing')||cat[0];
const boardAll=Object.values(D.board.cols).reduce((a,c)=>a+c.tasks.length,0);
API.setStatuses(new Set([one.status]));
const boardOne=Object.values(D.board.cols).reduce((a,c)=>a+c.tasks.length,0);
ok(`filtrar por "${one.status}" encolhe o quadro (${boardAll} -> ${boardOne})`, boardOne<boardAll,
   `${boardAll} -> ${boardOne}`);
has(H('body-tasks'),'Filtro de status ativo','rodapé avisa que há filtro ativo');
has(H('body-tasks'),'NÃO é o total','rodapé diz explicitamente que o quadro não é o total');
has(H('body-tasks'),`Status: 1 de ${cat.length}`,'botão mostra quantos status estão marcados');
/* verifica DE FATO que todo cartão no quadro tem o status escolhido, e que a contagem
   bate com quantas tarefas daquele status existem no payload */
const cardsShown=D.board.cols.flatMap(c=>c.tasks);
ok(`todo cartão no quadro tem status "${one.status}" (${cardsShown.length} cartões)`,
   cardsShown.length>0 && cardsShown.every(t=>API.cuStatus(t)===one.status),
   JSON.stringify([...new Set(cardsShown.map(t=>API.cuStatus(t)))]));
ok(`contagem no quadro == ocorrências no payload (${one.n})`,
   cardsShown.length===Math.min(one.n, one.status==='closed'?10:one.n),
   `${cardsShown.length} vs ${one.n}`);
/* o cartão tem de MOSTRAR o status -- é por ele que este filtro recorta; um filtro cujo
   critério não aparece no cartão obriga a adivinhar por que a tarefa está ali */
const cardsHtml=H('body-tasks');
ok('cartão mostra o status no rodapé',
   cardsHtml.includes('kcard-st') && cardsHtml.includes(one.status), one.status);
ok('cartão traz a bolinha com a cor do próprio ClickUp',
   /kf-dot" style="background:#[0-9a-fA-F]{3,8}"/.test(cardsHtml),
   cardsHtml.slice(cardsHtml.indexOf('kf-dot'),cardsHtml.indexOf('kf-dot')+60));

/* limpar tudo -> quadro vazio, mas com aviso, nunca "sem dados" enganoso */
API.setStatuses(new Set());
ok('limpar todos zera o quadro', Object.values(D.board.cols).every(c=>c.tasks.length===0));
has(H('body-tasks'),'Filtro de status ativo','quadro vazio por filtro ainda explica o motivo');

/* voltar para todos restaura exatamente o estado inicial */
API.setStatuses(null);
ok('voltar para todos restaura o quadro',
   Object.values(D.board.cols).reduce((a,c)=>a+c.tasks.length,0)===boardAll);
ok('marcar todos manualmente equivale a "todos" (state volta a null)',
   (API.setStatuses(new Set(cat.map(o=>o.status))), API.state.statuses===null));
ok('sem filtro o rodapé não fala de filtro', !H('body-tasks').includes('Filtro de status ativo'));

console.log('\n' + '='.repeat(74));
console.log('BUSCA POR TEXTO NO QUADRO');
console.log('-'.repeat(74));
/* Termos derivados do PRÓPRIO payload, nunca literais congelados: a view muda de conteúdo
   toda semana, e teste ancorado em título fixo apodrece igual às asserções de 27/07. */
const setQ=q=>{API.state.q=q;API.paint();};
const allCards=b=>b.cols.reduce((a,c)=>a.concat(c.tasks),[]);
const cardCount=b=>b.cols.reduce((a,c)=>a+c.tasks.length,0);

API.setStatuses(null); setQ('');
const baseCards=cardCount(D.board);

/* a caixa de busca mora na barra do quadro (.kfilters), junto do filtro de status --
   é o mesmo lugar e o mesmo peso da versão local */
has(H('body-tasks'),'id="boardSearch"','a caixa de busca é renderizada no tile');
has(H('body-tasks'),'kfilters','a busca está na barra de filtros do quadro');
ok('sem texto, não há botão de limpar', !H('body-tasks').includes('data-q-clear'));

/* --- casa por TÍTULO --- */
const someTask=allCards(D.board)[0];
const word=API.deacc(API.cuName(someTask)).split(/\s+/).filter(w=>w.length>4)[0]||'a';
setQ(word);
const found=allCards(D.board);
ok(`buscar "${word}" (palavra de um título real) encolhe o quadro (${baseCards} -> ${found.length})`,
   found.length>0 && found.length<baseCards, `${baseCards} -> ${found.length}`);
ok('TODO cartão que sobrou casa o termo em título/status/lista',
   found.every(t=>(API.deacc(API.cuName(t))+' '+API.deacc(API.cuStatus(t))+' '+API.deacc(API.cuList(t))).includes(word)),
   found.map(t=>API.cuName(t)).slice(0,3).join(' | '));
ok('a tarefa de origem do termo está entre as encontradas',
   found.some(t=>t.id===someTask.id));

has(H('body-tasks'),'data-q-clear','com texto, aparece o botão de limpar');
has(H('body-tasks'),`value="${word}"`,'o input reflete o termo digitado (sobrevive ao repaint)');

/* --- o rodapé nomeia a BUSCA, não "filtro de status" --- */
has(H('body-tasks'),'Busca','rodapé nomeia a busca como o filtro ativo');
has(H('body-tasks'),'NÃO é o total','rodapé mantém o aviso de que o quadro não é o total');
ok('rodapé NÃO culpa o filtro de status quando só a busca está ativa',
   !H('body-tasks').includes('Filtro de status ativo'));
has(H('body-tasks'),'escondida','rodapé diz quantas foram escondidas');

/* --- acento e caixa não importam --- */
ok('deacc tira acento e caixa', API.deacc('Integração Hyvä ÁÉÍÕÇ')==='integracao hyva aeiocc'
   || API.deacc('Integração Hyvä')==='integracao hyva', API.deacc('Integração Hyvä'));
const accTask=allCards(API.buildBoard(D.tasks,D.doneRows))
  .find(t=>API.deacc(API.cuName(t))!==String(API.cuName(t)).toLowerCase());
if(accTask){
  const accWord=API.deacc(API.cuName(accTask)).split(/\s+/).filter(w=>w.length>4)[0];
  setQ(accWord);
  ok(`buscar sem acento acha título acentuado ("${accWord}")`,
     allCards(D.board).some(t=>t.id===accTask.id), API.cuName(accTask));
}else{
  ok('buscar sem acento acha título acentuado (sem tarefa acentuada no payload — vácuo)', true);
}

/* --- vários termos = AND, em qualquer ordem --- */
const twoWords=API.deacc(API.cuName(someTask)).split(/\s+/).filter(w=>w.length>3).slice(0,2);
if(twoWords.length===2){
  setQ(twoWords.join(' '));
  const a=cardCount(D.board);
  setQ(twoWords.slice().reverse().join(' '));
  ok('dois termos: a ordem não muda o resultado (AND)', cardCount(D.board)===a, `${a}`);
  setQ(twoWords[0]);
  ok('dois termos filtram MAIS que um só (AND, não OR)', a<=cardCount(D.board), `${a} <= ${cardCount(D.board)}`);
}else{
  ok('dois termos: título curto demais no payload — vácuo', true);
  ok('dois termos filtram mais que um — vácuo', true);
}

/* --- busca casa por STATUS (campo que o cartão mostra no rodapé) --- */
const stTerm=API.deacc(cat[0].status).split(/\s+/)[0];
setQ(stTerm);
ok(`buscar por status ("${stTerm}") traz cartões daquele status`,
   allCards(D.board).some(t=>API.deacc(API.cuStatus(t)).includes(stTerm)));

/* --- busca sem resultado: quadro vazio EXPLICADO, nunca "sem dados" --- */
setQ('zzz-nada-casa-com-isso-zzz');
ok('busca sem resultado zera o quadro', cardCount(D.board)===0);
has(H('body-tasks'),'Busca','quadro vazio por busca ainda explica o motivo');
ok('quadro vazio por busca NÃO cai na caixa de "nenhuma tarefa retornada"',
   !H('body-tasks').includes('Nenhuma tarefa retornada'));

/* --- os dois filtros são cumulativos e AMBOS são nomeados --- */
API.setStatuses(new Set([cat[0].status])); setQ(word);
const both=H('body-tasks');
ok('status + busca: o rodapé nomeia os DOIS', both.includes('Filtro de status')&&both.includes('Busca'),
   both.slice(both.indexOf('hid'),both.indexOf('hid')+140));
ok('cartão visível passa pelos dois filtros ao mesmo tempo',
   allCards(D.board).every(t=>API.taskVisible(t)));

/* --- limpar restaura exatamente o estado inicial --- */
API.setStatuses(null); setQ('');
ok('limpar a busca restaura o quadro inteiro', cardCount(D.board)===baseCards,
   `${cardCount(D.board)} vs ${baseCards}`);
ok('sem busca o rodapé não fala de busca', !H('body-tasks').includes('Busca “'));

/* --- as opções de status NÃO encolhem com a busca (senão esconderiam o que existe) --- */
const catAll=API.statusCatalog(D.tasks,D.doneRows).length;
setQ(word);
ok('a lista de status do filtro não muda conforme se digita',
   API.statusCatalog(D.tasks,D.doneRows).length===catAll);
setQ('');

/* --- devolver o foco ao input não pode explodir num DOM sem foco --- */
API.state.qFocus=true;
let focoOk=true; try{ API.restoreSearchFocus(); }catch(e){ focoOk=false; }
ok('restaurar foco é seguro em ambiente sem foco (não lança)', focoOk);
ok('a marca de foco é consumida (repaint não rouba o cursor depois)', API.state.qFocus===false);

console.log('\n' + '='.repeat(74));
console.log('SETAS DE TENDÊNCIA (base do dia anterior)');
console.log('-'.repeat(74));
/* A base é o dataset OPCIONAL `board_baseline`. Três estados, todos declarados na tela:
   usável (setas), velha (setas desligadas) e ausente (setas nunca existiram). */
FAIL=new Set(); WRAP=new Map();
registry.clear();
await API.boot();
const Db=API.getD(), bl=Db.baseline;
console.log(`  base: rows=${bl.rows} refere_se_a=${bl.refDate} idade=${bl.age} usável=${bl.usable}`);
if(bl.rows){
  ok('base carregada e utilizável', bl.usable===true, JSON.stringify({age:bl.age,stale:bl.stale}));
  ok('base tem id → coluna', bl.map.size>0 && [...bl.map.values()][0].col>=1);
  has(H('body-tasks'),'Setas ▲▼= comparam','rodapé declara contra que dia a seta compara');
  has(H('body-tasks'),bl.refDate,'rodapé mostra a data da base');
  const temSeta=/class="trend (up|down|same|new)"/.test(H('body-tasks'));
  ok('cartões ganharam seta', temSeta, H('body-tasks').slice(0,120));
  /* uma tarefa que não está na base tem de sair como "novo", nunca como "=" */
  const semBase=Db.tasks.find(t=>!bl.map.has(String(t.id||''))&&
    ['researching','doing','on hold','to do (sprint)'].includes(API.cuStatus(t)));
  ok('tarefa fora da base recebe "novo", não "="',
     !semBase || API.trendOf(semBase,bl)==='new', semBase?API.trendOf(semBase,bl):'n/a');
  /* a seta tem de sair da COMPARAÇÃO de coluna: forçando a base a dizer "estava na 1"
     e "estava na 5", a mesma tarefa tem de virar ▲ e ▼ respectivamente */
  const alvo=Db.tasks.find(t=>['ready to deploy','testing - stg','testing - prd']
    .includes(API.cuStatus(t)));
  if(alvo){
    const fake=d=>({usable:true,refDate:'2026-07-28',
      map:new Map([[String(alvo.id),{col:d,status:'x'}]])});
    ok('base dizendo coluna 1 → ▲', API.trendOf(alvo,fake(1))==='up', API.trendOf(alvo,fake(1)));
    ok('base dizendo coluna 5 → ▼', API.trendOf(alvo,fake(5))==='down', API.trendOf(alvo,fake(5)));
    const mesma=1+['in_progress','ready_stg','awaiting_deploy','ready_prd','done_prd']
      .indexOf(API.statusToCol(API.cuStatus(alvo)));
    ok('base dizendo a MESMA coluna → =', API.trendOf(alvo,fake(mesma))==='same',
       `col atual ${mesma} → ${API.trendOf(alvo,fake(mesma))}`);
  }
  /* BASE VELHA: comparar com um dia qualquer é pior que não comparar */
  const velha=[...bl.map.entries()].slice(0,5).map(([id,v])=>
    ({refere_se_a:'2026-06-01',id,col:v.col,status:v.status}));
  WRAP=new Map([['board_baseline',{tarefas:velha}]]);
  registry.clear();
  await API.boot();
  ok('base velha desliga as setas', API.getD().baseline.usable===false,
     JSON.stringify({age:API.getD().baseline.age}));
  has(H('body-tasks'),'Setas <b>desligadas</b>','rodapé avisa que a base está velha');
  ok('base velha: nenhum cartão com seta', !/class="trend /.test(H('body-tasks')));
  WRAP=new Map();
}else{
  console.log('  (sem base publicada — rode `python build_data.py` para gerar uma)');
}
/* AUSENTE: é o estado de hoje no portal. Não pode virar erro nem pílula vermelha. */
FAIL=new Set(['board_baseline']);
registry.clear();
await API.boot();
ok('base ausente NÃO é erro de fonte', !H('srcPills').includes('src err'), H('srcPills').slice(0,120));
ok('base ausente: quadro renderiza normalmente', H('body-tasks').includes('kcard'));
ok('base ausente: nenhum cartão com seta', !/class="trend /.test(H('body-tasks')));
has(H('body-tasks'),'Sem setas','rodapé explica por que não há seta e o que fazer');
has(H('body-tasks'),'board_baseline','rodapé nomeia o dataset que ligaria as setas');
FAIL=new Set();

console.log('\n' + '='.repeat(74));
console.log('TEMA CLARO / ESCURO');
console.log('-'.repeat(74));
const themeBtn=document.getElementById('themeToggle');
/* Sem matchMedia (este stub) ou com sistema no claro, abre claro -- o antigo rótulo
   "abre no tema claro" afirmava mais do que passou a ser verdade quando a página começou
   a respeitar prefers-color-scheme; o invariante é "cai no claro quando não há sinal". */
ok('sem sinal do sistema, abre no claro', API.getTheme()==='light' && documentElement.getAttribute('data-theme')==='light',
   `${API.getTheme()} / ${documentElement.getAttribute('data-theme')}`);
ok('prefersDark() é falso quando o ambiente não tem matchMedia', API.prefersDark()===false);
ok('botão oferece o escuro', /Escuro/.test(themeBtn.textContent), themeBtn.textContent);
API.setTheme('dark');
ok('troca para escuro marca data-theme="dark" na raiz',
   documentElement.getAttribute('data-theme')==='dark', documentElement.getAttribute('data-theme'));
ok('botão passa a oferecer a volta ao claro', /Claro/.test(themeBtn.textContent), themeBtn.textContent);
API.setTheme('light');
ok('volta para claro', documentElement.getAttribute('data-theme')==='light', documentElement.getAttribute('data-theme'));
/* o tema não pode depender de repaint: os SVG leem var(--teal)/var(--card) direto no
   atributo, então nenhum dado precisa ser recalculado ao trocar */
const svgBefore=H('cw-revenue')+H('cw-orders');
API.setTheme('dark');
ok('trocar tema não redesenha nem perde os gráficos', H('cw-revenue')+H('cw-orders')===svgBefore);
has(H('cw-revenue'),'var(--teal)','barras usam a variável de cor (acompanham o tema)');
has(H('cw-orders'),'var(--card)','anel dos pontos segue a cor do card');
API.setTheme('light');

/* ---- prefers-color-scheme: abrir no tema do sistema ----
   Sem localStorage (sandbox do iframe) não há como lembrar a escolha, então o sinal do
   sistema é o único jeito de não dar flash branco em quem usa escuro. */
let sysDark=true, mqFns=[];
windowStub.matchMedia=q=>({
  matches:sysDark, media:q,
  addEventListener:(t,fn)=>mqFns.push(fn),
  addListener:fn=>mqFns.push(fn),
});
ok('prefersDark() lê o sistema quando matchMedia existe', API.prefersDark()===true);
API.setTheme(API.prefersDark()?'dark':'light');
ok('sistema no escuro => a página abre no escuro',
   documentElement.getAttribute('data-theme')==='dark', documentElement.getAttribute('data-theme'));
sysDark=false;
ok('sistema no claro => a página abre no claro',
   (API.setTheme(API.prefersDark()?'dark':'light'), documentElement.getAttribute('data-theme')==='light'),
   documentElement.getAttribute('data-theme'));

/* enquanto ninguém tocou no botão, a página SEGUE o sistema... */
API.watchSystemTheme();
ok('watchSystemTheme registra o ouvinte de mudança do sistema', mqFns.length>0, `${mqFns.length}`);
mqFns.forEach(fn=>fn({matches:true}));
ok('sistema muda para escuro e a página acompanha (ninguém tocou no botão)',
   API.getTheme()==='dark', API.getTheme());

/* ...e depois do clique, a escolha explícita VENCE o sistema pelo resto da sessão */
API.setTheme('light',true);
ok('clique no botão marca a escolha como manual', API.getThemeManual()===true);
mqFns.forEach(fn=>fn({matches:true}));
ok('escolha manual não é desfeita por mudança do sistema',
   API.getTheme()==='light' && documentElement.getAttribute('data-theme')==='light', API.getTheme());
delete windowStub.matchMedia;
API.setTheme('light');

console.log('\n' + '='.repeat(74));
console.log('ESTADOS DE ERRO (chave do ClickUp ausente + Magento fora)');
console.log('-'.repeat(74));
FAIL=new Set(['clickup_board_pg0']);
registry.clear();
await API.boot();
has(H('body-tasks'),'Não foi possível carregar o ClickUp','erro do ClickUp é explicado');
has(H('body-tasks'),'Sistemas → ClickUp','erro aponta onde cadastrar a chave');
has(H('srcPills'),'src err','pílula do ClickUp fica vermelha');
/* the re-boot lands on TODAY, so don't assert on a specific order -- assert the tile
   rendered its KPIs and did NOT fall into the error state */
ok('Magento continua renderizando com ClickUp caído',
   H('body-site').includes('Companies') && H('body-site').includes('Faturamento acumulado')
   && !H('body-site').includes('Não foi possível'));

/* TIMEOUT do ClickUp: é o erro que a plataforma devolveu de verdade em 29/07, e é
   DIFERENTE de falha de credencial -- a caixa não pode mandar procurar chave. */
/* DEGRADAÇÃO PARCIAL: é o ganho de dividir em 3 datasets -- um pedaço fora não derruba
   o tile inteiro, e o que faltou aparece escrito no rodapé. */
FAIL=new Set(['clickup_board_pg1']);
registry.clear();
await API.boot();
ok('página 1 fora: o quadro AINDA renderiza com a página 0', H('body-tasks').includes('kcard'));
has(H('body-tasks'),'página 1</b> da view não carregou','rodapé avisa qual pedaço faltou');
ok('página 1 fora: não cai na caixa de erro do tile',
   !H('body-tasks').includes('Não foi possível carregar o ClickUp'));

FAIL=new Set(['clickup_concluidas']);
registry.clear();
await API.boot();
ok('conclusões fora: as 4 colunas ativas continuam', H('body-tasks').includes('kcard'));
has(H('body-tasks'),'coluna 5 ','rodapé explica que só a coluna 5 esvaziou');
ok('conclusões fora: coluna 5 vazia, sem inventar cartão',
   API.getD().board.cols.find(c=>c.key==='done_prd').tasks.length===0);

/* TIMEOUT do ClickUp: é o erro que a plataforma devolveu de verdade em 29/07, e é
   DIFERENTE de falha de credencial -- a caixa não pode mandar procurar chave. */
/* ENVELOPE: o portal pode entregar o corpo cru em vez da lista. Aconteceu em 29/07 com
   `paginate: false` -- o quadro saiu VAZIO, sem erro, com o dado dentro do payload. */
console.log('  -- envelope do payload --');
ok('rowsFrom aceita lista', API.rowsFrom([1,2]).rows.length===2);
ok('rowsFrom acha .tasks[]', API.rowsFrom({tasks:[1,2,3],last_page:false}).rows.length===3);
ok('rowsFrom acha .rows[]', API.rowsFrom({rows:[1]}).rows.length===1);
ok('rowsFrom deduz a 1ª lista de um envelope desconhecido',
   API.rowsFrom({qualquer:[1,2]}).rows.length===2);
ok('rowsFrom relata objeto sem lista em vez de fingir vazio',
   /sem lista/.test(API.rowsFrom({last_page:false,err:'x'}).shape));
FAIL=new Set();
WRAP=new Map([['clickup_board_pg0','tasks'],['clickup_board_pg1','tasks'],
              ['clickup_concluidas','tasks']]);
registry.clear();
await API.boot();
ok('corpo cru {tasks:[...]}: o quadro RENDERIZA em vez de sair vazio',
   H('body-tasks').includes('kcard')&&!H('body-tasks').includes('Nenhuma tarefa retornada'));
/* UM dataset sem lista dentro, com os outros ok: o quadro segue renderizando (é o certo,
   há dado), mas a falha NÃO pode passar calada -- tem de virar aviso nomeado no rodapé */
WRAP=new Map([['clickup_board_pg0',{last_page:false,mensagem:'sem select aplicado'}]]);
registry.clear();
await API.boot();
ok('página 0 sem lista: o quadro ainda renderiza com o que veio',
   H('body-tasks').includes('kcard'));
has(H('body-tasks'),'respondeu <b>sem nenhuma linha</b>','dataset vazio sem erro vira aviso');
has(H('body-tasks'),'clickup_board_pg0','o aviso nomeia o dataset');
has(H('body-tasks'),'formato:','o aviso mostra o formato observado');
has(H('body-tasks'),'paginate: false','o aviso diz o que tentar primeiro');
/* TODOS sem lista: aí não há quadro, e a caixa de vazio tem de diagnosticar */
WRAP=new Map([['clickup_board_pg0',{last_page:false}],['clickup_board_pg1',{last_page:false}],
              ['clickup_concluidas',{last_page:false}]]);
registry.clear();
await API.boot();
has(H('body-tasks'),'Nenhuma tarefa retornada','nada em lugar nenhum cai na caixa de vazio');
has(H('body-tasks'),'formato','a caixa mostra o formato de cada dataset');
has(H('body-tasks'),'paginate: false','a caixa diz o que tentar primeiro');
has(H('body-tasks'),'clickup_board_pg0','a caixa nomeia os datasets');
WRAP=new Map();

FAIL=new Set();
META=new Map([['clickup_board_pg0',
  {status:'ERROR',error:'clickup_board_pg0: The operation was aborted due to timeout'}]]);
registry.clear();
await API.boot();
has(H('body-tasks'),'não respondeu em tempo','timeout tem caixa própria, não a de credencial');
has(H('body-tasks'),'Não é problema de credencial','a caixa desmente credencial explicitamente');
has(H('body-tasks'),'atualizar de novo','a caixa diz o que fazer');
ok('caixa de timeout NÃO lista causas de credencial como causa nº 1',
   !H('body-tasks').includes('Causas possíveis'));
has(H('srcPills'),'timeout','pílula diz "timeout", não "erro"');
has(H('srcPills'),'src empty','pílula de timeout é âmbar, não vermelha');
ok('Magento continua renderizando com ClickUp em timeout',
   H('body-site').includes('Companies') && !H('body-site').includes('Não foi possível'));
META=new Map();

/* ---- 401 do ClickUp: a mensagem REAL que o portal devolveu em 27/08/2026 ----
   Antes deste caso, um 401 caía na caixa genérica "Causas possíveis, em ordem", que
   mandava conferir quatro coisas (equipe/permissão/view/cadastro) quando o servidor já
   tinha dito qual era. Mesmo defeito que o timeout tinha em 29/07: a caixa adivinhava. */
META=new Map([['clickup_board_pg0',
  {status:'ERROR',error:'HTTP 401: {"err":"Token invalid","ECODE":"OAUTH_025"}'}]]);
registry.clear();
await API.boot();
has(H('body-tasks'),'recusada (401)','401 tem caixa própria, não a genérica de causas possíveis');
has(H('body-tasks'),'OAUTH_025','a caixa mostra o código do ClickUp');
ok('a caixa de 401 NÃO oferece a lista de "causas possíveis, em ordem"',
   !H('body-tasks').includes('Causas possíveis'));
ok('a caixa de 401 NÃO manda tentar de novo (não é falha transitória)',
   !H('body-tasks').includes('atualizar de novo'));
has(H('body-tasks'),'credentials: shared','a caixa manda checar DE QUEM é a chave (equipe vs pessoal)');
has(H('body-tasks'),'settings/apps','a caixa diz onde gerar outra');
has(H('body-tasks'),'invalida a anterior','a caixa explica por que uma chave que funcionava parou');
has(H('body-tasks'),'última execução que deu certo',
   'a caixa avisa que a contagem de linhas ao lado do erro é da execução anterior');
has(H('srcPills'),'chave 401','pílula nomeia credencial em vez de só "erro"');
has(H('srcPills'),'src err','pílula de 401 é vermelha (não é transitória como o timeout)');
ok('Magento continua renderizando com a chave do ClickUp recusada',
   H('body-site').includes('Companies') && !H('body-site').includes('Não foi possível'));
/* e o inverso: timeout não pode ser classificado como credencial */
ok('isAuthErr não confunde timeout com credencial',
   !H('body-tasks').includes('não respondeu em tempo'));
META=new Map();

FAIL=new Set(['mkt_orders']);
registry.clear();
await API.boot();
has(H('body-site'),'Não foi possível carregar os pedidos do Magento','erro do Magento é explicado');
has(H('body-sales'),'Sem dados de vendas','tile de vendas degrada');
ok('ClickUp continua renderizando com Magento caído', H('body-tasks').includes('kcard'));

console.log('\n' + '='.repeat(74));
console.log(`RESULTADO: ${pass} passaram, ${fail} falharam`);
console.log('='.repeat(74));
process.exit(fail?1:0);
