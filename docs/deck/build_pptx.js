const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";
p.author = "Regenerate-Until-Valid team";

const INK="0F1620", PAPER="FFFFFF", TEAL="0E8A8F", TEALD="0A6367", AMBER="DF7A3B",
      GREEN="178A58", RED="CF3B3B", MUTED="5A656E", TINT="EAF3F2", TINTA="FBEFE6",
      LINE="E3E7E5", DARK="0E1A1E", DARKCARD="16292E", ICE="CFE6E6";
const HEAD="Cambria", BODY="Calibri", MONO="Courier New";
const MW=0.7;

const sh = (o={}) => Object.assign({type:"outer",color:"8AA0A2",blur:9,offset:3,angle:90,opacity:0.22}, o);
function bg(s,c){ s.background={color:c}; }
function eyebrow(s,t,x=MW,y=0.55,color=TEAL){ s.addText(t.toUpperCase(),{x,y,w:11,h:0.3,fontFace:MONO,fontSize:11,color,charSpacing:2,bold:true}); }
function title(s,t,opt={}){ s.addText(t,{x:MW,y:opt.y||0.95,w:opt.w||12,h:opt.h||1.2,fontFace:HEAD,fontSize:opt.size||32,bold:true,color:opt.color||INK,align:"left",lineSpacing:opt.ls||34}); }
function stat(s,x,y,w,big,lbl,color){
  s.addShape(p.ShapeType.roundRect,{x,y,w,h:1.5,rectRadius:0.1,fill:{color:PAPER},line:{color:LINE,width:1},shadow:sh()});
  s.addText(big,{x:x+0.05,y:y+0.15,w:w-0.1,h:0.85,fontFace:HEAD,fontSize:40,bold:true,color,align:"left"});
  s.addText(lbl,{x:x+0.07,y:y+1.0,w:w-0.14,h:0.45,fontFace:BODY,fontSize:12.5,color:MUTED,align:"left",valign:"top"});
}
function chip(s,x,y,txt,fill){
  s.addShape(p.ShapeType.ellipse,{x,y,w:0.62,h:0.62,fill:{color:fill}});
  s.addText(txt,{x,y,w:0.62,h:0.62,align:"center",valign:"middle",fontFace:HEAD,fontSize:18,bold:true,color:PAPER});
}
function codeChip(s,x,y,w,txt){
  s.addShape(p.ShapeType.roundRect,{x,y,w,h:0.5,rectRadius:0.07,fill:{color:TINT},line:{color:LINE,width:1}});
  s.addText(txt,{x:x+0.1,y,w:w-0.2,h:0.5,align:"center",valign:"middle",fontFace:MONO,fontSize:13,color:INK});
}
function vbars(s,x0,y0,w,h,groups){
  const plotL=x0+0.55, plotB=y0+h, plotW=w-0.55;
  for(let i=0;i<=4;i++){
    const yy=plotB-(h*(i/4));
    s.addShape(p.ShapeType.line,{x:plotL,y:yy,w:plotW,h:0,line:{color:"EBEBEB",width:1}});
    s.addText(i*25+"%",{x:x0-0.05,y:yy-0.13,w:0.52,h:0.26,align:"right",valign:"middle",fontFace:BODY,fontSize:9.5,color:MUTED});
  }
  const gW=plotW/groups.length, bw=0.5, gap=0.16;
  groups.forEach((g,i)=>{
    const gx=plotL+gW*i+gW/2;
    [["fp",g.fp,AMBER],["pl",g.pl,TEAL]].forEach((b,j)=>{
      const bh=Math.max(0.02,(b[1]/100)*h);
      const bx=gx-(bw+gap/2)+j*(bw+gap);
      s.addShape(p.ShapeType.roundRect,{x:bx,y:plotB-bh,w:bw,h:bh,rectRadius:0.03,fill:{color:b[2]}});
      s.addText(b[1]+"%",{x:bx-0.18,y:plotB-bh-0.3,w:bw+0.36,h:0.28,align:"center",fontFace:HEAD,fontSize:12,bold:true,color:b[2]});
    });
    s.addText(g.label,{x:gx-gW/2,y:plotB+0.1,w:gW,h:0.5,align:"center",valign:"top",fontFace:MONO,fontSize:10,color:INK});
  });
}
function hbars(s,x0,y0,w,h,rows,maxv){
  const rowH=h/rows.length, labelW=2.55, barX=x0+labelW, barW=w-labelW-0.55;
  rows.forEach((r,i)=>{
    const yy=y0+rowH*i;
    s.addText(r[0],{x:x0,y:yy,w:labelW-0.12,h:rowH,align:"right",valign:"middle",fontFace:MONO,fontSize:12.5,color:INK});
    const bw=Math.max(0.04,(r[1]/maxv)*barW);
    s.addShape(p.ShapeType.roundRect,{x:barX,y:yy+rowH*0.24,w:bw,h:rowH*0.52,rectRadius:0.03,fill:{color:RED}});
    s.addText(String(r[1]),{x:barX+bw+0.1,y:yy,w:0.8,h:rowH,valign:"middle",fontFace:HEAD,fontSize:14,bold:true,color:INK});
  });
}
function pill(s,x,y,w,txt,o={}){
  s.addShape(p.ShapeType.roundRect,{x,y,w,h:o.h||0.44,rectRadius:0.06,fill:{color:o.fill||PAPER},line:{color:o.line||LINE,width:1}});
  s.addText(txt,{x:x+0.03,y,w:w-0.06,h:o.h||0.44,align:"center",valign:"middle",fontFace:o.mono?MONO:BODY,fontSize:o.fs||11,bold:o.bold,color:o.color||INK,lineSpacing:o.ls||11,margin:0});
}
function vArrow(s,x,y,h){ s.addShape(p.ShapeType.line,{x,y,w:0,h,line:{color:TEALD,width:2,endArrowType:"triangle"}}); }
function hArrow(s,x,y,w,dbl){ s.addShape(p.ShapeType.line,{x,y,w,h:0,line:{color:TEALD,width:2,endArrowType:"triangle",beginArrowType:dbl?"triangle":"none"}}); }
function dbgRow(s,x,y,w,id,type,tm,payload,tc){
  s.addText([
    {text:"#"+id+"  ",options:{color:"7FA8C9"}},
    {text:type.padEnd(9," ")+" ",options:{color:tc,bold:true}},
    {text:tm+"  ",options:{color:"6B7686"}},
    {text:payload,options:{color:"9AA6B2"}}
  ],{x,y,w,h:0.3,fontFace:MONO,fontSize:10.5,valign:"middle",margin:0});
}

