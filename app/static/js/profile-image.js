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
    const editor = document.getElementById('photo-crop-editor');
    const canvas = document.getElementById('photo-crop-canvas');
    const zoom = document.getElementById('photo-zoom');
    const zoomValue = document.getElementById('photo-zoom-value');
    const cropReset = document.getElementById('photo-crop-reset');
    const zoomOut = document.getElementById('photo-zoom-out');
    const zoomIn = document.getElementById('photo-zoom-in');
    const smallPreview = document.createElement('canvas');
    smallPreview.width = smallPreview.height = 88;
    let current = null, selected = null, objectUrl = null, busy = false;
    let source = null, crop = null, drag = null, renderFrame = null;

    function draw(target) {
        const context = target.getContext('2d');
        context.clearRect(0, 0, target.width, target.height);
        context.imageSmoothingEnabled = true;
        context.imageSmoothingQuality = 'high';
        context.drawImage(source, crop.x, crop.y, crop.size, crop.size, 0, 0, target.width, target.height);
    }
    function renderCrop() {
        if (!source || !crop) return;
        draw(canvas);
        draw(smallPreview);
        preview.src = smallPreview.toDataURL('image/png');
        zoom.value = crop.zoom;
        zoomValue.textContent = `${crop.zoom.toFixed(2)}×`;
        zoom.setAttribute('aria-valuetext', `${crop.zoom.toFixed(2)}배`);
    }
    function scheduleRender() {
        if (renderFrame !== null) return;
        renderFrame = requestAnimationFrame(() => { renderFrame = null; renderCrop(); });
    }
    function setZoom(value) {
        if (busy || !crop) return;
        crop = PhotoCrop.zoom(crop, value);
        renderCrop();
    }

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
        editor.hidden = !selected;
        zoom.disabled = cropReset.disabled = zoomOut.disabled = zoomIn.disabled = busy;
        canvas.setAttribute('aria-disabled', String(busy));
        panel.setAttribute('aria-busy', String(busy));
    }
    function clearSelection() {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = null;
        selected = null;
        source = crop = drag = null;
        if (renderFrame !== null) cancelAnimationFrame(renderFrame);
        renderFrame = null;
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
                // Export the same source rectangle shown in the circular preview.
                // The server still validates and normalizes the resulting square image.
                const output = document.createElement('canvas');
                output.width = output.height = 512;
                draw(output);
                const blob = await new Promise(resolve => output.toBlob(resolve, 'image/png'));
                if (!blob) throw new Error('사진을 자르지 못했습니다. 다시 시도해주세요.');
                const body = new FormData();
                body.append('photo', blob, 'profile.png');
                options.body = body;
            }
            const response = await fetch('/api/profile-image', options);
            if (response.status === 401) { location.assign('/auth/login'); return; }
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message || '사진을 저장하지 못했습니다.');
            current = data;
            clearSelection();
            updateHeaderProfile({name: data.name, profileImg: data.image});
            document.dispatchEvent(new CustomEvent('profile-image-changed', {detail:{profileImg:data.image}}));
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
    input.addEventListener('change', async () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            input.value = '';
            message('5MB 이하의 JPG, PNG 또는 WebP 사진을 선택해주세요.', true);
            return;
        }
        busy = true;
        controls();
        message('편집할 사진을 불러오는 중입니다.');
        const nextUrl = URL.createObjectURL(file);
        try {
            const image = new Image();
            image.src = nextUrl;
            await image.decode();
            if (image.naturalWidth * image.naturalHeight > 20_000_000) {
                throw new Error('사진 해상도가 너무 큽니다. 2천만 화소 이하로 줄여주세요.');
            }
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = nextUrl;
            selected = file;
            source = image;
            crop = PhotoCrop.fit(image.naturalWidth, image.naturalHeight);
            renderCrop();
            message('사진을 옮기고 확대해 원하는 부분을 맞춘 뒤 저장해주세요.');
        } catch (error) {
            URL.revokeObjectURL(nextUrl);
            input.value = '';
            message(error.name === 'EncodingError' ? '사진을 열지 못했습니다. 다른 사진을 선택해주세요.' : error.message, true);
        } finally {
            busy = false;
            controls();
            if (selected) canvas.focus({preventScroll: true});
        }
    });
    zoom.addEventListener('input', () => setZoom(Number(zoom.value)));
    zoomOut.addEventListener('click', () => setZoom(crop.zoom - .1));
    zoomIn.addEventListener('click', () => setZoom(crop.zoom + .1));
    cropReset.addEventListener('click', () => {
        if (!crop || busy) return;
        crop = PhotoCrop.fit(crop.width, crop.height);
        renderCrop();
    });
    canvas.addEventListener('pointerdown', event => {
        if (busy || !crop || drag || (event.pointerType === 'mouse' && event.button !== 0)) return;
        drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
        canvas.setPointerCapture(event.pointerId);
        canvas.classList.add('dragging');
    });
    canvas.addEventListener('pointermove', event => {
        if (busy || !drag || drag.id !== event.pointerId) return;
        crop = PhotoCrop.move(crop, event.clientX - drag.x, event.clientY - drag.y,
            canvas.getBoundingClientRect().width);
        drag.x = event.clientX;
        drag.y = event.clientY;
        scheduleRender();
    });
    const endDrag = () => { drag = null; canvas.classList.remove('dragging'); };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);
    canvas.addEventListener('lostpointercapture', endDrag);
    canvas.addEventListener('wheel', event => {
        if (busy || !crop) return;
        event.preventDefault();
        setZoom(crop.zoom * (event.deltaY > 0 ? .95 : 1.05));
    }, {passive: false});
    canvas.addEventListener('keydown', event => {
        if (busy || !crop) return;
        const step = event.shiftKey ? 20 : 5;
        const direction = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]}[event.key];
        if (direction) {
            event.preventDefault();
            crop = PhotoCrop.move(crop, ...direction, canvas.getBoundingClientRect().width);
            renderCrop();
        } else if (['+', '=', '-'].includes(event.key)) {
            event.preventDefault();
            setZoom(crop.zoom + (event.key === '-' ? -.1 : .1));
        }
    });
    save.addEventListener('click', () => { if (selected) requestPhoto('POST'); });
    cancel.addEventListener('click', () => { clearSelection(); message('사진 변경을 취소했습니다.'); });
    reset.addEventListener('click', () => requestPhoto('DELETE'));
    window.addEventListener('pagehide', () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
    requestPhoto();
})();
