from __future__ import annotations

from fastapi.testclient import TestClient

from snapims import db
from snapims.web.app import app


def _seed_minimal_batch(data_paths):
    db.initialize(data_paths.db_file, paths=data_paths)
    with db.transaction(data_paths.db_file) as connection:
        connection.execute(
            """INSERT INTO batches(
                   batch_id,source_fingerprint,source_folder,created_at,imported_at,
                   started,ended,status,item_count,product_photo_count,command_count,warning_count
               ) VALUES(?,?,?,?,?,1,1,'IMPORTED',1,0,0,0)""",
            ('OPFIRST-WEB','opf-web','/fixture',db.now(),db.now()),
        )
        connection.execute(
            """INSERT INTO items(
                   item_id,sku,batch_id,sequence,shelf,title,price_cents,
                   created_at,updated_at,working_source
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ('OPFIRST-WEB-001','OPFIRST-WEB-001','OPFIRST-WEB',1,'','',None,db.now(),db.now(),'IMPORT'),
        )
    return db.get_item(data_paths.db_file, 'OPFIRST-WEB-001')


def test_operator_first_routes_boot_and_blank_review_can_advance(data_paths):
    item = _seed_minimal_batch(data_paths)
    assert item is not None
    with TestClient(app) as client:
        for path in ('/search', '/data-sources', '/commit?batch_id=OPFIRST-WEB', '/review?batch_id=OPFIRST-WEB'):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code, response.text[:500])
        response = client.post(
            '/review/approve',
            data={
                'batch_id':'OPFIRST-WEB',
                'item_id':'OPFIRST-WEB-001',
                'title':'',
                'tag_ids':'',
                'revision':str(item['record_revision']),
            },
            follow_redirects=False,
        )
        assert response.status_code in {302,303}
    saved = db.get_item(data_paths.db_file, 'OPFIRST-WEB-001')
    assert saved is not None
    assert saved['review_status'] == 'DONE'
    assert saved['price_cents'] is None
    assert saved['title'] == ''


def test_operator_help_auto_and_palette_routes(data_paths):
    db.initialize(data_paths.db_file, paths=data_paths)
    with TestClient(app) as client:
        response = client.get('/api/operator-first/help-auto', params={'label':'Pause after current attempt','kind':'button','form_action':'/recognition/pause'})
        assert response.status_code == 200
        payload = response.json()
        assert payload['title'] == 'Pause after current attempt'
        response = client.get('/api/operator-first/palette', params={'q':'pricing'})
        assert response.status_code == 200
        groups = {group['label'] for group in response.json()['groups']}
        assert {'Items','Navigation','Settings','Help'} <= groups