/* 1 TITLE */
let s=p.addSlide(); bg(s,DARK);
eyebrow(s,"SCCUR 2026 · Undergraduate Research",MW,0.9,TEAL);
s.addText("Regenerate-Until-Valid",{x:MW,y:1.35,w:12,h:1.5,fontFace:HEAD,fontSize:52,bold:true,color:PAPER});
s.addText("A neuro-symbolic agentic framework for reliable STEM problem generation across Precalculus, Calculus, and AP Physics 1.",
  {x:MW,y:3.0,w:9.6,h:1.0,fontFace:BODY,fontSize:19,color:ICE,lineSpacing:27});
s.addText("Correctness is enforced deterministically — not predicted.",{x:MW,y:4.25,w:10,h:0.5,fontFace:MONO,fontSize:15,color:AMBER});
s.addText([{text:"Anay Parikh, Yuki Tanaka, Isabella Chen, Faiza Fatima, Ashna Munavalli\n",options:{bold:true,color:PAPER}},
  {text:"Advisor: Suresh Subramaniam",options:{color:"9FB2B4"}}],{x:MW,y:5.6,w:11,h:0.9,fontFace:BODY,fontSize:14,lineSpacing:22});
s.addNotes("An LLM proposes problems; a deterministic symbolic verifier decides correctness — a property of the system, not a probability.");

/* 2 PROBLEM */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"The Problem");
title(s,"LLMs write practice problems at scale —\nbut get the exact reasoning wrong.",{size:30,ls:36,h:1.5});
s.addText("A single wrong answer, bad unit, or ill-posed prompt erodes a student's trust and teaches the wrong thing. For a tutor, a 5% hallucination rate is a 5% chance of teaching a lie.",
  {x:MW,y:2.7,w:5.7,h:2.2,fontFace:BODY,fontSize:16,color:MUTED,lineSpacing:24,valign:"top"});
const bad=[["a projectile with time  t = −3 s","impossible value"],["momentum reported in joules","unit mismatch"],
  ["stated answer 7,  true answer 5","wrong math"],["an equation with no unique solution","ill-posed"]];
let by=2.55;
bad.forEach(b=>{
  s.addShape(p.ShapeType.roundRect,{x:6.9,y:by,w:5.7,h:0.92,rectRadius:0.08,fill:{color:TINTA},line:{color:"F0DCC9",width:1},shadow:sh({opacity:0.15})});
  s.addText(b[0],{x:7.15,y:by+0.1,w:5.2,h:0.45,fontFace:MONO,fontSize:13.5,color:INK,valign:"middle"});
  s.addText(b[1].toUpperCase(),{x:7.15,y:by+0.5,w:5.2,h:0.32,fontFace:BODY,fontSize:10.5,color:AMBER,charSpacing:1});
  by+=1.06;
});
s.addNotes("Generation is easy; guaranteeing correctness is the unsolved part.");

/* 3 OBJECTIVES */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Research Objectives");
title(s,"Can architecture — not model scale — make generation trustworthy?",{size:29,ls:34,h:1.3});
const objs=[["1","Enforce correctness deterministically.","Wrap an LLM in an independent symbolic verifier so no wrong problem is ever delivered."],
  ["2","Isolate what matters.","A causal ablation separating verification, adaptive planning, and personalization."],
  ["3","Test across models.","Does the architecture lift reliability regardless of the base model's strength?"],
  ["4","Design for learning.","A pilot protocol to measure learning gains from verified, personalized practice."]];
let oy=2.55;
objs.forEach(o=>{ chip(s,MW,oy,o[0],TEAL);
  s.addText([{text:o[1]+"  ",options:{bold:true,color:INK}},{text:o[2],options:{color:MUTED}}],
    {x:MW+0.85,y:oy-0.05,w:11.2,h:0.7,fontFace:BODY,fontSize:15.5,lineSpacing:21,valign:"middle"}); oy+=1.12; });
s.addNotes("Reliability, causal ablation, cross-model, and a learning-outcomes pilot (designed, not yet run).");

/* 4 APPROACH */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Approach");
title(s,"The model proposes. The verifier disposes.",{size:31});
s.addText([{text:"The LLM emits each problem as structured JSON and ",options:{color:MUTED}},
  {text:"never decides its own correctness",options:{bold:true,color:INK}},
  {text:". A deterministic neuro-symbolic verifier independently re-derives the answer and accepts or rejects against a ",options:{color:MUTED}},
  {text:"closed taxonomy of six failure codes",options:{bold:true,color:INK}},
  {text:" — every rejection maps to exactly one.",options:{color:MUTED}}],
  {x:MW,y:2.2,w:11.9,h:1.5,fontFace:BODY,fontSize:17,lineSpacing:26,valign:"top"});
const codes=["json_invalid","math_invalid","nonunique_solution","unit_mismatch","semantic_ambiguity","off_target_difficulty"];
let cx=MW, cyy=4.35; const cw=[1.9,1.9,2.7,2.05,2.7,2.9];
codes.forEach((c,i)=>{ if(i===3){cx=MW;cyy=5.05;} codeChip(s,cx,cyy,cw[i],c); cx+=cw[i]+0.18; });
s.addNotes("Six explicit failure codes give a quantifiable vocabulary for every rejection.");

