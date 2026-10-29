function updateHeaderProfile(user) {
    if (!user) return;
    const avatar = document.querySelector('.user-avatar img');
    const name = document.querySelector('.user-name');
    if (avatar && user.profileImg) {
        avatar.src = user.profileImg;
        avatar.alt = user.clubName ? `${user.clubName} 로고` : '기본 프로필 이미지';
    }
    if (name && (user.name || user.username)) name.textContent = `${user.name || user.username}님`;
}

if (document.currentScript.dataset.autoload === 'true') {
    fetch('/api/profile-data')
        .then(response => response.ok ? response.json() : null)
        .then(data => { if (data && data.success) updateHeaderProfile(data.user); })
        .catch(() => {});
}
