/* Testa os filtros do quadro do ClickUp no dashboard.html LOCAL.
 *
 *     node board_test.mjs            (rode `python build_data.py` antes)
 *
 * Extrai o <script> da própria página, roda contra um DOM stub e o `data.json` REAL, e
 * confere: (1) que a remontagem do quadro em JS reproduz exatamente o que o
 * `build_data.py` calculou para hoje -- mesmas colunas e as MESMAS setas, tarefa por
 * tarefa, comparadas contra o `trend_today` que o servidor gravou; (2) a reconstrução de
 * datas passadas contra o histórico cru; (3) a marcação "?" das trilhas com visita
 * escondida; (4) o filtro de status; (5) os limites do seletor de data.
 *
 * Nem tudo aqui é literal fixo: o quadro muda todo dia. Só valem como número fixo os
 * fatos de 27/07 (dia do report de referência, já passado e conferido à mão); o resto é
 * asserção de RELAÇÃO (a tela == o servidor, as contas fecham em 169, etc.), que continua
 * valendo amanhã. Não troque isso por contagens do dia -- elas se auto-quebram em horas.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const DIR = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(DIR, 'dashboard.html'), 'utf8');
const DATA = JSON.parse(fs.readFileSync(path.join(DIR, 'data.json'), 'utf8'));

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
    this.tagName=tag;this.innerHTML='';this.textContent='';this.value='';this.min='';this.max='';
    this.hidden=false;this.style={};this.dataset={};this.classList=new ClassList();this.children=[];
    this._listeners={};
    if(tag==='template'){const self=this;
      this.content={get firstChild(){const e=new El('section');
        const m=/data-tile="([^"]+)"/.exec(self.innerHTML);if(m)e.dataset.tile=m[1];return e;}};}
  }
  appendChild(c){this.children.push(c);return c;}
  insertBefore(){}
  setAttribute(k,v){(this._attrs=this._attrs||{})[k]=v;}
  getAttribute(k){return (this._attrs||{})[k]??null;}
  querySelectorAll(){return [];}
  querySelector(){return null;}
  closest(){return null;}
  matches(){return false;}
  addEventListener(t,fn){(this._listeners[t]=this._listeners[t]||[]).push(fn);}
  getBoundingClientRect(){return{left:0,top:0,width:200,height:100};}
}
const registry=new Map();
const document={
  readyState:'complete',documentElement:new El('html'),
  getElementById(id){if(!registry.has(id))registry.set(id,new El('div'));return registry.get(id);},
  createElement(tag){return new El(tag);},
  addEventListener(){},
};
globalThis.document=document;
globalThis.window={innerWidth:1600,addEventListener(){},DASHBOARD_DATA:DATA};
const LS=new Map();
globalThis.localStorage={getItem:k=>LS.has(k)?LS.get(k):null,
  setItem:(k,v)=>LS.set(k,String(v)),removeItem:k=>LS.delete(k)};
globalThis.history={replaceState(){}};
globalThis.location={search:'',pathname:'/dashboard.html'};
globalThis.addEventListener=()=>{};
globalThis.innerWidth=1600;
globalThis.setInterval=()=>0;
globalThis.fetch=async()=>({ok:true,status:200,json:async()=>DATA});

/* o último <script> sem atributos é o da página (há outro no <head>, que só aplica o
   tema salvo, e o <script src="data.js">) -- por isso split, não regex guloso */
const blocks=HTML.split('<script>');
const code=blocks[blocks.length-1].split('</script>')[0];
if(!/function paint\(\)/.test(code)) throw new Error('não achei o <script> principal da página');
eval(code+`
globalThis.__api={computeBoard,setBoardDate,setStatuses,setDate,setTheme,currentTheme,
  getBOARD:()=>BOARD,board,state,getD:()=>D,phxDayEnd,statusAtRows,renderBoard,esc,
  setHours,STALE_WARN,STALE_BAD};`);
await new Promise(r=>setTimeout(r,50));
const A=globalThis.__api, B=A.getBOARD(), D=A.getD(), T=D.tasks;

let pass=0,fail=0;
const ok=(l,c,x)=>{c?(pass++,console.log('  PASS  '+l)):(fail++,console.log('  FAIL  '+l+(x?'   -> '+x:'')));};
const counts=b=>B.defs.map(d=>(b.byCol.get(d.key)||[]).length);