/* 5 METHODOLOGY LOOP */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Methodology · The Closed Loop");
title(s,"Observe → plan → generate → verify → accept or regenerate.",{size:26,w:12.2});
const steps=[["OBSERVE","student model"],["PLAN","skill & difficulty"],["GENERATE","structured JSON"],["TRANSLATE","JSON → symbolic"],["VERIFY","neuro-symbolic"],["ACCEPT","deliver"]];
const bw=1.86, gap=0.13; let sx=MW, syy=2.9;
steps.forEach((st,i)=>{ const last=i===5;
  s.addShape(p.ShapeType.roundRect,{x:sx,y:syy,w:bw,h:1.35,rectRadius:0.09,fill:{color:last?TINT:PAPER},line:{color:last?TEAL:LINE,width:last?1.5:1},shadow:sh({opacity:0.16})});
  s.addText(st[0],{x:sx+0.12,y:syy+0.16,w:bw-0.24,h:0.3,fontFace:MONO,fontSize:10.5,color:TEAL,charSpacing:1,bold:true});
  s.addText(st[1],{x:sx+0.12,y:syy+0.55,w:bw-0.24,h:0.7,fontFace:BODY,fontSize:13.5,bold:true,color:INK,valign:"top",lineSpacing:16});
  if(!last) s.addText("→",{x:sx+bw-0.02,y:syy,w:0.28,h:1.35,align:"center",valign:"middle",fontFace:BODY,fontSize:18,color:MUTED});
  sx+=bw+gap; });
s.addShape(p.ShapeType.roundRect,{x:MW,y:4.65,w:12.0,h:0.7,rectRadius:0.08,fill:{color:TINTA},line:{color:"F0DCC9",width:1}});
s.addText("ON FAILURE  →  regenerate with the explicit reason as feedback, until valid or the budget is spent",
  {x:MW+0.2,y:4.65,w:11.6,h:0.7,fontFace:MONO,fontSize:13.5,color:AMBER,valign:"middle"});
s.addText("Every step is appended to an immutable event log — any problem's full generation trace is reconstructable per student and per session.",
  {x:MW,y:5.7,w:12,h:0.8,fontFace:BODY,fontSize:14,color:MUTED,lineSpacing:20});
s.addNotes("Propose, verify, and on rejection feed the specific failure back — deterministic acceptance, not probabilistic hope.");

/* 6 VERIFIER */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"The Neuro-Symbolic Verifier");
title(s,"Three independent checks, one strict acceptance rule.",{size:29});
const vc=[["SymPy","Mathematics","Symbolic equivalence, solution existence & uniqueness, derivative and integral validation.",TEAL],
  ["pint","Physics","Deterministic formula templates with dimensional analysis and realism envelopes — 1D, 2D, and rotational.",TEALD],
  ["LLM","Clarity","An advisory ambiguity check on wording only — never on correctness.",AMBER]];
let vx=MW;
vc.forEach(v=>{ s.addShape(p.ShapeType.roundRect,{x:vx,y:2.4,w:3.86,h:2.55,rectRadius:0.1,fill:{color:PAPER},line:{color:LINE,width:1},shadow:sh()});
  s.addText(v[0],{x:vx+0.28,y:2.62,w:3.3,h:0.6,fontFace:HEAD,fontSize:26,bold:true,color:v[3]});
  s.addText(v[1],{x:vx+0.28,y:3.28,w:3.3,h:0.4,fontFace:BODY,fontSize:15,bold:true,color:INK});
  s.addText(v[2],{x:vx+0.28,y:3.72,w:3.34,h:1.1,fontFace:BODY,fontSize:13,color:MUTED,lineSpacing:18,valign:"top"}); vx+=4.06; });
s.addText([{text:"Acceptance rule:  ",options:{bold:true,color:INK}},
  {text:"a problem is delivered only if every deterministic check passes and semantic ambiguity is below threshold. The translation layer fails closed — unparseable expressions raise, never eval.",options:{color:MUTED}}],
  {x:MW,y:5.35,w:12,h:1.0,fontFace:BODY,fontSize:14.5,lineSpacing:21,valign:"top"});
s.addNotes("The LLM's only verification role is an advisory clarity score. All correctness is symbolic and deterministic.");

/* 7 SYSTEM */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"System & Scope");
title(s,"Offline-first, model-agnostic, verifiably seeded.",{size:29});
const scg=[["8","Model backends","One interface: Llama, GPT, Gemma, Mistral, DeepSeek and Gemini all speak the OpenAI-compatible API; Claude uses Anthropic's; plus an offline mock."],
  ["19","Skills · 3 domains","Precalculus, single-variable Calculus, AP Physics 1."],
  ["1,226","Pre-verified problems","An offline mock oracle seeds a bank where every item passed the full verifier."],
  ["1D·2D·rot","Physics coverage","Projectile, incline, torque, rotational kinematics & dynamics — difficulty 1–5."]];
let scx=MW;
scg.forEach(c=>{ s.addShape(p.ShapeType.roundRect,{x:scx,y:2.45,w:2.86,h:2.7,rectRadius:0.1,fill:{color:PAPER},line:{color:LINE,width:1},shadow:sh()});
  s.addText(c[0],{x:scx+0.22,y:2.68,w:2.5,h:0.75,fontFace:HEAD,fontSize:c[0].length>4?24:36,bold:true,color:TEAL,valign:"middle"});
  s.addText(c[1],{x:scx+0.22,y:3.5,w:2.5,h:0.6,fontFace:BODY,fontSize:14,bold:true,color:INK,valign:"top",lineSpacing:17});
  s.addText(c[2],{x:scx+0.22,y:4.15,w:2.52,h:0.95,fontFace:BODY,fontSize:12,color:MUTED,lineSpacing:16,valign:"top"}); scx+=3.03; });
s.addText("Stack: Next.js · FastAPI · SQLite · immutable event log. The offline mock path keeps the whole pipeline reproducible with no keys.",
  {x:MW,y:5.55,w:12,h:0.6,fontFace:MONO,fontSize:12,color:MUTED,lineSpacing:18});
