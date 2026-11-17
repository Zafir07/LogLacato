// Página que a própria placa serve (http://192.168.4.1 no Wi-Fi da placa, ou o IP dela
// na sua rede). Funciona sem internet e sem servidor: é o "modo offline" de consulta.
#pragma once
#include <pgmspace.h>

static const char PAGINA_HTML[] PROGMEM = R"HTML(<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LogLacto · T-Beam</title>
<style>
:root{--bg:#0f1720;--card:#17212c;--line:#243241;--txt:#e6edf3;--mut:#8b9bab;--ok:#3fb27f;--warn:#e0a83a;--bad:#e5534b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:520px;margin:0 auto;padding:16px}
header{display:flex;justify-content:space-between;align-items:center;color:var(--mut);font-size:13px}
.ph{text-align:center;font-size:64px;font-weight:700;letter-spacing:-1px;margin:8px 0 0}
.sub{text-align:center;color:var(--mut);margin-bottom:10px}
.bar{position:relative;height:12px;border-radius:6px;background:linear-gradient(90deg,#e5534b,#f0883e,#e0c33a,#3fb27f,#3a8ee0,#6e5ae0,#9a4fd1)}
.mk{position:absolute;top:-5px;width:4px;height:22px;background:#fff;border-radius:2px;transform:translateX(-2px);transition:left .4s}
.esc{display:flex;justify-content:space-between;color:var(--mut);font-size:12px;margin:4px 0 14px}
.link{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.chip{flex:1;min-width:150px;border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:13px}
.chip b{display:block;font-size:14px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.c small{color:var(--mut);display:block;font-size:12px}.c b{font-size:20px}.c i{font-style:normal;color:var(--mut);font-size:12px;display:block}
canvas{width:100%;height:110px;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-top:8px}
h3{font-size:13px;color:var(--mut);font-weight:500;margin:14px 0 0}
</style></head><body><main>
<header><span id="id">LogLacto</span><span id="fw"></span></header>
<div class="ph" id="ph">--</div><div class="sub" id="phs">aguardando leitura</div>
<div class="bar"><div class="mk" id="mk" style="left:50%"></div></div>
<div class="esc"><span>0 ácido</span><span>7</span><span>básico 14</span></div>
<div class="link">
 <div class="chip"><small>Painel LogLacto</small><b id="mq">--</b></div>
 <div class="chip"><small>Guardadas na placa</small><b id="fl">--</b></div>
</div>
<div class="grid">
 <div class="c"><small>Tensão Po</small><b id="pv">--</b><i id="pvs"></i></div>
 <div class="c"><small>GPS</small><b id="gp">--</b><i id="gps"></i></div>
 <div class="c"><small>Temperatura do ar</small><b id="ar">--</b></div>
 <div class="c"><small>Umidade do ar</small><b id="um">--</b></div>
 <div class="c"><small>Temperatura do leite</small><b id="le">--</b></div>
 <div class="c"><small>Bateria</small><b id="bt">--</b><i id="bts"></i></div>
 <div class="c"><small>Hora (UTC)</small><b id="hr">--</b><i id="hrs"></i></div>
 <div class="c"><small>Wi-Fi</small><b id="wf">--</b><i id="wfs"></i></div>
</div>
<h3>pH nos últimos 5 minutos</h3><canvas id="cv" width="600" height="160"></canvas>
</main><script>
const $=i=>document.getElementById(i),f=(v,d,u)=>v==null?'--':v.toFixed(d)+(u||'');
function desenhar(h){const c=$('cv'),x=c.getContext('2d'),W=c.width,H=c.height;x.clearRect(0,0,W,H);
 const v=h.filter(a=>a!=null);if(v.length<2)return;let lo=Math.min(...v),hi=Math.max(...v);if(hi-lo<0.2){lo-=0.1;hi+=0.1}
 x.strokeStyle='#3a8ee0';x.lineWidth=3;x.beginPath();let p=false;
 h.forEach((a,i)=>{if(a==null){p=false;return}const X=i/(h.length-1)*(W-20)+10,Y=H-10-(a-lo)/(hi-lo)*(H-20);p?x.lineTo(X,Y):x.moveTo(X,Y);p=true});x.stroke();
 x.fillStyle='#8b9bab';x.font='20px sans-serif';x.fillText(hi.toFixed(2),12,24);x.fillText(lo.toFixed(2),12,H-14)}
async function atualizar(){try{const d=await (await fetch('/api/agora')).json();
 $('id').textContent=d.id;$('fw').textContent='fw '+d.fw;
 $('ph').textContent=f(d.ph,2);
 $('phs').textContent=d.flags&2?'pH sem sinal (confira Po e sonda)':d.flags&4?'pH fora da faixa (calibre)':'pH do leite';
 $('phs').className='sub '+(d.flags&6?'bad':'');
 if(d.ph!=null)$('mk').style.left=(d.ph/14*100)+'%';
 $('pv').textContent=f(d.ph_v,3,' V');$('pvs').textContent=d.flags&2?'sem sinal':d.flags&4?'fora da faixa':'ok';
 $('gp').textContent=d.gps.fix?d.gps.sats+' satélites':'sem fix';$('gps').textContent=d.gps.fix?d.gps.lat.toFixed(5)+', '+d.gps.lon.toFixed(5):'procurando…';
 $('ar').textContent=f(d.ar,1,' °C');$('um').textContent=f(d.umid,0,' %');
 $('le').textContent=d.leite==null?(d.flags&8?'não ligada':'erro'):f(d.leite,1,' °C');
 $('bt').textContent=d.bat?d.bat.pct+' %':'--';$('bts').textContent=d.bat&&d.bat.carregando?'carregando':'';
 $('hr').textContent=d.hora?d.hora.substr(11,8):'--';$('hrs').textContent={ntp:'internet (NTP)',gps:'GPS',estimated:'estimada',none:'sem hora'}[d.fonte];
 $('wf').textContent=d.wifi.ok?d.wifi.rede:'desconectado';$('wfs').textContent=d.wifi.ok?d.wifi.ip+' · '+d.wifi.rssi+' dBm':'Wi-Fi da placa: 192.168.4.1';
 $('mq').textContent=d.mqtt.ok?'enviando ('+d.mqtt.broker+')':'offline';$('mq').className=d.mqtt.ok?'ok':'warn';
 $('fl').textContent=d.fila.pendentes+' de '+d.fila.capacidade;$('fl').className=d.fila.pendentes>d.fila.capacidade*0.8?'bad':d.fila.pendentes>1?'warn':'ok';
 desenhar(d.hist)}catch(e){$('mq').textContent='placa sem resposta';$('mq').className='bad'}}
atualizar();setInterval(atualizar,2000);
</script></body></html>)HTML";
