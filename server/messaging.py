"""Durable per-patient burst collection and ordered, at-most-once message parts."""
import json
import base64
from photo_meals import validate_analysis, prepare as prepare_photo
import re
import threading
import time
import uuid


def split_message(text, limit=420):
    parts = []
    # A paragraph is a conversational bubble, even when the total is short.
    for paragraph in re.split(r'\n\s*\n', text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > limit:
            cut = paragraph.rfind('. ', 0, limit)
            if cut >= limit // 3:
                cut += 1
            else:
                cut = paragraph.rfind(' ', 0, limit + 1)
            if cut < limit // 3:
                cut = limit
            parts.append(paragraph[:cut].rstrip())
            paragraph = paragraph[cut:].lstrip()
        if paragraph:
            parts.append(paragraph)
    # The model and deterministic formatter retain the 1800-char total limit.
    if len(parts) > 10:
        return split_message(text.replace('\n\n', ' '), limit)
    return parts


class Messaging:
    def __init__(self, store, quiet_seconds=8):
        self.store, self.db = store, store.db
        self.quiet_seconds = quiet_seconds
        self.changed = threading.Condition(store.lock)
        self.db.executescript('''CREATE TABLE IF NOT EXISTS inbox (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
          text TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
          CREATE INDEX IF NOT EXISTS inbox_pending ON inbox(patient_id,status,created);
          CREATE TABLE IF NOT EXISTS dispatch_parts (
          id TEXT PRIMARY KEY, dispatch_id TEXT NOT NULL REFERENCES dispatches(id),
          position INTEGER NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          provider_id TEXT, UNIQUE(dispatch_id,position));''')

        self.db.execute("""CREATE TABLE IF NOT EXISTS media_jobs (
          id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
          token TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL)""")

        self.db.execute("""CREATE TABLE IF NOT EXISTS dispatch_documents (
          dispatch_id TEXT PRIMARY KEY REFERENCES dispatches(id), part_id TEXT UNIQUE NOT NULL,
          payload BLOB NOT NULL)""")

        self.db.executescript("""CREATE TABLE IF NOT EXISTS photo_drafts (
          id TEXT PRIMARY KEY REFERENCES media_jobs(id), patient_id TEXT NOT NULL REFERENCES patients(id),
          caption TEXT NOT NULL DEFAULT '', analysis TEXT, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS photo_events (
          id TEXT PRIMARY KEY REFERENCES events(id), payload TEXT NOT NULL);""")

    def photo_context(self, event, patient_id):
        ids=event.get('_photoSources',[])
        if not isinstance(ids,list) or not 1<=len(ids)<=10:return None
        rows=[]
        for identifier in ids:
            if not isinstance(identifier,str) or len(identifier)>300:continue
            row=self.db.execute("SELECT q.* FROM photo_drafts q JOIN media_jobs m ON m.id=q.id WHERE q.id=? AND q.patient_id=? AND m.status='processed' AND q.analysis IS NOT NULL",(identifier,patient_id)).fetchone()
            if row:rows.append(row)
        if not rows:return None
        user_text='\n'.join(r['caption'] for r in rows)+'\n'+str(event.get('_photoUserText',''))[:4000]
        analyses=[json.loads(r['analysis']) for r in rows]
        if any(a.get('usable') is not True for a in analyses):
            return {'records':None,'failed':True,'userText':user_text,'sourceIds':[r['id'] for r in rows]}
        records=prepare_photo(analyses,user_text)
        return {'records':records,'userText':user_text,'sourceIds':[r['id'] for r in rows]}

    def begin_media(self, event, instance):
        """Admit once before downloading media or paying for interpretation."""
        with self.changed, self.db:
            if not isinstance(event, dict) or event.get('kind') != 'incoming' or event.get('instance') != instance:
                return {'approved': False}
            event_id = event.get('eventId', '')
            if not isinstance(event_id, str) or not 8 <= len(event_id) <= 300 or event.get('mediaType') not in ('image', 'audio'):
                return {'approved': False}
            patient = self.db.execute('SELECT * FROM patients WHERE phone=? AND verified=1 AND consent=1', (event.get('phone'),)).fetchone()
            if not patient or self.db.execute('SELECT id FROM media_jobs WHERE id=?', (event_id,)).fetchone():
                return {'approved': False}
            count = self.db.execute('SELECT count(*) FROM media_jobs WHERE patient_id=? AND created>?', (patient['id'], time.time()-300)).fetchone()[0]
            if count >= 10:
                return {'approved': False}
            token = str(uuid.uuid4())
            self.db.execute('INSERT INTO media_jobs VALUES(?,?,?,?,?)', (event_id, patient['id'], token, time.time(), 'processing'))
            self.db.execute("INSERT INTO inbox(id,patient_id,text,created,status) VALUES(?,?,?,?,'processing')", (event_id, patient['id'], '', time.time()))
            if event['mediaType']=='image':
                self.db.execute('INSERT INTO photo_drafts(id,patient_id,caption,created) VALUES(?,?,?,?)', (event_id,patient['id'],str(event.get('caption',''))[:1000],time.time()))
            self.changed.notify_all()
            return {'approved': True, 'mediaToken': token}

    def finish_media(self, body, instance):
        event = body.get('event', {})
        with self.changed, self.db:
            row = self.db.execute("""SELECT m.*,p.phone,p.verified,p.consent FROM media_jobs m
                JOIN patients p ON p.id=m.patient_id WHERE m.id=?""", (event.get('eventId'),)).fetchone()
            if (not row or row['status'] != 'processing' or row['token'] != body.get('mediaToken') or
                not row['consent'] or not row['verified'] or row['phone'] != event.get('phone') or event.get('instance') != instance or
                time.time()-row['created'] > 100):
                return {'action': 'ignore'}
            text = event.get('text')
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
                return {'action': 'ignore'}
            if 'photo' in body and self.db.execute('SELECT id FROM photo_drafts WHERE id=?',(row['id'],)).fetchone():
                try: analysis=validate_analysis(body.get('photo'))
                except (ValueError,TypeError): analysis={'usable':False,'items':[]}
                self.db.execute('UPDATE photo_drafts SET analysis=? WHERE id=? AND patient_id=?',(json.dumps(analysis),row['id'],row['patient_id']))
            self.db.execute("UPDATE media_jobs SET status='processed' WHERE id=?", (row['id'],))
            self.db.execute("UPDATE inbox SET text=?,status='pending' WHERE id=? AND status='processing'", (text.strip(), row['id']))
            self.changed.notify_all()
        return self.collect(event, instance, admitted=True)

    def collect(self, event, instance, admitted=False):
        if not isinstance(event, dict) or event.get('kind') != 'incoming':
            return self.store.ingest(event, instance)
        with self.changed:
            phone, text = event.get('phone'), event.get('text')
            if event.get('instance') != instance or not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
                return {'action': 'ignore'}
            p = self.db.execute('SELECT * FROM patients WHERE phone=? AND verified=1 AND consent=1', (phone,)).fetchone()
            prefs = self.store.coaching.get(p['id']) if p else None
            command = text.strip().upper()
            immediate = command in ('SAIR', 'PARAR', 'CANCELAR', 'STOP', 'CONFIRMAR', 'CANCELAR REGISTRO',
                                    'NAO QUERO PDF', 'NÃO QUERO PDF', 'CANCELAR PDF',
                                    'NAO QUERO MAIS PDF', 'NÃO QUERO MAIS PDF', 'CANCELAR GUIA',
                                    'PARAR LEMBRETES', 'CANCELAR LEMBRETES', 'PARAR LEMBRETES DE ÁGUA',
                                    'CANCELAR LEMBRETES DE ÁGUA', 'ALTERAR LEMBRETES', 'ATIVAR LEMBRETES') or re.fullmatch(r'\d{6}', command)
            if not p or not prefs or prefs['stage'] != 'done' or immediate:
                if admitted:
                    self.db.execute("UPDATE inbox SET status='consumed' WHERE id=? AND status='pending'", (event.get('eventId'),))
                if phone and command in ('SAIR', 'PARAR', 'CANCELAR', 'STOP'):
                    with self.db:
                        self.db.execute("UPDATE inbox SET status='cancelled' WHERE patient_id IN (SELECT id FROM patients WHERE phone=?) AND status IN ('pending','processing')", (phone,))
                    self.changed.notify_all()
                with self.db:
                    return self.store._ingest(event, instance)
            event_id = event.get('eventId', '')
            if not isinstance(event_id, str) or not 8 <= len(event_id) <= 300:
                return {'action': 'ignore'}
            if not admitted and self.db.execute('SELECT id FROM inbox WHERE id=?', (event_id,)).fetchone():
                return {'action': 'ignore'}
            pending = self.db.execute("SELECT text FROM inbox WHERE patient_id=? AND status='pending'", (p['id'],)).fetchall()
            # Preserve oversized bursts by processing the extra message separately, never truncating it.
            if len(pending) >= 32 or sum(len(r['text']) + 1 for r in pending) + len(text) > 16000:
                with self.db:
                    return self.store._ingest(event, instance)
            with self.db:
                if not admitted:
                    self.db.execute('INSERT INTO inbox(id,patient_id,text,created) VALUES(?,?,?,?)',
                                    (event_id, p['id'], text.strip(), time.time()))
            self.changed.notify_all()
            while True:
                processing = self.db.execute("SELECT * FROM inbox WHERE patient_id=? AND status='processing'", (p['id'],)).fetchall()
                for media in processing:
                    if time.time()-media['created'] > 90:
                        with self.db:
                            self.db.execute("UPDATE inbox SET status='pending',text=? WHERE id=?", ('[Falha ao ler uma mídia. Peça para reenviar; não registre consumo a partir dela.]', media['id']))
                if any(time.time()-m['created'] <= 90 for m in processing):
                    self.changed.wait(timeout=1)
                    continue
                rows = self.db.execute("SELECT * FROM inbox WHERE patient_id=? AND status='pending' ORDER BY created,rowid", (p['id'],)).fetchall()
                if not rows or rows[-1]['id'] != event_id:
                    return {'action': 'ignore'}
                remaining = self.quiet_seconds - (time.time() - rows[-1]['created'])
                if remaining > 0:
                    self.changed.wait(timeout=remaining)
                    continue
                with self.db:
                    self.db.execute("UPDATE inbox SET status='consumed' WHERE patient_id=? AND status='pending'", (p['id'],))
                    photo_ids=[r['id'] for r in rows if self.db.execute('SELECT id FROM photo_drafts WHERE id=? AND analysis IS NOT NULL',(r['id'],)).fetchone()]
                    return self.store._ingest({**event, 'text': '\n'.join(r['text'] for r in rows),
                        '_photoSources':photo_ids,'_photoUserText':'\n'.join(r['text'] for r in rows if r['id'] not in photo_ids)}, instance)

    def prepare(self, dispatch_id, text, document=None):
        parts = split_message(text)
        for index, part in enumerate(parts):
            self.db.execute('INSERT INTO dispatch_parts(id,dispatch_id,position,text) VALUES(?,?,?,?)',
                            (str(uuid.uuid4()), dispatch_id, index, part))
        if document is not None:
            part_id = str(uuid.uuid4())
            self.db.execute('INSERT INTO dispatch_parts(id,dispatch_id,position,text) VALUES(?,?,?,?)',
                            (part_id, dispatch_id, len(parts), 'Seu guia de alimentação'))
            self.db.execute('INSERT INTO dispatch_documents VALUES(?,?,?)', (dispatch_id,part_id,document))
            parts.append('document')
        return [{'dispatchId': dispatch_id, 'index': index} for index in range(len(parts))]

    def authorize(self, body, instance):
        with self.store.lock, self.db:
            index = body.get('index')
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                return {'approved': False}
            row = self.db.execute('''SELECT q.*, d.created, d.patient_id, d.event_id, p.phone, p.consent, p.verified, e.optout, e.action
              FROM dispatch_parts q JOIN dispatches d ON d.id=q.dispatch_id JOIN patients p ON p.id=d.patient_id
              JOIN events e ON e.id=d.event_id WHERE q.dispatch_id=? AND q.position=?''', (body.get('dispatchId'), index)).fetchone()
            if not row or row['status'] != 'pending' or time.time() - row['created'] > 120:
                return {'approved': False}
            if row['optout']:
                if row['consent']:
                    return {'approved': False}
            elif not row['consent'] or (row['action'] != 'welcome' and not row['verified']):
                return {'approved': False}
            if row['event_id'].startswith('reminder:') and not self.store.coaching.reminder(row['event_id'], row['patient_id']):
                return {'approved': False}
            previous = self.db.execute("SELECT id FROM dispatch_parts WHERE dispatch_id=? AND position<? AND status<>'accepted'", (row['dispatch_id'], index)).fetchone()
            if previous:
                return {'approved': False}
            document = self.db.execute('SELECT payload FROM dispatch_documents WHERE part_id=?', (row['id'],)).fetchone()
            if document and (self.store.menu.get(row['patient_id']) or {}).get('stage') != 'ready':
                return {'approved': False}
            self.db.execute("UPDATE dispatch_parts SET status='reserved' WHERE id=?", (row['id'],))
            result = {'approved': True, 'partId': row['id'], 'dispatchId': row['dispatch_id'],
                    'number': row['phone'], 'instance': instance, 'text': row['text']}
            if document:
                result.update(mediaType='document', mimetype='application/pdf', fileName='seu-guia-alimentar.pdf',
                              media=base64.b64encode(document['payload']).decode('ascii'))
            return result

    def receipt(self, body):
        with self.store.lock, self.db:
            row = self.db.execute('SELECT * FROM dispatch_parts WHERE id=?', (body.get('partId'),)).fetchone()
            if not row or row['status'] not in ('reserved', 'accepted', 'uncertain'):
                return {'continue': False}
            status = body.get('status')
            if status not in ('accepted', 'uncertain'):
                return {'continue': False}
            if row['status'] != 'reserved':
                return {'continue': row['status'] == 'accepted'}
            self.db.execute('UPDATE dispatch_parts SET status=?,provider_id=? WHERE id=?',
                            (status, str(body.get('providerMessageId') or '')[:200], row['id']))
            remaining = self.db.execute("SELECT id FROM dispatch_parts WHERE dispatch_id=? AND status<>'accepted'", (row['dispatch_id'],)).fetchone()
            self.db.execute('UPDATE dispatches SET status=? WHERE id=?',
                            ('accepted' if not remaining else 'uncertain' if status == 'uncertain' else 'reserved', row['dispatch_id']))
            return {'continue': status == 'accepted'}