s.addNotes("Eight interchangeable LLM backends; a 1,226-problem verified bank built offline; physics spans 1D, 2D, and rotational.");

/* 8 ARCHITECTURE */
{
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"System Architecture");
title(s,"How the pieces fit: frontend, backend, verifier, models, and log.",{size:24,w:12.5});
const bx=2.6, bw2=8.13;
s.addShape(p.ShapeType.roundRect,{x:bx,y:1.9,w:bw2,h:1.0,rectRadius:0.1,fill:{color:PAPER},line:{color:LINE,width:1.2},shadow:sh()});
s.addText("FRONTEND — Next.js (App Router)",{x:bx+0.2,y:1.97,w:5,h:0.3,fontFace:MONO,fontSize:10,bold:true,color:TEAL,charSpacing:1});
["Practice UI","Debug event-log panel","Login / Auth","Model · Skill · Difficulty"].forEach((t,i)=>{ pill(s,bx+0.2+i*1.94,2.36,1.84,t,{fill:TINT,fs:9.5,h:0.42}); });
vArrow(s,bx+bw2/2,2.9,0.36);
s.addText("HTTP · Server-Sent Events",{x:bx+bw2/2+0.15,y:2.94,w:4,h:0.3,fontFace:MONO,fontSize:9,color:MUTED,valign:"middle"});
const bY=3.42, bH=2.3;
s.addShape(p.ShapeType.roundRect,{x:bx,y:bY,w:bw2,h:bH,rectRadius:0.1,fill:{color:"F4F8F7"},line:{color:"CFE0DD",width:1.2},shadow:sh()});
s.addText("BACKEND — FastAPI",{x:bx+0.2,y:bY+0.08,w:5,h:0.28,fontFace:MONO,fontSize:10,bold:true,color:TEAL,charSpacing:1});
s.addText("CLOSED-LOOP AGENT",{x:bx+0.2,y:bY+0.4,w:4,h:0.22,fontFace:MONO,fontSize:8,color:MUTED,charSpacing:1});
["Assessor","Planner","Context Selector","Orchestrator","Grader"].forEach((t,i)=>{ pill(s,bx+0.2+i*1.548,bY+0.62,1.46,t,{fill:PAPER,fs:9.5,h:0.4}); });
s.addText("NEURO-SYMBOLIC VERIFIER",{x:bx+0.2,y:bY+1.12,w:4,h:0.22,fontFace:MONO,fontSize:8,color:MUTED,charSpacing:1});
["Translation","SymPy · math","pint · physics","Difficulty","Clarity","Engine · accept"].forEach((t,i)=>{ pill(s,bx+0.2+i*1.29,bY+1.34,1.2,t,{fill:PAPER,fs:8.5,h:0.4}); });
s.addText("every rejection = one of six failure codes  →  regenerate with the reason as feedback",{x:bx+0.2,y:bY+1.84,w:bw2-0.4,h:0.32,fontFace:MONO,fontSize:8.5,color:AMBER,valign:"middle"});
s.addShape(p.ShapeType.roundRect,{x:0.5,y:bY,w:1.92,h:bH,rectRadius:0.1,fill:{color:PAPER},line:{color:LINE,width:1},shadow:sh()});
s.addText("CONTENT · JSON",{x:0.5,y:bY+0.12,w:1.92,h:0.24,align:"center",fontFace:MONO,fontSize:8.5,bold:true,color:MUTED,charSpacing:.5});
["skills.json","prompts.json","context_library","problem_bank"].forEach((t,i)=>{ s.addText("·  "+t,{x:0.64,y:bY+0.5+i*0.42,w:1.7,h:0.34,fontFace:MONO,fontSize:9,color:INK,valign:"middle"}); });
hArrow(s,2.42,bY+bH/2,0.16);
s.addShape(p.ShapeType.roundRect,{x:10.91,y:bY,w:1.92,h:bH,rectRadius:0.1,fill:{color:"0B1020"},line:{color:"22304A",width:1},shadow:sh({opacity:0.3})});
s.addText("LLM PROVIDERS",{x:10.91,y:bY+0.12,w:1.92,h:0.24,align:"center",fontFace:MONO,fontSize:8.5,bold:true,color:"9FC0E0",charSpacing:.5});
["mock  (offline)","OpenAI-compatible:","·  Llama · GPT","·  Gemma · Mistral","·  DeepSeek · R1","·  Gemini","Anthropic API:","·  Claude"].forEach((t,i)=>{ const hdr=t.endsWith(":"); s.addText(t,{x:11.05,y:bY+0.48+i*0.29,w:1.75,h:0.27,fontFace:MONO,fontSize:hdr?8:9,bold:hdr,color:i===0?"4ADE80":(hdr?"9FC0E0":"D7E1EA"),valign:"middle"}); });
hArrow(s,10.73,bY+bH/2,0.16,true);
vArrow(s,bx+bw2/2,bY+bH,0.3);
s.addText("append-only events · read saved state",{x:bx+bw2/2+0.15,y:bY+bH+0.02,w:4,h:0.3,fontFace:MONO,fontSize:9,color:MUTED,valign:"middle"});
const dY=bY+bH+0.34;
s.addShape(p.ShapeType.roundRect,{x:bx,y:dY,w:bw2,h:0.9,rectRadius:0.1,fill:{color:"0E1A1E"},line:{color:"22304A",width:1},shadow:sh({opacity:0.3})});
s.addText("DATABASE — SQLite (or Postgres)",{x:bx+0.2,y:dY+0.1,w:5,h:0.28,fontFace:MONO,fontSize:10,bold:true,color:"E5E9F0",charSpacing:1});
["Events — immutable append-only log","Students","Problems"].forEach((t,i)=>{ const wds=[3.9,1.35,1.35], xs=[bx+0.22,bx+4.25,bx+5.75];
  s.addShape(p.ShapeType.roundRect,{x:xs[i],y:dY+0.42,w:wds[i],h:0.36,rectRadius:0.05,fill:{color:"16292E"},line:{color:"2A3F46",width:1}});
  s.addText(t,{x:xs[i]+0.05,y:dY+0.42,w:wds[i]-0.1,h:0.36,align:"center",valign:"middle",fontFace:MONO,fontSize:8.5,color:"CFD8DE"}); });
