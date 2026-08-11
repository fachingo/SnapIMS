from pathlib import Path
from urllib.parse import urlparse, parse_qs

from snapims import db
from snapims.operator_first.taxonomy import normalize_automatic_tags, seed_approved_taxonomy, tag_id
from snapims.operator_first.pricing import ebay_sold_url, database_price_suggestion, autofill_database_price, pricing_badge
from snapims.operator_first.lifecycle import commit_preview, commit_batch
from snapims.operator_first.search import resolve_candidates, title_intelligence
from snapims.operator_first.help_registry import assert_help_coverage


def make_db(tmp_path: Path) -> Path:
    root=tmp_path/'SnapIMS-data'
    db_file=root/'database'/'inventory.sqlite3'
    db_file.parent.mkdir(parents=True)
    db.initialize(db_file)
    return db_file


def add_batch(db_file: Path, batch='B1'):
    with db.transaction(db_file) as c:
        c.execute("""INSERT INTO batches(batch_id,source_fingerprint,source_folder,created_at,imported_at,started,ended,status,item_count,product_photo_count,command_count,warning_count) VALUES(?,?,?,?,?,1,1,'IMPORTED',0,0,0,0)""",(batch,'fp-'+batch,'/'+batch,db.now(),db.now()))


def add_item(db_file: Path, item_id: str, seq: int, title='', price=None, batch='B1', edition='', distributor='', year=None, source='IMPORT'):
    with db.transaction(db_file) as c:
        c.execute("""INSERT INTO items(item_id,sku,batch_id,sequence,shelf,title,price_cents,edition,distributor,release_year,created_at,updated_at,working_source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(item_id,'SKU-'+item_id,batch,seq,'',title,price,edition,distributor,year,db.now(),db.now(),source))
        c.execute("UPDATE batches SET item_count=item_count+1 WHERE batch_id=?",(batch,))


def link_movie(db_file: Path, item_id: str, movie_id: str):
    with db.transaction(db_file) as c:
        c.execute("""INSERT INTO item_movie_links(item_id,movie_id,link_status,link_method,linked_at,updated_at) VALUES(?,?,'LINKED','TEST',?,?)""",(item_id,movie_id,db.now(),db.now()))


def test_closed_taxonomy_and_seed(tmp_path):
    db_file=make_db(tmp_path)
    chosen=normalize_automatic_tags(['Horror','1995','science fiction','vhs','arnold schwarzenegger','random'],limit=3)
    assert chosen == ('horror','science fiction','arnold schwarzenegger')
    changed=seed_approved_taxonomy(db_file)
    assert changed > 150
    definitions={row['canonical_label']: row for row in db.list_tag_definitions(db_file)}
    assert definitions['star trek']['ai_eligible'] == 1
    assert definitions['arnold schwarzenegger']['canonical_label'] == 'arnold schwarzenegger'
    assert definitions['horror']['tag_id'] == tag_id('horror')


def test_ebay_url_is_canada_sold_completed():
    url=ebay_sold_url('The Shining')
    assert url.startswith('https://www.ebay.ca/sch/i.html?')
    qs=parse_qs(urlparse(url).query)
    assert qs['_nkw']==['The Shining VHS']
    assert qs['LH_Complete']==['1'] and qs['LH_Sold']==['1']


def test_database_pricing_prefills_strong_identity_and_marks_database(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'OLD',1,'The Shining',1299,edition='standard',year=1980,source='BATCH_EDITOR')
    add_item(db_file,'NEW',2,'The Shining',None,edition='standard',year=1980)
    link_movie(db_file,'OLD','MOV-SHINING'); link_movie(db_file,'NEW','MOV-SHINING')
    suggestion=database_price_suggestion(db_file,'NEW')
    assert suggestion.applicable and suggestion.suggested_price_cents==1299
    autofill_database_price(db_file,'NEW')
    item=db.get_item(db_file,'NEW')
    assert item['price_cents']==1299
    assert item['working_source']=='PRICING_DATABASE'
    assert pricing_badge(db_file,item)=='DATABASE'


def test_ambiguous_title_history_is_guidance_only(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'OLD',1,'The Mummy',999,edition='special edition')
    add_item(db_file,'NEW',2,'The Mummy',None,edition='standard')
    suggestion=database_price_suggestion(db_file,'NEW')
    assert not suggestion.applicable
    assert suggestion.previous_count==1
    autofill_database_price(db_file,'NEW')
    assert db.get_item(db_file,'NEW')['price_cents'] is None


def test_inventory_commit_is_advisory_and_idempotent(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'I1',1,'',None)
    preview=commit_preview(db_file,'B1')
    assert preview.items_with_warnings==1 and not preview.already_committed
    still_preview=commit_batch(db_file,'B1',force=False)
    assert not still_preview.already_committed
    committed=commit_batch(db_file,'B1',force=True)
    assert committed.already_committed
    committed2=commit_batch(db_file,'B1',force=True)
    assert committed2.already_committed
    with db.connect(db_file) as c:
        assert c.execute("SELECT COUNT(*) FROM inventory_events WHERE item_id='I1' AND event_type='INVENTORY_COMMITTED'").fetchone()[0]==1
        assert c.execute("SELECT status FROM batches WHERE batch_id='B1'").fetchone()[0]=='INVENTORY_COMMITTED'


def test_search_never_merges_alien_and_aliens(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'A1',1,'Alien',1299)
    add_item(db_file,'A2',2,'Aliens',999)
    add_item(db_file,'A3',3,'Alien 3',799)
    cands=resolve_candidates(db_file,'Alien')
    assert len(cands)==1 and cands[0].title=='Alien' and cands[0].local_count==1
    info=title_intelligence(db_file,'Alien')
    assert info['status']=='FOUND' and info['local_count']==1
    assert {row['title'] for row in info['records']}=={'Alien'}


def test_help_registry_covers_primary_new_controls():
    assert_help_coverage(['global.search','global.command_palette','review.title','review.tags','review.approve','review.reject','review.skip','review.edit_details','review.bulk_confidence','bulk.price','bulk.database_price','bulk.ebay_sold','pricing.queue','commit.commit_anyway','diagnostics.data_sources'])


def add_recognition(db_file: Path, item_id: str, title: str, confidence: float, tags=(), state='SELECTED') -> int:
    with db.transaction(db_file) as c:
        cur=c.execute("""INSERT INTO recognition_results(
            item_id,provider,source_kind,created_at,suggested_title,suggested_tag_ids_json,
            suggested_price_cents,suggested_discount_percent,confidence,pricing_source
        ) VALUES(?, 'mock','TEST',?,?,?,?,0,?,'NO_RECOGNITION_PRICING')""",
        (item_id,db.now(),title,__import__('json').dumps(list(tags)),None,confidence))
        rid=int(cur.lastrowid)
        c.execute("INSERT INTO recognition_attempt_states(recognition_result_id,state,selected_at,selected_by,updated_at) VALUES(?,?,?,?,?)",
                  (rid,state,db.now(),'test',db.now()))
        c.execute("INSERT INTO item_recognition_selection(item_id,recognition_result_id,selected_by,selected_at) VALUES(?,?,?,?)",
                  (item_id,rid,'test',db.now()))
        c.execute("UPDATE items SET recognition_status='COMPLETE' WHERE item_id=?",(item_id,))
        return rid


def test_operator_review_is_title_tags_only_and_blank_is_allowed(tmp_path):
    from snapims.operator_first.review import operator_approve
    db_file=make_db(tmp_path); add_batch(db_file); seed_approved_taxonomy(db_file)
    add_item(db_file,'I1',1,'',None)
    rid=add_recognition(db_file,'I1','The Shining',0.95,[tag_id('horror'),tag_id('psychological horror')])
    before=db.get_item(db_file,'I1')
    result=operator_approve(db_file,'I1',title='',tag_ids=[],expected_revision=before['record_revision'])
    assert result['review_status']=='DONE'
    assert result['title']=='' and result['price_cents'] is None and result['barcode']==''
    assert result['working_source']==before['working_source']  # Review must not rewrite unrelated price/source provenance.
    assert result['review']==1
    with db.connect(db_file) as c:
        # Blank operator title is an accepted review disposition, not a claim that AI title was accepted.
        assert c.execute("SELECT state FROM recognition_attempt_states WHERE recognition_result_id=?",(rid,)).fetchone()[0]=='SELECTED'


def test_operator_review_accepts_closed_tags_and_marks_attempt(tmp_path):
    from snapims.operator_first.review import operator_approve
    db_file=make_db(tmp_path); add_batch(db_file); seed_approved_taxonomy(db_file)
    add_item(db_file,'I1',1,'',None)
    rid=add_recognition(db_file,'I1','The Shining',0.96,[tag_id('horror')])
    item=db.get_item(db_file,'I1')
    result=operator_approve(db_file,'I1',title='The Shining',tag_ids=[tag_id('horror'),tag_id('psychological horror'), 'not-real'],expected_revision=item['record_revision'])
    assert result['title']=='The Shining'
    assert result['price_cents'] is None
    assert result['tags']=='horror, psychological horror'
    with db.connect(db_file) as c:
        assert c.execute("SELECT state FROM recognition_attempt_states WHERE recognition_result_id=?",(rid,)).fetchone()[0]=='ACCEPTED'


def test_reject_flags_and_bulk_approval_excludes_rejected_blank_failed(tmp_path):
    from snapims.operator_first.review import operator_reject, bulk_approval_preview, bulk_approve
    db_file=make_db(tmp_path); add_batch(db_file); seed_approved_taxonomy(db_file)
    for n in range(1,6): add_item(db_file,f'I{n}',n,'',None)
    add_recognition(db_file,'I1','Alien',0.99,[tag_id('science fiction')])
    add_recognition(db_file,'I2','Aliens',0.96,[tag_id('science fiction')])
    add_recognition(db_file,'I3','',0.99,[])
    add_recognition(db_file,'I4','The Thing',0.50,[tag_id('horror')])
    add_recognition(db_file,'I5','The Shining',0.99,[tag_id('horror')])
    i5=db.get_item(db_file,'I5'); operator_reject(db_file,'I5',expected_revision=i5['record_revision'])
    preview=bulk_approval_preview(db_file,'B1',0.95)
    assert preview.eligible_item_ids==('I1','I2')
    assert preview.excluded['blank']==1 and preview.excluded['below_threshold']==1 and preview.excluded['rejected']==1
    bulk_approve(db_file,'B1',0.95)
    assert db.get_item(db_file,'I1')['review_status']=='DONE'
    assert db.get_item(db_file,'I2')['review_status']=='DONE'
    assert db.get_item(db_file,'I5')['review_status']=='UNFINISHED'


def test_partial_search_discovers_separate_titles_without_aggregation(tmp_path):
    from snapims.operator_first.search import find_title_candidates
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'A1',1,'Alien',1299); add_item(db_file,'A2',2,'Aliens',999); add_item(db_file,'A3',3,'Alien 3',799)
    choices=find_title_candidates(db_file,'alie')
    assert {row['title'] for row in choices}=={'Alien','Aliens','Alien 3'}
    assert all(row['count']==1 for row in choices)


def test_database_pricing_ignores_legacy_ai_placeholder_price(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    # A legacy recognition-sourced 9.99 must never become trusted database pricing.
    add_item(db_file,'AI999',1,'The Shining',999,edition='standard',year=1980,source='AI_ACCEPTED')
    add_item(db_file,'HUMAN',2,'The Shining',1299,edition='standard',year=1980,source='BATCH_EDITOR')
    add_item(db_file,'NEW',3,'The Shining',None,edition='standard',year=1980)
    for item_id in ('AI999','HUMAN','NEW'):
        link_movie(db_file,item_id,'MOV-SHINING')
    suggestion=database_price_suggestion(db_file,'NEW')
    assert suggestion.applicable
    assert suggestion.suggested_price_cents==1299
    assert {row.item_id for row in suggestion.evidence}=={'HUMAN'}


def test_data_sources_are_read_only_and_truthful(tmp_path):
    from snapims.operator_first.data_sources import data_source_status
    db_file=make_db(tmp_path); add_batch(db_file); add_item(db_file,'I1',1,'Alien',None)
    rows=data_source_status(db_file)
    by_name={row['source']: row for row in rows}
    assert {'SnapIMS Inventory','Recognition','Catalog / Metadata','Pricing History','Shopify','eBay Pricing'} <= set(by_name)
    assert by_name['SnapIMS Inventory']['records']==1
    assert by_name['Shopify']['state'] in {'CONFIGURED','NOT CONFIGURED'}
    assert 'historical orders' in by_name['Shopify']['detail'].lower()


def test_title_search_20k_records_is_bounded_and_exact(tmp_path):
    import time
    db_file=make_db(tmp_path); add_batch(db_file)
    now=db.now()
    rows=[]
    for seq in range(1,20001):
        if seq == 19990:
            title='Alien'
        elif seq == 19991:
            title='Aliens'
        elif seq == 19992:
            title='Alien 3'
        else:
            title=f'Common Tape {seq:05d}'
        item_id=f'I{seq:05d}'
        rows.append((item_id,'SKU-'+item_id,'B1',seq,'',title,None,'','',None,now,now,'IMPORT'))
    with db.transaction(db_file) as c:
        c.executemany("""INSERT INTO items(item_id,sku,batch_id,sequence,shelf,title,price_cents,edition,distributor,release_year,created_at,updated_at,working_source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        c.execute("UPDATE batches SET item_count=? WHERE batch_id='B1'",(len(rows),))
    started=time.perf_counter()
    info=title_intelligence(db_file,'Alien')
    elapsed=time.perf_counter()-started
    assert info['status']=='FOUND' and info['local_count']==1
    assert {row['effective_title'] for row in info['records']}=={'Alien'}
    # Generous local-sandbox ceiling: guards accidental full Python/N+1 scans, not hardware speed.
    assert elapsed < 2.5, f'exact 20k title intelligence took {elapsed:.3f}s'


def test_database_pricing_treats_unknown_edition_against_special_edition_as_guidance(tmp_path):
    db_file=make_db(tmp_path); add_batch(db_file)
    add_item(db_file,'SPECIAL',1,'Alien',1999,edition='special edition',source='BATCH_EDITOR')
    add_item(db_file,'UNKNOWNED',2,'Alien',None,edition='',source='IMPORT')
    link_movie(db_file,'SPECIAL','MOV-ALIEN'); link_movie(db_file,'UNKNOWNED','MOV-ALIEN')
    suggestion=database_price_suggestion(db_file,'UNKNOWNED')
    assert not suggestion.applicable
    assert suggestion.previous_count==1
    assert suggestion.average_price_cents==1999
    assert db.get_item(db_file,'UNKNOWNED')['price_cents'] is None
