(() => {
    const panel = document.getElementById('profile-photo');
    if (!panel) return;
    const preview = document.getElementById('photo-preview');
    const input = document.getElementById('photo-file');
    const choose = document.getElementById('photo-choose');
    const save = document.getElementById('photo-save');
    const cancel = document.getElementById('photo-cancel');
    const reset = document.getElementById('photo-reset');
    const status = document.getElementById('photo-status');
    let current = null, selected = null, objectUrl = null, busy = false;

    function message(text, error = false) {
        status.textContent = text;
        status.classList.toggle('error', error);
    }
    function controls() {
        choose.disabled = busy || !current;
        reset.disabled = busy || !current?.hasCustom;
        save.disabled = busy;
        cancel.disabled = busy;
        save.hidden = cancel.hidden = !selected;
        panel.setAttribute('aria-busy', String(busy));
    }
    function clearSelection() {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = null;
        selected = null;
        input.value = '';
        if (current) preview.src = current.image;
        controls();
    }
    async function requestPhoto(method = 'GET') {
        if (busy) return;
        busy = true;
        controls();
        message(method === 'GET' ? '사진을 불러오는 중입니다.' : '사진을 저장하는 중입니다.');
        try {
            const options = {method, cache: 'no-store', signal: AbortSignal.timeout(30000),
                headers: {'X-CSRF-Token': panel.dataset.csrf}};
            if (method === 'POST') {
                const body = new FormData();
                body.append('photo', selected);
                options.body = body;
            }
            const response = await fetch('/api/profile-image', options);
            if (response.status === 401) { location.assign('/auth/login'); return; }
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || '사진을 저장하지 못했습니다.');
            current = data;
            clearSelection();
            updateHeaderProfile({name: data.name, profileImg: data.image});
            message(method === 'POST' ? '프로필 사진을 저장했습니다.' : method === 'DELETE'
                ? '동아리 로고로 변경했습니다.' : data.hasCustom ? '내 사진을 사용 중입니다.' : '동아리 로고를 사용 중입니다.');
        } catch (error) {
            message(error.name === 'TimeoutError' ? '응답이 지연되고 있습니다. 새로고침 후 확인해주세요.'
                : error.message || '사진을 처리하지 못했습니다. 다시 시도해주세요.', true);
        } finally {
            busy = false;
            controls();
        }
    }
    choose.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            input.value = '';
            message('5MB 이하의 JPG, PNG 또는 WebP 사진을 선택해주세요.', true);
            return;
        }
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        selected = file;
        objectUrl = URL.createObjectURL(file);
        preview.src = objectUrl;
        message('미리보기를 확인하고 저장을 눌러주세요. 사진은 가운데를 기준으로 맞춰집니다.');
        controls();
    });
    save.addEventListener('click', () => { if (selected) requestPhoto('POST'); });
    cancel.addEventListener('click', () => { clearSelection(); message('사진 변경을 취소했습니다.'); });
    reset.addEventListener('click', () => requestPhoto('DELETE'));
    window.addEventListener('pagehide', () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
    requestPhoto();
})();