s.addNotes("Frontend (Next.js) ↔ FastAPI over HTTP+SSE; backend runs the agent loop + verifier, calls any of seven LLM providers, seeded by JSON content, appends to an immutable SQLite log.");
}

/* 9 DEBUG LOG */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"The System, Instrumented");
title(s,"Every step is a logged event — reconstructable, live.",{size:28});
s.addText([{text:"The full app runs the loop end to end. An in-app ",options:{color:MUTED}},
  {text:"debug panel",options:{bold:true,color:INK}},
  {text:" streams the immutable event log in real time — every ",options:{color:MUTED}},
  {text:"observe, deliver, verify, and attempt",options:{color:INK}},
  {text:" is one structured row, keyed by student and session.",options:{color:MUTED}}],
  {x:MW,y:2.35,w:5.15,h:2.2,fontFace:BODY,fontSize:15.5,lineSpacing:23,valign:"top"});
s.addText("So any delivered problem's entire generation trace — including every rejected candidate and its failure code — is auditable after the fact.",
  {x:MW,y:4.7,w:5.15,h:1.4,fontFace:BODY,fontSize:14,color:MUTED,lineSpacing:21,valign:"top"});
const px=6.35, pyy=1.95, pw=6.3, ph=4.9;
s.addShape(p.ShapeType.roundRect,{x:px,y:pyy,w:pw,h:ph,rectRadius:0.09,fill:{color:"0B1020"},line:{color:"22304A",width:1},shadow:sh({color:"1B2437",opacity:0.35})});
s.addText("EVENT LOG",{x:px+0.3,y:pyy+0.22,w:3,h:0.3,fontFace:MONO,fontSize:11,bold:true,color:"E5E9F0",charSpacing:1.5});
s.addText("demo · this session · 11 events",{x:px+pw-3.3,y:pyy+0.24,w:3,h:0.3,fontFace:MONO,fontSize:9.5,color:"6B7686",align:"right"});
s.addShape(p.ShapeType.line,{x:px+0.3,y:pyy+0.62,w:pw-0.6,h:0,line:{color:"22304A",width:1}});
const G2="4ADE80", A2="FBBF24";
const rows=[["580","login","16:16:44","{ username: demo }",A2],["579","attempt","16:14:14","{ skill: projectile_motion, correct: false }",A2],
  ["578","deliver","16:14:14","{ skill: projectile_motion, difficulty: 5 }",G2],["577","observe","16:14:14","{ skill_vector: {...} }",A2],
  ["576","attempt","16:14:14","{ skill: kinematics, correct: false }",A2],["575","deliver","16:14:14","{ skill: kinematics, difficulty: 1 }",G2],
  ["573","attempt","16:14:14","{ skill: derivative_rules, correct: false }",A2],["572","deliver","16:14:14","{ skill: derivative_rules, difficulty: 3 }",G2],
  ["571","observe","16:14:14","{ skill_vector: {...} }",A2],["570","register","16:14:14","{ username: demo }",A2]];
let ry=pyy+0.82;
rows.forEach(r=>{ dbgRow(s,px+0.3,ry,pw-0.55,r[0],r[1],r[2],r[3],r[4]); ry+=0.395; });
s.addNotes("The debug panel shows the real immutable event log keyed by user and session. Green = delivered. Full traces are auditable.");

/* 10 RESULTS: BUDGET CURVE (the money plot) */
function bcurve(s,x0,y0,w,h,vals){
  const plotL=x0+0.55, plotB=y0+h, plotW=w-0.55;
  for(let i=0;i<=4;i++){ const yy=plotB-(h*(i/4));
    s.addShape(p.ShapeType.line,{x:plotL,y:yy,w:plotW,h:0,line:{color:"EBEBEB",width:1}});
    s.addText(i*25+"%",{x:x0-0.05,y:yy-0.13,w:0.52,h:0.26,align:"right",valign:"middle",fontFace:BODY,fontSize:9.5,color:MUTED}); }
  const gW=plotW/vals.length, bw=0.62;
  vals.forEach((v,i)=>{ const gx=plotL+gW*i+gW/2, bh=Math.max(0.02,(v[1]/100)*h);
    s.addShape(p.ShapeType.roundRect,{x:gx-bw/2,y:plotB-bh,w:bw,h:bh,rectRadius:0.03,fill:{color:i===0?AMBER:TEAL}});
    s.addText(v[1]+"%",{x:gx-bw/2-0.18,y:plotB-bh-0.3,w:bw+0.36,h:0.28,align:"center",fontFace:HEAD,fontSize:12,bold:true,color:i===0?AMBER:TEAL});
    s.addText(v[0],{x:gx-gW/2,y:plotB+0.1,w:gW,h:0.5,align:"center",valign:"top",fontFace:MONO,fontSize:10,color:INK}); });
}
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Results · Reliability");
title(s,"Validity climbs with each regeneration — then plateaus.",{size:28});
s.addShape(p.ShapeType.rect,{x:MW+2.55,y:2.2,w:0.18,h:0.18,fill:{color:AMBER}});
s.addText("single-shot (budget 0)",{x:MW+2.8,y:2.11,w:2.6,h:0.36,fontFace:BODY,fontSize:12,color:INK,valign:"middle"});
s.addShape(p.ShapeType.rect,{x:MW+5.35,y:2.2,w:0.18,h:0.18,fill:{color:TEAL}});
s.addText("with regeneration",{x:MW+5.6,y:2.11,w:2.0,h:0.36,fontFace:BODY,fontSize:12,color:INK,valign:"middle"});
bcurve(s,MW+0.15,2.7,7.55,3.35,[["@0",21],["@1",26],["@2",35],["@3",36],["@4",40],["@5",42],["@6",43]]);
stat(s,8.7,2.5,3.95,"21 → 43%","budget 0 → 6 · +22 pts · 2.0× validity",TEAL);
stat(s,8.7,4.25,3.95,"58% / 30%","closed-loop validity · math vs physics",INK);
s.addText("Llama 3.1 8B · 95 generations · all 19 skills × 5 difficulties · 0 infrastructure errors. Each regeneration adds validity; returns flatten by budget 5–6.",{x:8.7,y:6.05,w:3.95,h:1.0,fontFace:MONO,fontSize:9.5,color:MUTED,lineSpacing:14});
s.addNotes("Difficulty-complete run on the corrected prompts. Budget 0 (single-shot) delivers 21%; each regeneration adds validity to 43% by budget 6, a 2.0x lift, flattening around 5-6. The loop lifts math (24->58%) far more than physics (18->30%), where the base model's arithmetic caps it.");