console.log('\n=== modelo ===');
ok('modo ao vivo (items + histórico presentes)',B.live===true);
ok(`items == tarefas da view (${T.items.length})`,
   T.items.length===T.stats.tasks_in_view,`${T.items.length} vs ${T.stats.tasks_in_view}`);
ok(`janela de reconstrução declarada (${B.minDate} .. ${B.maxDate})`,
   !!B.minDate&&B.minDate<B.maxDate);
const withHist=T.items.filter(i=>i.hist);
ok('histórico só para quem precisa (ativas + concluídas na janela)',
   withHist.length===T.stats.history_calls,`${withHist.length} vs ${T.stats.history_calls}`);
ok('todo histórico veio ordenado por tempo',
   withHist.every(i=>i.hist.every((r,k)=>k===0||r.ms>=i.hist[k-1].ms)));

console.log('\n=== HOJE: a tela reproduz o quadro que o build_data.py montou ===');
const today=A.computeBoard(T.as_of);
// esperado = a classificação que o SERVIDOR gravou em cada item (coluna 5 limitada ao top N)
const serverCounts=B.defs.map(d=>{
  const n=T.items.filter(i=>i.column===d.key).length;
  return d.key===B.doneKey?Math.min(n,B.topN):n;});
console.log('    colunas hoje:',counts(today).join(' / '));
ok('colunas iguais às do servidor',
   JSON.stringify(counts(today))===JSON.stringify(serverCounts),
   `tela ${JSON.stringify(counts(today))} vs servidor ${JSON.stringify(serverCounts)}`);
// coluna de hoje, por tarefa, tem de bater com o `column` que o servidor gravou
const posToday=new Map();
for(const d of B.defs)for(const c of today.byCol.get(d.key)||[])posToday.set(c.title,d.key);
const colMismatch=T.items.filter(i=>i.column&&i.column!==B.doneKey&&posToday.get(i.title)!==i.column);
ok('cada tarefa ativa caiu na coluna que o servidor calculou',colMismatch.length===0,
   colMismatch.slice(0,3).map(i=>i.title).join(' | '));
// setas: comparar com trend_today (calculado no servidor, com o mesmo corte)
const cardTrend=new Map();
for(const d of B.defs)for(const c of today.byCol.get(d.key)||[])cardTrend.set(c.title,c.trend);
const trendRows=T.items.filter(i=>i.trend_today!==undefined);
const trendBad=trendRows.filter(i=>cardTrend.get(i.title)!==i.trend_today);
ok(`setas idênticas às do servidor nas ${trendRows.length} tarefas ativas`,trendBad.length===0,
   trendBad.slice(0,3).map(i=>`${i.title}: tela=${cardTrend.get(i.title)} servidor=${i.trend_today}`).join(' | '));
ok('nenhuma tarefa sem status conhecido hoje',today.unknown===0,today.unknown);
/* Nenhuma tarefa pode sumir sem explicação: ou está no quadro, ou está fora por status
   não mapeado, ou não tinha status conhecido naquela data. */
const soma=b=>b.shown+b.unknown+[...b.off.values()].reduce((a,x)=>a+x,0);
ok(`quadro + fora-do-mapa + desconhecidas = ${T.items.length} (hoje)`,
   soma(today)===T.items.length,soma(today));

console.log('\n=== DATA PASSADA: 27/07, o dia do report de referência ===');
const d27=A.computeBoard('2026-07-27');
console.log('    colunas em 27/07:',counts(d27).join(' / '),
            ' | fora:',[...d27.off].map(([s,n])=>s+'='+n).join(',')||'-',
            ' | sem status:',d27.unknown);
const find=(b,frag)=>{for(const d of B.defs)for(const c of b.byCol.get(d.key)||[])
  if(c.title.toLowerCase().includes(frag))return{col:d.key,...c};return null;};
/* Os fatos de 27/07 só valem enquanto a tarefa continuar na view do go-live -- se o time
   tirar de lá, o certo é PULAR, não falhar: a view é deles, não deste dashboard. */
