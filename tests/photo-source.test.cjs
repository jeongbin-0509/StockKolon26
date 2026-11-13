const {test} = require('node:test');
const assert = require('node:assert/strict');
const PhotoSource = require('../app/static/js/photo-source.js');

function browser(t, results) {
    let urls = [];
    const OldImage = global.Image, OldReader = global.FileReader;
    global.FileReader = class {
        readAsDataURL(file) {
            queueMicrotask(() => { this.result = file.url; this.onload(); });
        }
    };
    global.Image = class {
        decode() { throw new Error('Broken browser decode() must not be used'); }
        set src(url) {
            urls.push(url);
            const result = results.shift();
            queueMicrotask(() => {
                if (!result) this.onerror();
                else { [this.naturalWidth,this.naturalHeight] = result; this.onload(); }
            });
        }
    };
    t.after(()=>{global.Image=OldImage;global.FileReader=OldReader;});
    return urls;
}

test('ordinary image opens with load events even when decode is unavailable', async t=>{
    const urls=browser(t,[[800,400]]);
    const image=await PhotoSource.open({size:200,url:'data:image/png;base64,test'},()=>{throw new Error('No upload needed');});
    assert.equal(image.naturalWidth,800);
    assert.deepEqual(urls,['data:image/png;base64,test']);
});
test('browser failure uses server conversion once and then loads its full image',async t=>{
    const urls=browser(t,[null,[600,800]]);
    let calls=0;
    const file={size:100,url:'data:image/jpeg;base64,original',type:''};
    const image=await PhotoSource.open(file,async original=>{
        assert.equal(original,file);calls++;
        return {url:'data:image/png;base64,converted'};
    });
    assert.equal(calls,1);assert.equal(image.naturalHeight,800);
    assert.equal(urls.length,2);
});
test('invalid or oversized files report actionable errors without repeated attempts',async t=>{
    browser(t,[null]);
    await assert.rejects(PhotoSource.open({size:0},()=>{}),/내용이 없는/);
    await assert.rejects(PhotoSource.open({size:6*1024*1024},()=>{}),/5MB/);
    await assert.rejects(PhotoSource.open({size:200,url:'bad'},async()=>{throw new Error('정상적인 JPG, PNG 또는 WebP 사진을 선택해주세요.');}),/JPG/);
});
test('oversized decoded dimensions do not bypass the pixel limit via conversion',async t=>{
    browser(t,[[5000,5000]]);
    await assert.rejects(PhotoSource.open({size:200,url:'large'},()=>{throw new Error('Do not convert oversized photos');}),/2천만 화소/);
});
