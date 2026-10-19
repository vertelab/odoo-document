# Usage

## Ansluta en WebDAV-klient till DMS

Modulen exponerar DMS på **`/webdav/`** på Odoo-serverns egen URL.
Ingen separat tjänst, ingen lokal filsynk — varje operation går direkt mot
`dms.storage` / `dms.directory` / `dms.file` via ORM.

## 1. Adressen

```
https://<odoo-host>/webdav/
```

**Det finns ingen `dav://`-adress.** WebDAV är HTTP/HTTPS — `dav://` är
bara ett schema som vissa filhanterare (GNOME/Nautilus, KDE Dolphin) visar
för att markera att en montering är WebDAV. Den underliggande URL:en är
alltid `https://…`.

| Klient | Adress att ange |
|---|---|
| GNOME Files / Nautilus | `davs://<odoo-host>/webdav/` (davs = WebDAV över TLS) |
| KDE Dolphin | `webdavs://<odoo-host>/webdav/` |
| Windows Explorer ("Anslut nätverksenhet") | `https://<odoo-host>/webdav/` |
| macOS Finder (Cmd+K) | `https://<odoo-host>/webdav/` |
| davfs2 (Linux, `mount.davfs`) | `https://<odoo-host>/webdav/` |
| rclone | `rclone config` → typ `webdav` → URL `https://<odoo-host>/webdav/` |
| curl (test) | `curl -u user:pass -X PROPFIND https://<odoo-host>/webdav/ -H "Depth: 1"` |

**Avslutande snedstreck krävs.** `/webdav` (utan slash) ger 404 — routen är
registrerad med `strict_slashes`, så `/webdav/` är den enda giltiga formen.
Klienter som normaliserar bort sista slashen (bl.a. Windows Explorer) måste
få URL:en med slash i konfigurationen.

Det finns också en discovery-endpoint: `/.well-known/webdav/` → 307-redirect
till `/webdav/`. Använd den om klienten stödjer well-known.

## 2. Inloggning

HTTP Basic auth med **Odoo-användare + lösenord** (inte API-nyckel).
Servern prövar inloggningen mot databaserna i `list_db`-listan och använder
den första som accepterar användaren. Användarens vanliga DMS-behörigheter
gäller — `check_access()` anropas per operation.

Rekommendation: skapa en dedikerad WebDAV-användare med åtkomst bara till
de storage:n som ska delas. Basic auth skickar lösenordet i klartext över
nätet — **använd alltid HTTPS** (Caddy-terminering framför Odoo).

## 3. Vad man ser i monteringen

```
/webdav/
├── <Storage 1>/          ← dms.storage (is_hidden=False)
│   ├── <Rotmapp>/        ← dms.directory (is_root_directory=True)
│   │   ├── <Undermapp>/
│   │   └── fil.pdf
└── <Storage 2>/
```

Filer kan **inte** skapas direkt under en storage — de måste ligga i en
rotmapp (`dms.directory` med `is_root_directory=True`). Försök ger 409.

## 4. Protokollstöd

| Metod | Stöds | Not |
|---|---|---|
| OPTIONS | ✅ | `DAV: 1, 2` (ingen auth krävs) |
| PROPFIND | ✅ | `Depth: 0/1/infinity` |
| GET / HEAD | ✅ | |
| PUT | ✅ | hela filen; **`Content-Range`/chunked PUT → 501** |
| DELETE | ✅ | mapp måste vara tom (409 annars) |
| MKCOL | ✅ | |
| MOVE / COPY | ✅ | `Destination`-header krävs |
| LOCK / UNLOCK | ⚠️ | se nedan |

### LOCK — varning

LOCK svarar med ett lock-token men **token valideras inte** vid PUT/DELETE.
Låset sätts som `locked_by` på `dms.file` och kan därför fastna om klienten
kraschar innan UNLOCK. Kontrollera/rensa i Odoo: fältet *Locked* på filen.

### Chunked PUT

Office-program (Word, Excel, LibreOffice) och rclone kan skicka stora filer
som `Content-Range`-chunks. Det stöds inte — servern svarar 501. Filen måste
skickas i ett svep. Samma gäller `PUT` med `Transfer-Encoding: chunked` hos
vissa proxys; sätt `request_buffering`/storleksgräns i Caddy i så fall.

## 5. Felsökning

| Symptom | Orsak |
|---|---|
| 404 på `/webdav` | snedstrecket saknas — använd `/webdav/` |
| 404 på `/webdav/` | modulen `dms_webdav` är inte installerad i den databas Odoo kör |
| 301-loop på `/webdav/` | gammal version (≤ 18.0.1.0.0) med `strict_slashes=False` — uppgradera |
| 401 trots rätt lösenord | användaren finns i en DB utanför `list_db`, eller 2FA är på |
| 409 vid uppladdning | föräldramappen finns inte, eller filen ligger direkt under en storage |
| 501 vid uppladdning | chunked PUT (`Content-Range`) |
| Filen "låst" i Odoo | LOCK utan efterföljande UNLOCK — rensa *Locked* |

Logga inkommande anrop: `grep '\[WebDAV\]' /var/log/odoo/odoo-server.log`.