/* 11 RESULTS: FAILURES */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Results · Failure Taxonomy");
title(s,"518 wrong problems caught before a student saw them.",{size:27});
hbars(s,MW,2.7,8.05,3.7,[["math_invalid",376],["off_target_difficulty",110],["json_invalid",20],["nonunique_solution",6],["unit_mismatch",6]],420);
s.addShape(p.ShapeType.roundRect,{x:8.85,y:2.7,w:3.8,h:3.3,rectRadius:0.1,fill:{color:TINT},line:{color:LINE,width:1},shadow:sh()});
s.addText("73%",{x:9.05,y:2.95,w:3.4,h:1.0,fontFace:HEAD,fontSize:52,bold:true,color:RED});
s.addText([{text:"of caught failures were ",options:{color:MUTED}},{text:"mathematically invalid",options:{bold:true,color:INK}},
  {text:" — concrete wrong answers a single-shot pipeline would have delivered as fact.",options:{color:MUTED}}],
  {x:9.05,y:4.0,w:3.42,h:1.9,fontFace:BODY,fontSize:14,lineSpacing:20,valign:"top"});
s.addNotes("Llama n=95: 518 rejections across the closed taxonomy, math_invalid dominating at 73%, off_target_difficulty next. json_invalid dropped sharply after the prompt-completeness fix. Every failure type appears; the verifier is doing real work.");

/* 11b MATH vs PHYSICS */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Results · Where the loop helps");
title(s,"The loop lifts math further than physics.",{size:28});
s.addShape(p.ShapeType.rect,{x:MW+2.55,y:2.2,w:0.18,h:0.18,fill:{color:AMBER}});
s.addText("single-shot",{x:MW+2.8,y:2.11,w:1.4,h:0.36,fontFace:BODY,fontSize:12,color:INK,valign:"middle"});
s.addShape(p.ShapeType.rect,{x:MW+4.2,y:2.2,w:0.18,h:0.18,fill:{color:TEAL}});
s.addText("closed-loop",{x:MW+4.45,y:2.11,w:1.4,h:0.36,fontFace:BODY,fontSize:12,color:INK,valign:"middle"});
vbars(s,MW+0.15,2.7,7.55,3.35,[{label:"math (n=45)",fp:24,pl:58},{label:"physics (n=50)",fp:18,pl:30}]);
s.addShape(p.ShapeType.roundRect,{x:8.85,y:2.7,w:3.8,h:3.3,rectRadius:0.1,fill:{color:TINT},line:{color:LINE,width:1},shadow:sh()});
s.addText("The ceiling tracks arithmetic, not the system.",{x:9.05,y:2.9,w:3.4,h:0.85,fontFace:HEAD,fontSize:16,bold:true,color:INK,lineSpacing:20});
s.addText([{text:"Physics templates the model can compute pass; those it can't are caught, never delivered.\n\n",options:{color:MUTED}},
  {text:"rotational_dynamics (τ = I·α)   5/5\n",options:{color:GREEN,bold:true}},
  {text:"torque · incline · projectile\n(sin/cos)   0/5\n",options:{color:RED,bold:true}},
  {text:"\nWrong arithmetic on trig / multi-step formulas is genuine 8B weakness — rejected by the verifier.",options:{color:MUTED}}],
  {x:9.05,y:3.8,w:3.42,h:2.15,fontFace:BODY,fontSize:11.5,lineSpacing:15,valign:"top"});
s.addText("Math = Precalculus + Calculus (SymPy) · Physics = template + unit checks · closed-loop = validity within a 6-regeneration budget",{x:MW,y:6.55,w:12,h:0.3,fontFace:MONO,fontSize:8,color:MUTED});
s.addNotes("Splitting the two tracks: the loop lifts math from 24 to 58 percent but physics only 18 to 30. Physics is capped by the base model's arithmetic — it nails simple formulas (rotational_dynamics 5/5) but fails trig/multi-step ones (torque, incline, projectile 0/5), which the verifier correctly rejects. The ceiling is the model, not the system.");

