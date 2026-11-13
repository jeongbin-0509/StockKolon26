// Use load events and embedded file data: some in-app browsers cannot decode blob URLs.
(() => {
    function readDataURL(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reader.onabort = () => reject(new Error('사진 파일을 읽지 못했습니다. 기기에 저장한 파일을 다시 선택해주세요.'));
            reader.readAsDataURL(file);
        });
    }
    function loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            const finish = error => {
                clearTimeout(timer);
                image.onload = image.onerror = null;
                if (error) reject(error); else resolve(image);
            };
            const timer = setTimeout(() => finish(new Error('사진을 여는 시간이 초과되었습니다. 다시 선택해주세요.')), 15000);
            image.onload = () => finish(image.naturalWidth && image.naturalHeight ? null : new Error('이미지 크기를 확인할 수 없습니다.'));
            image.onerror = () => finish(new Error('사진 형식을 해석하지 못했습니다.'));
            image.src = url;
        });
    }
    function validateSize(file) {
        if (!file.size) throw new Error('내용이 없는 파일입니다. 사진을 다시 저장한 뒤 선택해주세요.');
        if (file.size > 5 * 1024 * 1024) throw new Error('5MB 이하의 사진을 선택해주세요.');
    }
    async function open(file, prepare) {
        validateSize(file);
        let image;
        try {
            image = await loadImage(await readDataURL(file));
        } catch (_) {
            // The server checks actual file content; a missing or inaccurate MIME label is not fatal.
            const compatible = await prepare(file);
            image = await loadImage(await readDataURL(compatible));
        }
        if (image.naturalWidth * image.naturalHeight > 20_000_000) {
            throw new Error('사진 해상도가 너무 큽니다. 2천만 화소 이하로 줄여주세요.');
        }
        return image;
    }
    const api = {open};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof window !== 'undefined') window.PhotoSource = api;
})();
