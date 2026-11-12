"""Small, normalized avatars in the application's persistent private database."""
import hashlib
from io import BytesIO
import warnings
from threading import BoundedSemaphore

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.ranking_service import profile_key


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
_image_decode = BoundedSemaphore(1)


def normalize_image(raw):
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError('5MB 이하의 사진을 선택해주세요.')
    try:
        with _image_decode, warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError('사진 해상도가 너무 큽니다. 2천만 화소 이하로 줄여주세요.')
                source.load()
                source.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                picture = ImageOps.exif_transpose(source).convert('RGBA')
                picture = ImageOps.fit(picture, (256, 256), method=Image.Resampling.LANCZOS)
                # A new image strips EXIF, GPS and other uploaded metadata.
                clean = Image.new('RGBA', picture.size)
                clean.paste(picture)
                output = BytesIO()
                clean.save(output, format='WEBP', quality=85, method=4)
                data = output.getvalue()
                if len(data) > 128 * 1024:
                    raise ValueError('사진을 처리하지 못했습니다. 다른 사진을 선택해주세요.')
                return data
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ValueError('정상적인 JPG, PNG 또는 WebP 사진을 선택해주세요.') from None


class ProfileImages:
    def __init__(self, market):
        self.market = market

    def initialize(self):
        binary = 'BYTEA' if self.market.store.postgres else 'BLOB'
        with self.market.connection(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS profile_images ('
                       'user_id TEXT PRIMARY KEY, profile_key TEXT NOT NULL UNIQUE, '
                       f'revision TEXT NOT NULL, image {binary} NOT NULL, '
                       'CHECK(length(image) <= 131072))')
            if self.market.store.postgres:
                # Flask sessions authorize access; this table is never a browser Data API.
                db.execute('ALTER TABLE profile_images ENABLE ROW LEVEL SECURITY')
                db.execute('REVOKE ALL ON profile_images FROM PUBLIC')
                for role in ('anon', 'authenticated'):
                    if db.execute('SELECT 1 FROM pg_roles WHERE rolname=?', (role,)).fetchone():
                        db.execute(f'REVOKE ALL ON profile_images FROM {role}')

    def revisions(self, keys):
        keys = list(set(keys))
        if not keys:
            return {}
        with self.market.connection() as db:
            rows = db.execute('SELECT profile_key,revision FROM profile_images WHERE profile_key IN ('
                              + ','.join('?' for _ in keys) + ')', keys).fetchall()
        return {row['profile_key']: row['revision'] for row in rows}

    def save(self, user_id, raw):
        data = normalize_image(raw)
        revision = hashlib.sha256(data).hexdigest()
        with self.market.connection(write=True) as db:
            db.execute('INSERT INTO profile_images (user_id,profile_key,revision,image) VALUES (?,?,?,?) '
                       'ON CONFLICT (user_id) DO UPDATE SET revision=excluded.revision,image=excluded.image',
                       (str(user_id), profile_key(user_id), revision, data))
        return revision

    def remove(self, user_id):
        with self.market.connection(write=True) as db:
            db.execute('DELETE FROM profile_images WHERE user_id=?', (str(user_id),))

    def read(self, key, revision):
        with self.market.connection() as db:
            row = db.execute('SELECT image FROM profile_images WHERE profile_key=? AND revision=?',
                             (key, revision)).fetchone()
        return bytes(row['image']) if row else None
