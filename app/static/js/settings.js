(() => {
    const checkbox=document.getElementById('reduce-effects');
    try{checkbox.checked=localStorage.getItem('stockolon-reduce-motion')==='true';}catch(_){}
    checkbox.addEventListener('change',()=>{
        document.documentElement.classList.toggle('reduce-effects',checkbox.checked);
        try{localStorage.setItem('stockolon-reduce-motion',String(checkbox.checked));document.getElementById('settings-status').textContent='화면 설정을 저장했습니다.';}
        catch(_){document.getElementById('settings-status').textContent='이 브라우저에서는 저장할 수 없어 현재 화면에만 적용됩니다.';}
    });
})();
