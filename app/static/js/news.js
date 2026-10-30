const newsPage = document.querySelector('.news-page');

async function checkLatestNews() {
    if (document.hidden) return;
    try {
        const response = await fetch('/api/news/latest', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
        if (!response.ok) return;
        const data = await response.json();
        if ((data.latest_id || '') !== newsPage.dataset.latestId) location.reload();
    } catch (_) {
        // Keep the existing articles visible and retry at the next check.
    }
}

setInterval(checkLatestNews, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkLatestNews(); });