/* 12 CROSS-MODEL (three models) */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Cross-Model Insight");
title(s,"The weaker the model, the more the loop matters.",{size:28});
function mpanel(x,tag,tagc,jump,jumpc,lift,body){
  s.addShape(p.ShapeType.roundRect,{x,y:2.5,w:3.85,h:3.2,rectRadius:0.11,fill:{color:PAPER},line:{color:LINE,width:1},shadow:sh()});
  s.addText(tag.toUpperCase(),{x:x+0.28,y:2.74,w:3.35,h:0.32,fontFace:MONO,fontSize:10.5,color:tagc,charSpacing:1,bold:true});
  s.addText(jump,{x:x+0.25,y:3.12,w:3.4,h:0.8,fontFace:HEAD,fontSize:33,bold:true,color:jumpc});
  s.addShape(p.ShapeType.roundRect,{x:x+0.28,y:4.02,w:1.3,h:0.44,rectRadius:0.22,fill:{color:tagc}});
  s.addText(lift,{x:x+0.28,y:4.02,w:1.3,h:0.44,align:"center",valign:"middle",fontFace:HEAD,fontSize:13,bold:true,color:PAPER});
  s.addText(body,{x:x+0.28,y:4.62,w:3.35,h:1.0,fontFace:BODY,fontSize:12.5,color:MUTED,lineSpacing:17,valign:"top"});
}
mpanel(MW,"Local · Llama 3.1 8B",AMBER,"21% → 43%",AMBER,"2.0×","Weakest base model, largest relative lift — the loop doubles what reaches a student (n=95, difficulty-complete).");
mpanel(4.84,"Local · Gemma 4",RED,"52% → 82%",RED,"1.6×","A stronger 8B model clears the physics arithmetic Llama can't — physics 55→70% vs Llama's 30% (n=40, balanced).");
mpanel(8.98,"Frontier · Gemini 3.6",TEAL,"82% → 91%",TEAL,"1.1×","Strongest model, smallest relative lift — already 82% first-try. Clears physics too (78→82%); the loop polishes the rest to near-perfect (n=95).");
s.addText([{text:"Reliability is architectural, not a function of scale.  ",options:{bold:true,color:INK}},
  {text:"The loop's relative lift shrinks as the model strengthens (Llama 2.0× → Gemma 1.6× → Gemini 1.1×), and physics is the divider — validity climbs 30% → 70% → 82% as models get better at the arithmetic the verifier checks.",options:{color:MUTED}}],
  {x:MW,y:5.95,w:12,h:0.6,fontFace:BODY,fontSize:14.5,lineSpacing:20,valign:"top"});
s.addText("single-shot → closed-loop delivered validity · corrected prompts · Llama & Gemini n=95 (all cells), Gemma n=40 balanced · Gemini 3.6 Flash on Tier 1",
  {x:MW,y:6.62,w:12,h:0.3,fontFace:MONO,fontSize:8,color:MUTED});
s.addNotes("All three on the corrected prompts. Llama and Gemini are full 95-problem runs; Gemma is 40 problems balanced 8 per difficulty. Overall 43% -> 82% -> 91% as the model strengthens, and relative lift shrinks (2.0x -> 1.6x -> 1.1x). Physics is the divider: 30% -> 70% -> 82% — a stronger model does the trig/multi-step arithmetic the verifier checks, which Llama can't. On the 40 identical cells Llama and Gemma share, Llama is 28->60% vs Gemma 82%. Gemini 3.6 Flash ran on Tier 1 billing.");

/* 12b MODEL COMPARISON TABLE (validity × cost × deployment) */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Cross-Model · Full Comparison");
title(s,"Validity, cost, and footprint — side by side.",{size:27});
{
  const head=["Model","Deployment","Params","Footprint","Single-shot","Closed-loop","Median/prob"];
  const data=[
    ["Llama 3.1 8B","Local (Ollama)","8B","4.9 GB","21%","43%","138 s"],
    ["Gemma 4","Local (Ollama)","8B","9.6 GB","52%","82%","228 s"],
    ["Gemini 3.6 Flash","API key","—","cloud","82%","91%","18 s"],
  ];
  const rowc=[AMBER,RED,TEAL];
  const rows=[ head.map(t=>({text:t,options:{bold:true,color:PAPER,fill:{color:TEALD},align:"center",valign:"middle",fontFace:MONO,fontSize:11}})) ];
  data.forEach((r,ri)=>{ rows.push(r.map((c,ci)=>({text:c,options:{
    color:ci===0?INK:(ci===5?rowc[ri]:MUTED), bold:ci===0||ci===5,
    align:ci===0?"left":"center", valign:"middle",
    fontFace:ci===0?BODY:MONO, fontSize:ci===0?13:12,
    fill:{color:ri%2?TINT:"FFFFFF"}}}))); });
  s.addTable(rows,{x:MW,y:2.55,w:11.9,colW:[2.5,1.85,0.95,1.3,1.5,1.5,1.8],
    rowH:[0.5,0.72,0.72,0.72],border:{type:"solid",color:LINE,pt:1},valign:"middle"});
}
s.addText([{text:"Validity, cost, and deployment — one trade-off.  ",options:{bold:true,color:INK}},
  {text:"Validity rises with model strength, but so does the bill: the two local 8B models need no key yet are slow (Gemma 193s per regeneration cycle); hosted Gemini is fastest and most accurate but off-device and paid. The loop improves every row — the row you pick is an infrastructure decision.",options:{color:MUTED}}],
  {x:MW,y:5.5,w:12,h:1.0,fontFace:BODY,fontSize:14,lineSpacing:20,valign:"top"});
s.addText("Ollama Q4 GGUF footprints ≈ RAM/VRAM to load · closed-loop = validity within a 6-regeneration budget · per-regeneration cycle: Llama 28s · Gemma 193s · Gemini 18s · Llama/Gemini n=95, Gemma n=40",
  {x:MW,y:6.72,w:12,h:0.3,fontFace:MONO,fontSize:8,color:MUTED});
s.addNotes("A single table trading validity against cost and deployment. Llama 21->43% (28s/regen cycle), Gemma 52->82% (193s/cycle — accurate but slow), Gemini 3.6 82->91% (18s, fastest and most accurate, but hosted and paid Tier 1). Both local models need no key. The loop improves every row; the row you pick is an infrastructure decision.");

/* 13 CONCLUSION */
s=p.addSlide(); bg(s,DARK);
eyebrow(s,"Conclusion",MW,0.8,TEAL);
s.addText("Deterministic verification turns unreliable generation into trustworthy content.",{x:MW,y:1.3,w:11.6,h:1.7,fontFace:HEAD,fontSize:34,bold:true,color:PAPER,lineSpacing:40});
s.addText("By making the LLM a proposer and a symbolic engine the judge, correctness stops being a probability and becomes a property of the system. Fail-closed delivery trades coverage for a guarantee — the right trade for education.",
  {x:MW,y:3.25,w:11.4,h:1.3,fontFace:BODY,fontSize:17,color:ICE,lineSpacing:26});
