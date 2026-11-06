"""Durable per-patient burst collection and ordered, at-most-once message parts."""
import json
import re
import threading
import time
import uuid


def split_message(text, limit=700):
    parts = []
    while len(text) > limit:
        cut = text.rfind('\n\n', 0, limit + 1)
        if cut < limit // 3:
            cut = text.rfind('\n', 0, limit + 1)
        if cut < limit // 3:
            cut = text.rfind(' ', 0, limit + 1)
        if cut < limit // 3:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
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

    def collect(self, event, instance):
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
                                    'PARAR LEMBRETES', 'CANCELAR LEMBRETES', 'PARAR LEMBRETES DE ÁGUA',
                                    'CANCELAR LEMBRETES DE ÁGUA', 'ALTERAR LEMBRETES', 'ATIVAR LEMBRETES') or re.fullmatch(r'\d{6}', command)
            if not p or not prefs or prefs['stage'] != 'done' or immediate:
                if phone and command in ('SAIR', 'PARAR', 'CANCELAR', 'STOP'):
                    with self.db:
                        self.db.execute("UPDATE inbox SET status='cancelled' WHERE patient_id IN (SELECT id FROM patients WHERE phone=?) AND status='pending'", (phone,))
                    self.changed.notify_all()
                with self.db:
                    return self.store._ingest(event, instance)
            event_id = event.get('eventId', '')
            if not isinstance(event_id, str) or not 8 <= len(event_id) <= 300:
                return {'action': 'ignore'}
            if self.db.execute('SELECT id FROM inbox WHERE id=?', (event_id,)).fetchone():
                return {'action': 'ignore'}
            pending = self.db.execute("SELECT text FROM inbox WHERE patient_id=? AND status='pending'", (p['id'],)).fetchall()
            # Preserve oversized bursts by processing the extra message separately, never truncating it.
            if len(pending) >= 32 or sum(len(r['text']) + 1 for r in pending) + len(text) > 16000:
                with self.db:
                    return self.store._ingest(event, instance)
            with self.db:
                self.db.execute('INSERT INTO inbox(id,patient_id,text,created) VALUES(?,?,?,?)',
                                (event_id, p['id'], text.strip(), time.time()))
            self.changed.notify_all()
            while True:
                rows = self.db.execute("SELECT * FROM inbox WHERE patient_id=? AND status='pending' ORDER BY created,rowid", (p['id'],)).fetchall()
                if not rows or rows[-1]['id'] != event_id:
                    return {'action': 'ignore'}
                remaining = self.quiet_seconds - (time.time() - rows[-1]['created'])
                if remaining > 0:
                    self.changed.wait(timeout=remaining)
                    continue
                with self.db:
                    self.db.execute("UPDATE inbox SET status='consumed' WHERE patient_id=? AND status='pending'", (p['id'],))
                    return self.store._ingest({**event, 'text': '\n'.join(r['text'] for r in rows)}, instance)

    def prepare(self, dispatch_id, text):
        parts = split_message(text)
        for index, part in enumerate(parts):
            self.db.execute('INSERT INTO dispatch_parts(id,dispatch_id,position,text) VALUES(?,?,?,?)',
                            (str(uuid.uuid4()), dispatch_id, index, part))
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
            self.db.execute("UPDATE dispatch_parts SET status='reserved' WHERE id=?", (row['id'],))
            return {'approved': True, 'partId': row['id'], 'dispatchId': row['dispatch_id'],
                    'number': row['phone'], 'instance': instance, 'text': row['text']}

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
