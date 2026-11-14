// Geometry is expressed in source-image pixels, independent of screen size.
(() => {
    const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
    function fit(width, height, zoom = 1, cx = width / 2, cy = height / 2) {
        zoom = clamp(zoom, 1, 4);
        const size = Math.min(width, height) / zoom;
        cx = clamp(cx, size / 2, width - size / 2);
        cy = clamp(cy, size / 2, height - size / 2);
        return {width, height, zoom, cx, cy, size, x: cx - size / 2, y: cy - size / 2};
    }
    function move(crop, dx, dy, displaySize) {
        return fit(crop.width, crop.height, crop.zoom,
            crop.cx - dx * crop.size / displaySize, crop.cy - dy * crop.size / displaySize);
    }
    function zoom(crop, value) {
        return fit(crop.width, crop.height, value, crop.cx, crop.cy);
    }
    const api = {fit, move, zoom};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof window !== 'undefined') window.PhotoCrop = api;
})();
