(() => {
    const panel = document.querySelector('[data-portfolio-mode]');
    if (!panel) return;
    const own = panel.dataset.portfolioMode === 'own';
    const mobile = matchMedia('(max-width: 760px)');
    const status = panel.querySelector('.pf-status');
    const button = panel.querySelector('.pf-refresh');
    const colors = ['#7ee4b2','#6ba9ed','#c0a0ee','#edbd7b','#e98eaf'];
    const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
    const signed = value => `${value > 0 ? '+' : ''}${won(value)}`;
    const node = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
    function render(data) {
        const p = data.portfolio;
        const holdings = [...p.holdings].sort((a,b) => b.value-a.value || a.club_num-b.club_num);
        const ratio = value => p.total ? value / p.total * 100 : 0;
        const put = (selector,text) => { panel.querySelector(selector).textContent=text; };
        put('.pf-total', won(p.total)); put('.pf-cash',won(p.cash)); put('.pf-stock-value',won(p.value));
        put('.pf-rank',`전교 ${data.user.rank.toLocaleString('ko-KR')}위`);
        put('.pf-profit',signed(p.profit)); put('.pf-rate',`(${p.cost ? (p.profit/p.cost*100).toFixed(2) : '0.00'}%)`);
        for (const selector of ['.pf-profit','.pf-rate']) { panel.querySelector(selector).classList.toggle('pf-down',p.profit<0); panel.querySelector(selector).classList.toggle('pf-up',p.profit>0); }
        put('.pf-count',`${holdings.length}개 종목`); put('.pf-stock-ratio',`${ratio(p.value).toFixed(1)}%`);
        const pieces = holdings.slice(0,4).map((h,i)=>({name:h.name,value:h.value,color:colors[i]}));
        if(holdings.length>4) pieces.push({name:'그 외 종목',value:holdings.slice(4).reduce((sum,h)=>sum+h.value,0),color:colors[4]});
        pieces.push({name:'현금',value:p.cash,color:'#526c64'});
        let cursor=0; const stops=[]; const legend=panel.querySelector('.pf-legend'); legend.replaceChildren();
        for(const piece of pieces){
            const percent=ratio(piece.value); stops.push(`${piece.color} ${cursor}% ${cursor+percent}%`); cursor+=percent;
            const li=node('li'), dot=node('i'); dot.style.background=piece.color; li.append(dot,node('span','',piece.name),node('b','',`${percent.toFixed(1)}%`)); legend.append(li);
        }
        const donut=panel.querySelector('.pf-donut'); donut.style.background=p.total?`conic-gradient(${stops.join(',')})`:'#30433a';
        donut.setAttribute('aria-label',pieces.map(x=>`${x.name} ${ratio(x.value).toFixed(1)}%`).join(', '));
        const list=panel.querySelector('.pf-holding-list'); list.replaceChildren();
        for(const item of holdings){
            const card=node('article','pf-holding'), top=node('div','pf-holding-top'), img=node('img');
            img.src=`/static/images/${item.club_num}.png`; img.alt=''; img.loading='lazy'; img.decoding='async'; img.width=38; img.height=38;
            img.addEventListener('error',()=>{img.src='/static/images/default_stock_logo.png';},{once:true});
            const name=node('div','pf-holding-name'), link=node('a','',item.name); link.href=`/buy?club=${item.club_num}&side=buy`;
            name.append(link,node('small','',`${item.quantity.toLocaleString('ko-KR')}주 보유 · ${item.category}`));
            top.append(img,name,node('span','pf-weight',`${ratio(item.value).toFixed(1)}%`));
            const metrics=node('div','pf-holding-metrics');
            for(const [label,value,sub,cls] of [['평가금액',won(item.value),`현재 매도가 ${won(item.price)}`,''],['평가손익',signed(item.profit),`${item.rate>0?'+':''}${item.rate.toFixed(2)}%`,item.profit<0?'pf-down':item.profit>0?'pf-up':'']]){
                const block=node('div');block.append(node('span','',label),node('strong',cls,value),node('small',cls,sub));metrics.append(block);
            }
            card.append(top,metrics);list.append(card);
        }
        if(!holdings.length){const empty=node('div','pf-empty','아직 보유한 주식이 없습니다.');if(own){const link=node('a','','첫 종목 살펴보기 →');link.href='/buy';empty.append(link);}list.append(empty);}
        const time=new Date(data.timestamp*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
        put('.pf-time',`${time} 시세 기준${data.catching_up?' · 시세 갱신 중':''}`);
        if(own){updateHeaderProfile({...data.user,clubName:data.user.club_name});panel.querySelector('.pf-intro').textContent=`${data.user.name}님의 투자, 한눈에 모아보기`;}
        status.hidden=true;panel.querySelector('.pf-content').hidden=false;
    }
    if(!own){try{render(JSON.parse(document.getElementById('member-portfolio-data').textContent));}catch(_){status.textContent='포트폴리오를 표시하지 못했습니다. 새로고침해주세요.';}return;}
    let loading=false;
    async function load(){
        if(loading||document.hidden||!mobile.matches)return;
        loading=true;button.disabled=true;
        try{const response=await fetch('/api/portfolio',{cache:'no-store',signal:AbortSignal.timeout(20000)});if(response.status===401){location.href='/auth/login';return;}const data=await response.json();if(!response.ok||!data.success)throw new Error();render(data);}
        catch(_){status.hidden=false;status.textContent='연결이 지연되고 있습니다. 잠시 후 다시 시도하거나 새로고침을 눌러주세요.';}
        finally{loading=false;button.disabled=false;}
    }
    button.addEventListener('click',load); mobile.addEventListener('change',load);document.addEventListener('visibilitychange',load);load();setInterval(load,30000);
})();
