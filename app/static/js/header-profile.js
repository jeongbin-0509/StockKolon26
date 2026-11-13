function updateHeaderProfile(user) {
    if (!user) return;
    const avatar = document.querySelector('.user-avatar img');
    const name = document.querySelector('.user-name');
    if (avatar && user.profileImg) {
        avatar.src = user.profileImg;
        avatar.alt = '프로필 사진';
    }
    if (name && (user.name || user.username)) name.textContent = `${user.name || user.username}님`;
    if (user.cosmetics && window.StockCosmetics) {
        StockCosmetics.label(name, user.cosmetics);
    }
}

if (document.currentScript.dataset.autoload === 'true') {
    fetch('/api/header-profile')
        .then(response => response.ok ? response.json() : null)
        .then(data => { if (data && data.success) updateHeaderProfile(data.user); })
        .catch(() => {});
}


if (document.querySelector('.user-rank') && !document.getElementById('card-total-assets')) {
    let rankLoading = false;
    async function refreshMyRank() {
        if (rankLoading || document.hidden) return;
        rankLoading = true;
        const badge = document.querySelector('.user-rank');
        try {
            const response = await fetch('/api/my-rank', {cache:'no-store', signal:AbortSignal.timeout(15000)});
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error();
            badge.textContent = `전교 ${data.rank.toLocaleString('ko-KR')}위`;
            badge.title = `${data.count.toLocaleString('ko-KR')}명 중 · 같은 자산은 공동 순위`;
        } catch (_) {
            badge.textContent = '순위 확인 재시도 중';
        } finally { rankLoading = false; }
    }
    refreshMyRank();
    setInterval(refreshMyRank, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshMyRank(); });
}
