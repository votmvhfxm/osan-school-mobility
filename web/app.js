"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let data, segments = [], segmentError = false, map, layers = [];
const state = {page:"recommend", category:"walk", complex:null, school:null, mode:"walk", schoolLevel:"all", segment:0, complexQuery:""};
const copy = {recommend:["개선 위치 추천","통학 부담이 큰 곳부터, 개선이 필요한 위치를 살펴보세요."],commute:["우리 집 통학길","우리 단지에서 학교까지, 시간과 위험 구간을 함께 비교하세요."]};
function csv(text) {
  const rows=[]; let row=[],cell="",quote=false;
  text=text.replace(/^\uFEFF/,"");
  for(let i=0;i<text.length;i++){const c=text[i];if(quote){if(c==='"'&&text[i+1]==='"'){cell+='"';i++;}else if(c==='"')quote=false;else cell+=c;}else if(c==='"')quote=true;else if(c===","){row.push(cell);cell="";}else if(c==='\n'){row.push(cell);rows.push(row);row=[];cell="";}else if(c!=='\r')cell+=c;}
  if(cell||row.length){row.push(cell);rows.push(row);}const head=rows.shift()||[];
  return rows.filter(r=>r.length===head.length).map(r=>Object.fromEntries(head.map((h,i)=>[h,r[i]])));
}
const currentComplex=()=>data.complexes.find(c=>c.id===state.complex);
const result=()=>currentComplex()?.results[state.school];
const fmt=n=>Number.isFinite(Number(n))?Number(n).toFixed(1):"—";
const options=(items,value)=>items.map(([id,name])=>`<option value="${esc(id)}" ${id===value?"selected":""}>${esc(name)}</option>`).join("");
const visibleSchools=()=>data.schools.filter(s=>state.schoolLevel==="all"||s.school_level===state.schoolLevel);
const sortKorean=(a,b)=>String(a).localeCompare(String(b),"ko");
const sortedComplexes=()=>[...data.complexes].sort((a,b)=>sortKorean(a.name,b.name));
const compact=(value)=>String(value??"").toLocaleLowerCase("ko-KR").replace(/\s+/g,"");
const complexMatches=(query)=>{
  const matches=sortedComplexes().filter(c=>!query||compact(c.name).includes(compact(query)));
  return query?matches.slice(0,8):matches;
};
function selectors(school=false){
  const selected=currentComplex();
  const matches=complexMatches(state.complexQuery);
  return `<div class="field complex-picker"><label for="complexSearch">출발 단지</label><input id="complexSearch" class="complex-search" type="search" autocomplete="off" placeholder="단지명을 검색하세요" value="${esc(state.complexQuery)}" aria-autocomplete="list" aria-controls="complexList"><div id="complexList" class="complex-list" role="listbox" aria-label="출발 단지 목록">${matches.map(c=>`<button type="button" role="option" class="${c.id===state.complex?"selected":""}" aria-selected="${c.id===state.complex}" data-complex-option="${esc(c.id)}">${esc(c.name)}</button>`).join("")}</div>${selected?`<p class="field-hint">선택됨: ${esc(selected.name)}</p>`:""}</div>${school?`<label class="field">도착 학교<select id="schoolSelect">${options(visibleSchools().sort((a,b)=>sortKorean(a.name,b.name)).map(s=>[s.school_id,`${s.name} · ${s.school_level||"학교"}`]),state.school)}</select></label>`:""}`;
}
function tabs(items,active,attr){return `<div class="tabs">${items.map(([id,name])=>`<button ${attr}="${id}" class="${id===active?"active":""}" aria-pressed="${id===active}">${name}</button>`).join("")}</div>`;}
function render(){
  if(!data)return;
  $("pageTitle").textContent=copy[state.page][0];$("pageDesc").textContent=copy[state.page][1];
  document.querySelectorAll("[data-page]").forEach(b=>{if(b.dataset.page===state.page)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
  let html="";
  if(state.page==="recommend"){
    html=`<span class="pill">우선 살펴볼 곳</span><h2 class="panel-title">어디부터 바꾸면 좋을까요?</h2><p class="panel-lead">학생이 많이 지나는 길과 위험도가 높은 구간을 함께 보고, 예산을 먼저 써야 할 위치를 제안합니다.</p>${tabs([["walk","보행 환경"],["bus","버스정류장"],["school","학교 위치"]],state.category,"data-category")}`;
    if(state.category==="walk"){
      html+=`<p class="small">위험도와 통과 경로를 기준으로 정렬한 보행 개선 검토 지점입니다. 시설 종류와 설치 가능 여부는 현장 확인이 필요합니다.</p>`;
      if(segmentError)html+='<div class="notice">개선 검토 지점 데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.</div>';
      else if(!segments.length)html+='<div class="notice">등록된 개선 검토 지점이 없습니다.</div>';
      html+=segments.slice(0,12).map((s,i)=>`<button class="candidate ${i===state.segment?"selected":""}" data-segment="${i}" aria-pressed="${i===state.segment}"><div class="row"><strong>${esc(s["도로명"]||"도로명 미등록 구간")}</strong><span class="rank">${i+1}순위</span></div><div class="priority-meter"><i style="width:${Math.min(100,Number(s["우선점수"]||0)*8)}%"></i></div><div class="tags"><span>구간 ${esc(s["길이_m"])}m</span><span>위험도 ${esc(s["위험도"])}</span><span>통과 경로 ${esc(s["통과경로수"])}개</span></div><div class="small">${esc(s["관련단지"])}</div></button>`).join("");
      html+='<p class="small">통과 경로 수는 학생 수가 아닙니다. 표시 지점은 구간의 대표 위치입니다.</p>';
    }else if(state.category==="bus"){
      const items=data.meta.bus_recommendations||[];
      html+=`<div class="notice">노선·배차 원본 없이 정류장 좌표와 직선거리 기반으로 계산한 <strong>배치 검토용 추정</strong>입니다. 실제 노선 신설·이전 결정 전 현장 확인이 필요합니다.</div>`;
      html+=items.length?items.map((x,i)=>`<div class="candidate"><div class="row"><strong>${i+1}. ${esc(x.stop)}</strong><span class="rank">${esc(x.distance_m)}m</span></div><div class="small">${esc(x.complex)} · ${esc(x.reason)}</div></div>`).join(""):'<div class="empty"><h3>정류장 좌표가 없습니다</h3><p>정류장 데이터를 먼저 수집해야 합니다.</p></div>';
    }else{
      const items=data.meta.school_recommendations||[];
      html+=`<div class="notice">새 학교의 확정 위치가 아니라, 현재 단지·학교 통학 부담을 바탕으로 산출한 <strong>학교 후보 검토 권역</strong>입니다. 부지·학생 수요·수용 여력 확인이 필요합니다.</div>`;
      html+=items.length?items.map((x,i)=>`<div class="candidate"><div class="row"><strong>${i+1}. ${esc(x.area)} 권역</strong><span class="rank">부담 ${fmt(x.mean_index)}</span></div><div class="small">${esc(x.reason)}</div></div>`).join(""):'<div class="empty"><h3>학교 분석 데이터가 없습니다</h3><p>통학 계산 결과를 먼저 생성해야 합니다.</p></div>';
    }
  }else{
    html=`<h2 class="panel-title">우리 단지에서 학교까지</h2><p class="panel-lead">출발 단지를 바꾸면 학교별 통학 부담과 안전 경로가 즉시 업데이트됩니다.</p>${selectors()}${tabs([["all","전체 학교"],["초등학교","초등학교"],["중학교","중학교"]],state.schoolLevel,"data-level")}${tabs([["walk","도보"],["bus","버스"]],state.mode,"data-mode")}`;
    if(state.mode==="bus"&&!data.meta.bus_available)html+=`<div class="notice">${data.meta.bus_estimate_available?`노선·배차 원본이 없어 최근접 정류장과 거리 기반으로 계산한 추정값입니다. 실제 버스 시간표가 아닙니다.`:"버스 정류장 데이터 수집 전입니다."}</div>`;
    const rankedSchools=visibleSchools().map(s=>({school:s,walk:currentComplex().results[s.school_id]?.[state.mode]})).sort((a,b)=>{
      const at=Number(a.walk?.time_min),bt=Number(b.walk?.time_min);
      if(Number.isFinite(at)&&Number.isFinite(bt))return at-bt;
      return Number.isFinite(at)?-1:Number.isFinite(bt)?1:sortKorean(a.school.name,b.school.name);
    });
    html+=rankedSchools.map(({school:s,walk:w})=>w?`<button class="school-card ${state.school===s.school_id?"selected":""}" data-school="${esc(s.school_id)}" aria-pressed="${state.school===s.school_id}"><div class="row"><strong>${esc(s.name)}</strong><span class="school-level">${esc(s.school_level||"학교")}</span><span class="score">${fmt(w.time_min)}<small>분</small></span></div><div class="tags"><span>부담 지수 ${fmt(w.index)}</span><span>위험 구간 ${esc(w.risk_len_m)}m</span></div>${state.mode==="bus"?`<div class="small">${esc(w.route_name)}번 · 대기 ${fmt(w.wait_min)}분 · 승차 ${fmt(w.ride_min)}분</div>`:""}</button>`:`<div class="notice">${esc(s.name)} · ${data.meta.bus_available?"계산된 버스 경로 없음":"버스 데이터 미수집"}</div>`).join("");
    html+='<p class="small">단지 중심점 기준 추정입니다. 실제 출입구와 보행 환경에 따라 시간이 달라질 수 있습니다.</p>';
  }
  $("panel").innerHTML=html;bindPanel();drawMap();
}
function bindPanel(){
  for(const [attr,key] of [["category","category"],["mode","mode"],["school","school"],["level","schoolLevel"],["segment","segment"]])document.querySelectorAll(`[data-${attr}]`).forEach(b=>b.onclick=()=>{state[key]=key==="segment"?Number(b.dataset[attr]):b.dataset[attr];if(key==="schoolLevel"){const first=visibleSchools()[0];state.school=first?.school_id||null;}render();});
  if($("complexList"))$("complexList").onclick=e=>{
    const button=e.target.closest("[data-complex-option]");
    if(!button)return;
    state.complex=button.dataset.complexOption;
    state.complexQuery="";
    render();
  };
  if($("complexSearch")){
    $("complexSearch").oninput=e=>{
      state.complexQuery=e.target.value;
      const list=$("complexList");
      if(list)list.innerHTML=complexMatches(state.complexQuery).map(c=>`<button type="button" role="option" class="${c.id===state.complex?"selected":""}" aria-selected="${c.id===state.complex}" data-complex-option="${esc(c.id)}">${esc(c.name)}</button>`).join("");
    };
  }
  if($("schoolSelect"))$("schoolSelect").onchange=e=>{state.school=e.target.value;render();};
}
function scene(){
  const paths=[],points=[];
  const focused=state.page==="commute";
  const complexes=focused?data.complexes.filter(c=>c.id===state.complex):data.complexes;
  const schools=focused?data.schools.filter(s=>s.school_id===state.school):data.schools;
  complexes.forEach(c=>{const avg=Number(c.mean_index);points.push({lat:c.lat,lon:c.lon,label:c.name,id:c.id,color:$("burden").checked?(avg<33.3?"#46866d":avg<66.6?"#bd963c":"#c76b59"):"#7d9390",type:"complex"});});
  schools.forEach(s=>points.push({lat:s.lat,lon:s.lon,label:s.name,color:"#243f4a",type:"school"}));
  if(state.page==="recommend"&&state.category==="walk")segments.slice(0,12).forEach((s,i)=>points.push({lat:Number(s.lat),lon:Number(s.lon),label:`${i+1}. ${s["도로명"]}`,color:i===state.segment?"#bc453b":"#cb8476",type:"candidate",id:i}));
  if(state.page==="commute"){
    const w=result()?.[state.mode];
    if(w){if(w.path)paths.push({coords:w.path,color:"#3975bd"});(w.walk_paths||[]).forEach(coords=>paths.push({coords,color:"#3975bd",dash:true}));if(w.bus_path)paths.push({coords:w.bus_path,color:"#7958b6"});(w.risk_segments||[]).forEach(s=>paths.push({coords:s.coords,color:"#cc6255"}));}
  }
  return {paths,points:points.filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon))};
}
function selectPoint(p){if(p.type==="candidate"){state.segment=p.id;render();}else if(p.type==="complex"){state.complex=p.id;if(state.page==="recommend")navigate("commute");else render();}}
function drawMap(){
  const {paths,points}=scene();$("mapTitle").textContent=state.page==="recommend"?"통학 부담과 개선 검토 지점":"우리 단지의 통학 경로";
  if(map){
    layers.forEach(l=>l.setMap(null));layers=[];const bounds=new naver.maps.LatLngBounds(points[0] ? new naver.maps.LatLng(points[0].lat,points[0].lon) : map.getCenter(), points[0] ? new naver.maps.LatLng(points[0].lat,points[0].lon) : map.getCenter());
    for(const p of points){const el=document.createElement("button");el.className="map-pin"+(p.type==="school"?" school":"");el.textContent=p.type==="complex"?p.label.replace(/^오산세교2 /,""):p.label;el.style.background=p.color;if(state.page==="recommend"&&state.category==="walk"&&!(p.type==="candidate"&&p.id===state.segment))el.style.opacity=".4";el.onclick=()=>selectPoint(p);const pos=new naver.maps.LatLng(p.lat,p.lon);bounds.extend(pos);const o=new naver.maps.Marker({position:pos,icon:{content:el,anchor:new naver.maps.Point(0,0)},zIndex:p.type==="candidate"?(p.id===state.segment?8:4):2});o.setMap(map);layers.push(o);}
    for(const p of paths){const path=p.coords.map(([a,b])=>new naver.maps.LatLng(a,b));path.forEach(pos=>bounds.extend(pos));const l=new naver.maps.Polyline({map,path,strokeColor:p.color,strokeWeight:5,strokeStyle:p.dash?"shortdash":"solid",strokeOpacity:.9});layers.push(l);}
    map.fitBounds(bounds,{top:80,right:60,bottom:60,left:60});return;
  }
  const coords=points.map(p=>[p.lat,p.lon]).concat(paths.flatMap(p=>p.coords));if(!coords.length)return;
  const width=Math.max(280,$("overview").clientWidth),height=Math.max(300,$("overview").clientHeight);$("overview").setAttribute("viewBox",`0 0 ${width} ${height}`);
  const lat0=Math.min(...coords.map(p=>p[0])),lat1=Math.max(...coords.map(p=>p[0]));const lon0=Math.min(...coords.map(p=>p[1])),lon1=Math.max(...coords.map(p=>p[1]));const cos=Math.cos((lat0+lat1)/2*Math.PI/180);const scale=Math.min((width-100)/Math.max((lon1-lon0)*cos,.001),(height-130)/Math.max(lat1-lat0,.001));
  const xy=(lat,lon)=>[width/2+(lon-(lon0+lon1)/2)*cos*scale,(height-40)/2-(lat-(lat0+lat1)/2)*scale];
  let html='<text x="30" y="35" fill="#789184" font-size="12">N ↑</text>';
  html+=paths.map(p=>`<polyline points="${p.coords.map(([a,b])=>xy(a,b).join(",")).join(" ")}" fill="none" stroke="${p.color}" stroke-width="4" ${p.dash?'stroke-dasharray="7 6"':""} opacity=".85"/>`).join("");
  html+=points.map((p,i)=>{const [x,y]=xy(p.lat,p.lon),candidate=p.type==="candidate",selected=candidate&&p.id===state.segment;const showLabel=p.type==="school"||(p.type==="complex"&&p.id===state.complex);const opacity=state.page==="recommend"&&state.category==="walk"&&!selected?".4":"1";return `<g data-point="${i}" tabindex="0" role="button" aria-label="${esc(p.label)}" style="cursor:pointer;opacity:${opacity}"><title>${esc(p.label)}</title>${selected?`<circle cx="${x}" cy="${y}" r="21" fill="#cc625522"/>`:""}<circle cx="${x}" cy="${y}" r="${candidate?10:7}" fill="${p.color}" stroke="white" stroke-width="2"/>${candidate?`<text x="${x}" y="${y+4}" text-anchor="middle" fill="white" font-size="10">${p.id+1}</text>`:showLabel?`<text x="${x>width*.6?x-12:x+12}" y="${y+4}" text-anchor="${x>width*.6?"end":"start"}" fill="#243f4a" font-size="11" paint-order="stroke" stroke="#edf2ed" stroke-width="3">${esc(p.label.replace(/^오산세교2 /,""))}</text>`:""}</g>`;}).join("");
  $("overview").innerHTML=html;$("overview").querySelectorAll("[data-point]").forEach(g=>{const activate=()=>selectPoint(points[Number(g.dataset.point)]);g.onclick=activate;g.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();activate();}};});
}
function navigate(page){if(!copy[page])page="commute";state.page=page;history.replaceState(null,"",`#${page}`);render();}
function surveyUrl(){try{const u=new URL(window.SURVEY_FORM_URL);return u.protocol==="https:"&&(u.hostname==="forms.gle"||(u.hostname==="docs.google.com"&&u.pathname.startsWith("/forms/")))?u.href:null;}catch{return null;}}
$("surveyButton").onclick=()=>{const url=surveyUrl();if(window.SURVEY_ENABLED===true&&url)window.open(url,"_blank","noopener,noreferrer");else $("surveyDialog").showModal();};
$("methodButton").onclick=()=>$("methodDialog").showModal();
document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>navigate(b.dataset.page));
window.addEventListener("hashchange",()=>navigate(location.hash.slice(1)));
window.addEventListener("resize",()=>{if(data&&!map)drawMap();});
$("burden").onchange=()=>{if(data)drawMap();};
function mapFallback(message){
  layers.forEach(layer=>layer.setMap(null));layers=[];
  if(map){map.destroy();map=null;}
  $("naverMap").style.display="none";$("overview").style.display="block";
  $("mapStatus").textContent=message;
  if(data)drawMap();
}
async function initMap(){
  const key=String(window.NAVER_MAP_CLIENT_ID||"").trim();
  if(!key){mapFallback("좌표 기반 경로 개요 · 네이버 지도 연결 전 · 배경지도/축척 안내 없음");return;}
  let failed=false;
  try{
    await new Promise((resolve,reject)=>{
      const fail=message=>{failed=true;clearTimeout(timer);mapFallback(message);reject(new Error(message));};
      const timer=setTimeout(()=>fail("네이버 지도 연결 시간 초과 · 좌표 기반 개요를 표시합니다."),12000);
      window.navermap_authFailure=()=>fail("네이버 지도 인증 실패 · Client ID·등록 URL·이용 한도를 확인해 주세요.");
      const script=document.createElement("script");
      script.src=`https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(key)}`;
      script.onload=()=>{clearTimeout(timer);if(failed)return;if(!window.naver?.maps?.Map){fail("네이버 지도 SDK를 확인해 주세요.");return;}resolve();};
      script.onerror=()=>fail("네이버 지도 연결 실패 · 좌표 기반 개요를 표시합니다.");
      document.head.appendChild(script);
    });
    if(failed)return;
    $("naverMap").style.display="block";
    map=new naver.maps.Map($("naverMap"),{center:new naver.maps.LatLng(data.complexes[0].lat,data.complexes[0].lon),zoom:14,zoomControl:true,zoomControlOptions:{position:naver.maps.Position.TOP_RIGHT}});
    $("overview").style.display="none";
    $("mapStatus").textContent="";
    drawMap();
    new ResizeObserver(()=>{if(map){map.setSize(new naver.maps.Size($("naverMap").clientWidth,$("naverMap").clientHeight));drawMap();}}).observe($("naverMap"));
  }catch{if(!failed)mapFallback("네이버 지도 연결을 확인해 주세요. 좌표 기반 개요를 표시합니다.");}
}
(async()=>{
  try{
    const r=await fetch("../data/index.json?v=20261016",{cache:"no-store"});if(!r.ok)throw new Error("통학 데이터 응답 오류");data=await r.json();if(!data.complexes?.length||!data.schools?.length)throw new Error("통학 데이터가 비어 있습니다");
    try{const sr=await fetch("../data/priority_segments.csv?v=20261016",{cache:"no-store"});if(!sr.ok)throw new Error();segments=csv(await sr.text());}catch{segmentError=true;}
    state.complex=data.complexes[0].id;state.school=data.schools[0].school_id;
    $("coverage").textContent=`${data.complexes.length}개 단지 · ${data.schools.length}개 학교`;
    $("riskCount").textContent=`${segments.length || "—"}개`;
    $("schoolCount").textContent=`${data.schools.length}곳`;
    $("dataStatus").textContent=`${data.meta.risk_model==="rule"?"규칙 기반 위험도":"계산된 위험도"} · ${data.meta.bus_available?"버스 경로 연결":data.meta.bus_stop_count?`정류장 ${data.meta.bus_stop_count}곳 수집`:"버스 데이터 수집 전"}`;
    if(window.SURVEY_ENABLED===true&&surveyUrl()){$("surveyButton").setAttribute("aria-label","현장 의견조사 · 구글폼 새 창");$("surveyButton").title="현장 의견조사 · 구글폼 새 창";$("surveyButton").querySelector(".pending-dot").hidden=true;}
    navigate(location.hash.slice(1)||"commute");await initMap();
  }catch(e){$("panel").innerHTML=`<h2>데이터를 불러오지 못했어요</h2><p>${esc(e.message)}</p><p class="small">서버 실행 상태와 data/index.json을 확인한 뒤 새로고침해 주세요.</p>`;$("mapStatus").textContent="통학 데이터 연결 필요";$("dataStatus").textContent="데이터 연결 오류";}
})();