const inView=frag=>T.items.some(i=>i.title.toLowerCase().includes(frag));
const skip=(l,r)=>console.log(`  SKIP  ${l}   -> ${r}`);
const okIfInView=(frag,label,cond,extra)=>inView(frag)
  ? ok(label,cond,extra) : skip(label,`"${frag}" não está mais na view`);
const bulk=find(d27,'bulk pack');
okIfInView('bulk pack','Bulk Pack está em "aguardando deploy" em 27/07',
   bulk&&bulk.col==='awaiting_deploy',bulk?bulk.col:'não encontrada');
okIfInView('bulk pack','Bulk Pack com seta ▲ em 27/07 (era fail - stg no fechamento de 26/07)',
   bulk&&bulk.trend==='up',bulk?`${bulk.trend} (status ${bulk.status})`:'-');
okIfInView('bulk pack','Bulk Pack com status `ready to deploy` em 27/07',
   bulk&&bulk.status==='ready to deploy',bulk&&bulk.status);
okIfInView('bulk pack','Bulk Pack NÃO é marcada como incerta em 27/07 (trilha completa a partir de 27/07 15:51)',
   bulk&&!bulk.unsure,bulk&&bulk.unsure);
const fb=find(d27,'fallback and notification');
console.log('    Fallback and Notification em 27/07:',fb?`${fb.col} / ${fb.status} / ${fb.trend} / incerta=${fb.unsure}`:'ausente');
okIfInView('fallback and notification',
   'Fallback and Notification em `ready for testing - prd` no fechamento de 27/07 (bate com o registro do dia 28)',
   fb&&fb.status==='ready for testing - prd',fb&&fb.status);
const dash=find(d27,'dashboard credit limit');
console.log('    Dashboard Credit Limit em 27/07 :',dash?`${dash.col} / ${dash.status} / ${dash.trend} / incerta=${dash.unsure}`:'ausente');
// caso conhecido: em 28/07 ela foi reaberta e reaprovada, então o `since` da aprovação
// aponta para a 2a vez e a reconstrução de 27/07 erraria. Tem de sair marcada.
okIfInView('dashboard credit limit',
   'Dashboard Credit Limit sai marcada como INCERTA em 27/07 (visita escondida detectada)',
   dash&&dash.unsure===true,dash?`unsure=${dash.unsure} col=${dash.col}`:'ausente');
okIfInView('dashboard credit limit','cartão incerto não recebe seta',
   !dash||dash.trend===null,dash&&dash.trend);
ok('hoje ninguém é marcado como incerto',today.unsure===0,today.unsure);
console.log('    incertas em 27/07:',d27.unsure,'| em 15/06:',A.computeBoard('2026-06-15').unsure,
            '| total com visita escondida:',T.stats.tasks_with_hidden_visits);
ok('em 27/07 existem tarefas sem status conhecido (criadas depois) OU zero, mas nunca negativo',
   d27.unknown>=0);
ok(`27/07: quadro + fora + desconhecidas = ${T.items.length}`,soma(d27)===T.items.length,soma(d27));
ok('27/07 não mostra conclusões posteriores a 27/07',
   (d27.byCol.get(B.doneKey)||[]).every(c=>c.since<=A.phxDayEnd('2026-07-27')));
ok('27/07: concluídas contadas são menos que hoje',d27.doneTotal<today.doneTotal,
   `${d27.doneTotal} vs ${today.doneTotal}`);

console.log('\n=== reconstrução vs. história crua (amostra independente) ===');
// para 3 tarefas com histórico, conferir a coluna em 3 datas contra o cálculo direto
let sampleBad=0;
for(const it of withHist.slice(0,40)){
  for(const dstr of ['2026-07-27','2026-07-10','2026-06-15']){
    const end=A.phxDayEnd(dstr);
    const direto=it.hist.filter(r=>r.ms<=end).sort((a,b)=>b.ms-a.ms)[0];
    const b=A.computeBoard(dstr);
    let achou=null;
    for(const d of B.defs)for(const c of b.byCol.get(d.key)||[])if(c.title===it.title)achou=c;
    const esperado=direto?(T.statuses[direto.s]||{}).col:null;
    const obtido=achou?achou.col:null;
    // a coluna 5 mostra só as 10 conclusões mais recentes: ausência é esperada além disso
    const capDone=esperado===B.doneKey&&obtido===null&&b.doneTotal>=B.topN;
    if(esperado!==obtido&&!capDone){sampleBad++;console.log('    !!',dstr,it.title,esperado,obtido);}
  }
}
ok('40 tarefas × 3 datas: coluna == status com o maior `since` <= 23:59 daquele dia',sampleBad===0,sampleBad);