function dstat(x,big,lbl,c){ s.addShape(p.ShapeType.roundRect,{x,y:4.9,w:3.85,h:1.6,rectRadius:0.1,fill:{color:DARKCARD},line:{color:"244047",width:1}});
  s.addText(big,{x:x+0.28,y:5.05,w:3.3,h:0.85,fontFace:HEAD,fontSize:40,bold:true,color:c});
  s.addText(lbl,{x:x+0.3,y:5.9,w:3.3,h:0.5,fontFace:BODY,fontSize:12.5,color:"9FB2B4",valign:"top"}); }
dstat(MW,"100%","of delivered problems verified correct",GREEN);
dstat(4.74,"6","explicit, closed failure codes",TEAL);
dstat(8.78,"0","wrong problems reach students","F0935B");
s.addNotes("Correctness becomes a property of the system, not a probability.");

/* 14 LIMITATIONS */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Limitations");
title(s,"Where the system stops — stated plainly.",{size:29});
const lim=[["Weak-model ceiling.","Even with the loop, an 8B model reaches only 43% delivery — physics trig/multi-step templates (torque, incline, projectile) stay near 0% because the model computes sin/cos wrong, not because the system fails. The loop amplifies capability; it can't manufacture it. Fail-closed refuses rather than lowering the bar."],
  ["Physics difficulty granularity.","Each physics skill maps to one fixed-formula template, so a skill occupies one difficulty bin; the domain spans 1–5 across skills, not within one."],
  ["Lightweight student model.","Mastery is an exponential-moving-average tracer, not Bayesian Knowledge Tracing or IRT."],
  ["No learning data yet.","Results establish generation reliability; learning outcomes are designed but not yet measured."]];
let ly=2.5;
lim.forEach(l=>{ s.addShape(p.ShapeType.ellipse,{x:MW,y:ly+0.04,w:0.28,h:0.28,fill:{color:TEAL}});
  s.addText([{text:l[0]+"  ",options:{bold:true,color:INK}},{text:l[1],options:{color:MUTED}}],{x:MW+0.55,y:ly-0.1,w:11.3,h:0.95,fontFace:BODY,fontSize:15,lineSpacing:21,valign:"top"}); ly+=1.08; });
s.addNotes("Stating limits proactively is a strength: weak-model ceiling, physics granularity, EMA student model, no human data yet.");

/* 15 FUTURE WORK */
s=p.addSlide(); bg(s,PAPER);
eyebrow(s,"Future Work");
title(s,"From reliable generation to measured learning.",{size:29});
const fut=[["Within-subject pilot study.","Isomorphic pre/post tests to estimate learning-gain effect sizes from verified, personalized practice."],
  ["Multi-step physics templates.","Problems whose single template spans several difficulty bins; multi-body systems and rotational-energy conservation."],
  ["Richer student model.","Swap the EMA tracer for BKT/IRT behind the existing interface."],
  ["Full cross-model benchmark.","A funded, large-sample GPT / Gemini / DeepSeek sweep to complete the architecture-vs-scale comparison."]];
let fy=2.5;
fut.forEach(f=>{ s.addShape(p.ShapeType.ellipse,{x:MW,y:fy+0.04,w:0.28,h:0.28,fill:{color:AMBER}});
  s.addText([{text:f[0]+"  ",options:{bold:true,color:INK}},{text:f[1],options:{color:MUTED}}],{x:MW+0.55,y:fy-0.1,w:11.3,h:0.95,fontFace:BODY,fontSize:15,lineSpacing:21,valign:"top"}); fy+=1.08; });
s.addNotes("Next: the learning-outcomes pilot, multi-step physics, a BKT/IRT student model, and a funded cross-model benchmark.");

/* 16 CLOSE */
s=p.addSlide(); bg(s,DARK);
eyebrow(s,"Regenerate-Until-Valid",MW,1.0,TEAL);
s.addText("Correctness you can verify.",{x:MW,y:1.5,w:11.6,h:1.3,fontFace:HEAD,fontSize:48,bold:true,color:PAPER});
dstat(MW,"21→43%","validity, single-shot → closed-loop",TEAL);
s.addShape(p.ShapeType.roundRect,{x:4.74,y:4.9,w:3.85,h:1.6,rectRadius:0.1,fill:{color:DARKCARD},line:{color:"244047",width:1}});
s.addText("518",{x:5.02,y:5.05,w:3.3,h:0.85,fontFace:HEAD,fontSize:40,bold:true,color:"F0935B"});
s.addText("errors intercepted (Llama n=95)",{x:5.04,y:5.9,w:3.3,h:0.5,fontFace:BODY,fontSize:12.5,color:"9FB2B4"});
s.addShape(p.ShapeType.roundRect,{x:8.78,y:4.9,w:3.85,h:1.6,rectRadius:0.1,fill:{color:DARKCARD},line:{color:"244047",width:1}});
s.addText("0",{x:9.06,y:5.05,w:3.3,h:0.85,fontFace:HEAD,fontSize:40,bold:true,color:GREEN});
s.addText("reached a student",{x:9.08,y:5.9,w:3.3,h:0.5,fontFace:BODY,fontSize:12.5,color:"9FB2B4"});
s.addText("Anay Parikh · Yuki Tanaka · Isabella Chen · Faiza Fatima · Ashna Munavalli    —    Advisor: Suresh Subramaniam",
  {x:MW,y:6.85,w:12,h:0.4,fontFace:BODY,fontSize:12.5,color:"8FA2A4"});
s.addNotes("Close on the guarantee: 21 to 43 percent validity on the finalized Llama n=95 run, 518 errors intercepted, zero reaching a student.");

p.writeFile({ fileName: "/private/tmp/claude-502/-Users-anayparikh-mlg-project-work/2d62bc14-713e-4d6e-94b3-cb1fbd14d855/scratchpad/Regenerate-Until-Valid-v2.pptx" })
 .then(f=>console.log("WROTE", f));
