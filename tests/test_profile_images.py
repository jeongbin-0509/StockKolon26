import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import create_app
from app.services.database import DatabaseError
from app.services.profile_images import MAX_UPLOAD_BYTES, ProfileImages, normalize_image
from app.services.ranking_service import profile_key


def picture(color='red', fmt='PNG', size=(400, 200)):
    output = io.BytesIO()
    Image.new('RGB', size, color).save(output, format=fmt)
    return output.getvalue()


class ProfileImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'photo-test',
            'MARKET_DATABASE': str(Path(self.tmp.name) / 'market.sqlite3')})
        self.client = self.app.test_client()
        self.service = self.app.extensions['profile_images']
        self.login('a')
        user = patch('app.routes.main.display_user', return_value={
            'name': '회원', 'club_id': 'c1', 'club_name': '세미콜론', 'cash': 100})
        user.start()
        self.addCleanup(user.stop)

    def login(self, user):
        with self.client.session_transaction() as session:
            session.clear()
            if user:
                session.update(user_id=user, admin_csrf='test-token')

    def upload(self, raw=None, **extra):
        data = {'photo': (io.BytesIO(raw if raw is not None else picture()), 'photo.png'), **extra}
        return self.client.post('/api/profile-image', data=data,
            headers={'X-CSRF-Token': 'test-token'}, content_type='multipart/form-data')

    def reset(self):
        return self.client.delete('/api/profile-image', headers={'X-CSRF-Token': 'test-token'})

    def test_default_upload_persistence_and_delete(self):
        original = self.client.get('/api/profile-image').json
        self.assertFalse(original['hasCustom'])
        self.assertEqual(original['image'], '/static/images/61.png')
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['hasCustom'])
        url = response.json['image']
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        served = self.client.get(url)
        self.assertEqual(served.mimetype, 'image/webp')
        self.assertEqual(Image.open(io.BytesIO(served.data)).size, (256, 256))
        self.assertEqual(served.headers['Cache-Control'], 'private, no-cache')
        self.assertEqual(served.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.client.get(url, headers={'If-None-Match': served.headers['ETag']}).status_code, 304)
        other_instance = ProfileImages(self.app.extensions['market'])
        self.assertEqual(other_instance.revisions([profile_key('a')]), self.service.revisions([profile_key('a')]))
        self.assertEqual(self.client.get('/api/header-profile').json['user']['profileImg'], url)
        reset = self.reset()
        self.assertEqual(reset.json['image'], '/static/images/61.png')
        self.assertFalse(reset.json['hasCustom'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_user_cannot_replace_or_delete_another_users_photo(self):
        a_url = self.upload().json['image']
        self.login('b')
        b_url = self.upload(picture('blue'), user_id='a').json['image']
        self.assertNotEqual(a_url, b_url)
        self.assertEqual(self.client.get(a_url).status_code, 200)
        self.reset()
        self.assertEqual(self.client.get(a_url).status_code, 200)
        self.assertEqual(self.client.get(b_url).status_code, 404)

    def test_auth_and_csrf_required(self):
        self.assertEqual(self.client.post('/api/profile-image').status_code, 403)
        self.assertEqual(self.client.delete('/api/profile-image').status_code, 403)
        url = self.upload().json['image']
        self.login(None)
        for method in ['get', 'post', 'delete']:
            self.assertEqual(getattr(self.client, method)('/api/profile-image').status_code, 401)
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_bad_files_do_not_overwrite_existing_photo(self):
        original = self.upload().json['image']
        for raw in [b'<svg onload="alert(1)"></svg>', b'not an image', b'']:
            self.assertEqual(self.upload(raw).status_code, 400)
        self.assertEqual(self.upload(b'x' * (MAX_UPLOAD_BYTES + 1)).status_code, 400)
        self.assertEqual(self.upload(b'x' * (MAX_UPLOAD_BYTES + 100000)).status_code, 413)
        self.assertEqual(self.client.get('/api/profile-image').json['image'], original)

    def test_revision_changes_and_old_file_disappears(self):
        old = self.upload().json['image']
        new = self.upload(picture('blue')).json['image']
        self.assertNotEqual(old, new)
        self.assertEqual(self.client.get(old).status_code, 404)
        self.assertEqual(self.client.get(new).status_code, 200)

    def test_all_public_and_own_profile_surfaces_use_custom_photo(self):
        url = self.upload().json['image']
        member = {'profile_key': profile_key('a'), 'name': '학생', 'club_name': '세미콜론',
                  'rank': 1, 'assets': 100, 'rate': 0, 'is_me': True}
        ranking = dict(me=member, members=[member], count=1, available=True,
                       timestamp=1, catching_up=False, portfolio={'holdings': []})
        with patch.object(self.app.extensions['ranking'], 'rankings', return_value=ranking):
            self.assertEqual(self.client.get('/api/index-data').json['profile']['profileImg'], url)
            self.assertEqual(self.client.get('/api/profile-data').json['user']['profileImg'], url)
            self.assertEqual(self.client.get('/api/portfolio').json['user']['profileImg'], url)
            self.assertEqual(self.client.get('/api/rankings').json['members'][0]['profileImg'], url)
            self.assertIn(url, self.client.get('/members/' + profile_key('a')).text)
        self.assertEqual(self.client.get('/profile-images/bad/bad.webp').status_code, 404)

    def test_database_failure_has_safe_message(self):
        with patch.object(self.service, 'save', side_effect=DatabaseError('secret password')):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)

    def test_exif_removed_and_supported_formats_normalized(self):
        source = Image.new('RGB', (100, 200), 'green')
        exif = Image.Exif()
        exif[270] = 'private metadata'
        raw = io.BytesIO()
        source.save(raw, format='JPEG', exif=exif)
        result = Image.open(io.BytesIO(normalize_image(raw.getvalue())))
        self.assertFalse(result.getexif())
        self.assertNotIn('exif', result.info)
        for fmt in ['JPEG', 'PNG', 'WEBP']:
            self.assertEqual(Image.open(io.BytesIO(normalize_image(picture(fmt=fmt)))).format, 'WEBP')

    def test_settings_has_upload_controls(self):
        response = self.client.get('/settings')
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="photo-file"', response.text)
        self.assertIn('동아리 로고로 되돌리기', response.text)

    def test_excessive_dimensions_rejected_before_decode(self):
        with patch('app.services.profile_images.MAX_PIXELS', 100):
            self.assertEqual(self.upload(picture(size=(11, 10))).status_code, 400)

    def prepare(self, raw):
        return self.client.post('/api/profile-image/prepare',
            data={'photo': (io.BytesIO(raw), 'image.jpg')}, headers={'X-CSRF-Token':'test-token'})

    def test_editor_conversion_preserves_full_image_and_does_not_save(self):
        original = self.upload().json['image']
        for fmt in ['JPEG','PNG','WEBP']:
            response = self.prepare(picture(fmt=fmt, size=(800,400)))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/png')
            result = Image.open(io.BytesIO(response.data))
            self.assertEqual(result.size,(800,400))
            self.assertFalse(result.getexif())
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/api/profile-image').json['image'], original)

    def test_editor_conversion_applies_orientation_and_bounds_dimensions(self):
        raw = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'private metadata'
        Image.new('RGB',(3000,1500),'blue').save(raw,format='JPEG',exif=exif)
        response = self.prepare(raw.getvalue())
        result = Image.open(io.BytesIO(response.data))
        self.assertEqual(result.size,(1024,2048))
        self.assertFalse(result.getexif())
        self.assertNotIn(b'private metadata',response.data)

    def test_editor_conversion_rejects_invalid_files_and_requires_auth_csrf(self):
        for raw in [b'',b'not an image',b'<svg onload="alert(1)"></svg>']:
            self.assertEqual(self.prepare(raw).status_code,400)
        self.assertEqual(self.prepare(b'x'*(MAX_UPLOAD_BYTES+100000)).status_code,413)
        self.assertEqual(self.client.post('/api/profile-image/prepare').status_code,403)
        self.login(None)
        self.assertEqual(self.prepare(picture()).status_code,401)
