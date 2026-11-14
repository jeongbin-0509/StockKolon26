(() => {
    const root=document.querySelector('.mobile-movers'); if(!root)return;
    const mobile=matchMedia('(max-width: 760px)'); let loading=false;
    async function load(){
        if(!mobile.matches||document.hidden||loading)return;
        loading=true;
        try{
            const response=await fetch('/api/market/movers',{cache:'no-store',signal:AbortSignal.timeout(20000)});
            const data=await response.json();if(!response.ok||!data.success)throw new Error();
            for(const side of ['up','down']){
                const stock=data[side],card=root.querySelector(`[data-mover="${side}"]`),chart=card.querySelector('.mover-chart'),link=card.querySelector('.mover-link');
                card.querySelector('.mover-name').textContent=stock.name;
                card.querySelector('.mover-sub').textContent=stock.sub;
                const img=card.querySelector('img');img.src=stock.logo;
                const change=card.querySelector('.mover-change');change.textContent=stock.change==null?'—':`${stock.change>0?'+':''}${stock.change.toFixed(2)}%`;
                change.className=`mover-change ${side==='up'?'pf-up':'pf-down'}`;
                link.hidden=stock.club_num==null;if(stock.club_num!=null){link.href=`/buy?club=${stock.club_num}&side=buy`;link.setAttribute('aria-label',`${stock.name} 종목 보기`);}
                StockolonCharts.renderCandlestickChart(chart,{candles:stock.candles,compact:false,seriesKey:stock.club_num,timestamp:stock.timestamps?.at(-1),ariaLabel:`${stock.name} 최근 1시간 5분봉 차트`});
            }
            root.querySelector('.movers-status').hidden=true;
        }catch(_){const status=root.querySelector('.movers-status');status.hidden=false;status.textContent='등락 정보를 불러오지 못했습니다. 잠시 후 다시 갱신합니다.';}
        finally{loading=false;}
    }
    mobile.addEventListener('change',()=>{if(mobile.matches)load();else root.querySelectorAll('.mover-chart').forEach(StockolonCharts.disposeChart);});
    document.addEventListener('visibilitychange',load);load();setInterval(load,30000);
})();