console.log('\n=== filtro de status ===');
// status ativo mais numeroso de hoje -- escolhido dos dados, não fixado (o quadro muda)
const st1=[...today.counts].filter(([s])=>B.statusCol[s]!==B.doneKey)
  .sort((a,b)=>b[1]-a[1])[0][0];
A.setStatuses(new Set([st1]));
const f=A.computeBoard(T.as_of);
const all=[...f.byCol.values()].flat();
ok(`só cartões do status escolhido (\`${st1}\`)`,all.every(c=>c.status===st1)&&all.length>0,all.length);
ok('exibidas == contagem daquele status no quadro cheio',all.length===today.counts.get(st1),
   `${all.length} vs ${today.counts.get(st1)}`);
ok('ocultas + exibidas = quadro cheio',f.hidden+all.length===today.shown,
   `${f.hidden}+${all.length} vs ${today.shown}`);
ok('opções do filtro continuam mostrando o quadro inteiro (contagens não filtradas)',
   [...f.counts.values()].reduce((a,x)=>a+x,0)===[...today.counts.values()].reduce((a,x)=>a+x,0));
A.setStatuses(new Set());
const vazio=A.computeBoard(T.as_of);
ok('“Limpar” esvazia o quadro sem quebrar',[...vazio.byCol.values()].flat().length===0);
A.setStatuses(null);
ok('“Todos” volta ao quadro cheio',
   JSON.stringify(counts(A.computeBoard(T.as_of)))===JSON.stringify(serverCounts));

console.log('\n=== limites do seletor de data ===');
A.setBoardDate('2026-01-01');
ok('data anterior à janela é presa no mínimo',A.board.date===B.minDate,A.board.date);
A.setBoardDate('2027-01-01');
ok('data futura é presa em hoje',A.board.date===B.maxDate,A.board.date);
A.setBoardDate(B.maxDate);

console.log('\n=== o filtro do topo arrasta o quadro junto ===');
A.setDate('2026-07-25');
ok('mudar o dia do relatório move o quadro',A.board.date==='2026-07-25',A.board.date);
A.setDate('2026-02-01');
ok('dia do relatório fora da janela: quadro prende no mínimo e avisa',
   A.board.date===B.minDate&&A.state.date==='2026-02-01',`${A.state.date} / ${A.board.date}`);
const foot=registry.get('kfoot').innerHTML;
ok('rodapé explica o descasamento de datas',foot.includes('filtro do topo está em'),foot.slice(0,120));
A.setDate(D.period.max);

console.log('\n=== escape / render ===');
ok('esc() neutraliza HTML',A.esc('<img src=x onerror=1>')==='&lt;img src=x onerror=1&gt;');
const bad={id:'x',title:'<script>alert(1)</script>',status:'doing',column:'in_progress',
  updated_ms:Date.now(),completed_ms:null,hist:[{ms:Date.now()-86400000,s:'doing'}]};
T.items.push(bad);A.renderBoard();
const html=registry.get('kboard').innerHTML;
ok('título malicioso sai escapado no cartão',html.includes('&lt;script&gt;')&&!html.includes('<script>alert'));
T.items.pop();A.renderBoard();
ok('cartão traz o status junto da seta',registry.get('kboard').innerHTML.includes('kcard-st'));
ok('cabeçalho do tile mostra a data do quadro',registry.get('extra-tasks').innerHTML.includes('quadro em'));
ok('botão de status rotula o estado',/Status: (todos|\d+ de \d+)/.test(registry.get('kbStatus').textContent),
   registry.get('kbStatus').textContent);

