"""Persistência transacional local; nenhum pacote externo necessário."""
import json
import os
import sqlite3


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, data TEXT NOT NULL, PRIMARY KEY(kind,id))')
        self.db.commit()
        self.cache = {(k, i): d for k, i, d in self.db.execute('SELECT kind,id,data FROM records')}

    def read(self, kind):
        return {i: json.loads(d) for (k, i), d in self.cache.items() if k == kind}

    def sync(self, groups):
        desired = {(kind, str(i)): json.dumps(v, ensure_ascii=False, sort_keys=True)
                   for kind, rows in groups.items() for i, v in rows.items()}
        changed = [(k, i, d) for (k, i), d in desired.items() if self.cache.get((k, i)) != d]
        removed = [key for key in self.cache if key[0] in groups and key not in desired]
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO records VALUES (?,?,?)', changed)
            self.db.executemany('DELETE FROM records WHERE kind=? AND id=?', removed)
        for key in removed:
            del self.cache[key]
        self.cache.update(desired)

    def page(self, offset=0, limit=100):
        total = self.db.execute("SELECT COUNT(*) FROM records WHERE kind='leads'").fetchone()[0]
        rows = self.db.execute("SELECT data FROM records WHERE kind='leads' ORDER BY id LIMIT ? OFFSET ?", (limit, offset))
        return total, [json.loads(d) for (d,) in rows]

    def close(self):
        self.db.close()


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Não foi possível ler {os.path.basename(path)}. O original foi preservado. Restaure um backup antes de iniciar.') from exc


def write_json(path, data):
    temp = path + '.tmp'
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