console.log('\n=== tema claro/escuro ===');
const root=document.documentElement, btn=registry.get('themeToggle');
ok('abre no claro quando não há escolha salva',A.currentTheme()==='light',A.currentTheme());
ok('botão oferece o escuro',btn.textContent.includes('Escuro'),btn.textContent);
A.setTheme('dark',true);
ok('escuro marca data-theme na raiz',root.getAttribute('data-theme')==='dark');
ok('botão passa a oferecer o claro',btn.textContent.includes('Claro'),btn.textContent);
ok('escolha fica salva no localStorage',localStorage.getItem('jem-mktdaily-theme')==='dark');
A.setTheme('light',true);
ok('volta para o claro',A.currentTheme()==='light'&&localStorage.getItem('jem-mktdaily-theme')==='light');
// o CSS tem de cobrir os dois temas com os MESMOS tokens, senão algo fica claro no escuro
const css=/<style>([\s\S]*?)<\/style>/.exec(HTML)[1];
const tokens=s=>new Set([...s.matchAll(/(--[a-z0-9-]+)\s*:/g)].map(m=>m[1]));
const claro=tokens(/:root\{([\s\S]*?)\}/.exec(css)[1]);
const escuro=tokens(/:root\[data-theme="dark"\]\{([\s\S]*?)\}/.exec(css)[1]);
const faltando=[...claro].filter(t=>!escuro.has(t));
ok(`o tema escuro redefine todos os ${claro.size} tokens do claro`,faltando.length===0,faltando.join(', '));
// cor fixa (não-token) só é aceitável como texto/glifo branco sobre cor forte
const fixas=css.split('\n').filter(l=>/#[0-9a-fA-F]{3,6}/.test(l)&&!/^\s*--/.test(l)
  &&!/color:#fff|#fff}|#7fe3a1/.test(l));
ok('nenhuma cor fixa de fundo/borda sobrou no CSS',fixas.length===0,fixas.slice(0,3).join(' // '));

/* ---- faixa de dado velho (24/08) -------------------------------------------------
   Existe porque o refresh falhou 17 noites seguidas e passou 26 dias sem ninguém notar:
   a única pista era `Last execution` em texto miúdo. Aqui a asserção que importa é a
   NEGATIVA -- dado velho NÃO pode passar calado. */
console.log('\n=== faixa de dado velho ===');
const bar=document.getElementById('staleBar'), hEl=document.getElementById('hoursExec');
const realExec=D.last_execution;
// `last_execution` é hora de Phoenix (UTC-7); volta N horas a partir de agora
const execHaAtras=h=>new Date(Date.now()-h*3600e3-7*3600e3).toISOString().slice(0,19).replace('T',' ');
/* a página seta `className` (mesmo estilo do #toast); o El do stub não liga className a
   classList como o navegador liga, então leia o que a página realmente escreve */
const cls=()=>bar.className||'';
D.last_execution=execHaAtras(2); A.setHours();
ok('dado fresco (2h) não mostra faixa',cls()==='',cls());
ok('contador de horas fica sem destaque quando fresco',hEl.className==='',hEl.className);
D.last_execution=execHaAtras(A.STALE_WARN+3); A.setHours();
ok(`${A.STALE_WARN+3}h acende a faixa`,cls().includes('show'),cls());
ok('faixa âmbar (ainda não é a vermelha)',!cls().includes('bad'),cls());
ok('faixa diz quantas horas',/\b\d+h\b/.test(bar.innerHTML),bar.innerHTML.slice(0,60));
ok('faixa aponta a causa real (rede da JEM), não credencial',
   /rede da JEM/.test(bar.innerHTML)&&!/senha|credencial/i.test(bar.innerHTML));
ok('contador de horas ganha destaque',hEl.className==='stale-h',hEl.className);
D.last_execution=execHaAtras(A.STALE_BAD+5); A.setHours();
ok(`${A.STALE_BAD+5}h escala para a faixa vermelha`,
   cls().includes('show')&&cls().includes('bad'),cls());
ok('faixa vermelha conta os dias',/~\d+ dias?/.test(bar.innerHTML),bar.innerHTML.slice(0,80));
// o caso real da pane: 26 dias parados
D.last_execution=execHaAtras(26*24); A.setHours();
ok('a pane de 26 dias teria acendido a faixa vermelha',
   cls().includes('bad')&&/~26 dias/.test(bar.innerHTML),cls()+' | '+bar.innerHTML.slice(0,60));
D.last_execution=realExec; A.setHours();
ok('volta ao estado real do arquivo depois do teste',D.last_execution===realExec);

console.log(`\n${pass} passaram, ${fail} falharam`);
process.exit(fail?1:0);
