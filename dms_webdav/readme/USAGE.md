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

| Klient | Status | Adress att ange |
|---|---|---|
| **rclone** | ✅ **verifierad** | `rclone config` → typ `webdav` → URL `https://<odoo-host>/webdav/` |
| curl (test) | ✅ verifierad | `curl -u user:pass -X PROPFIND https://<odoo-host>/webdav/ -H "Depth: 1"` |
| GNOME Files / Nautilus | ⚠️ ej testad | `davs://<odoo-host>/webdav/` (davs = WebDAV över TLS) |
| KDE Dolphin | ⚠️ ej testad | `webdavs://<odoo-host>/webdav/` |
| Windows Explorer | ⚠️ ej testad | `https://<odoo-host>/webdav/` |
| macOS Finder (Cmd+K) | ⚠️ ej testad | `https://<odoo-host>/webdav/` |
| **davfs2** (`mount.davfs`) | ❌ **fungerar inte** | se avsnitt 7 |

**Använd rclone.** Det är den enda klient vi verifierat end-to-end mot en
körande Odoo 18 (2026-10-20, `dms_webdav` 18.0.1.0.20): lista, skriva,
läsa, kopiera, flytta och radera fungerar.

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
| 401 trots rätt lösenord | användaren finns i en DB utanför `list_db`, eller 2FA är på |
| 409 vid uppladdning | föräldramappen finns inte, eller filen ligger direkt under en storage |
| 501 vid uppladdning | chunked PUT (`Content-Range`) |
| Filen "låst" i Odoo | LOCK utan efterföljande UNLOCK — rensa *Locked* |
| Tom katalog i davfs2 | känt fel i davfs2, se avsnitt 7 — använd rclone |

Logga inkommande anrop: `grep '\[WebDAV\]' /var/log/odoo/odoo-server.log`.

## 6. Behörigheter — krävs för att se och skriva

DMS har ett eget behörighetssystem ovanpå Odoo:s. En användare som är
`admin` i Odoo ser **ingenting** i DMS om den inte har:

1. **En DMS-grupp** — `dms.group_dms_user` eller `dms.group_dms_manager`.
2. **En `dms.access.group`** kopplad till katalogen, med `perm_create`,
   `perm_write`, `perm_unlink` satta efter behov.

Saknas punkt 2 blir katalogen tom och alla skrivförsök ger `403`.

Modulen kör listning och uppslag med `sudo()` och kontrollerar sedan
behörigheten per post via `_filtered_access()` — DMS:s egen mekanism.
`check_access()` duger **inte** här: `dms.directory` har en `ir.rule` på det
beräknade fältet `permission_read`, och för `create` är fältet `False` ända
tills posten finns, så en vanlig `create()` nekas alltid.

## 7. davfs2 — känd icke-fungerande klient

**`davfs2` 1.7.0 kan inte montera den här endpointen.** Mounten lyckas och
autentiseringen går igenom, men `ls` på monteringen ger
`Invalid argument` och katalogen visas tom.

### Vad som händer

`strace` på `mount.davfs` visar att servern svarar korrekt — davfs2 läser in
ett giltigt `<d:multistatus>` med både roten och storage:n — men den skriver
bara `.` till sin katalogcache. Storage-namnet förekommer **inte alls** i
davfs2:s minne:

```
read(7, "@\0\0\0\35\0\0\0...")   opcode 29 (FUSE_READDIR), offset 8, size 32768
write(8, ".", 1)                    ← enda posten i cachen
write(7, "\20\0\0\0\352\377\377\377...")  error -22 = EINVAL
```

Kärnan begär `READDIR` vid **offset 8**, men davfs2 har bara en post och
svarar `EINVAL`.

### Vad som uteslutits

Serverns svar är verifierat korrekt på alla punkter:

| Test | Resultat |
|---|---|
| XML välformad (`xml.etree`) | ✅ 2 `<d:response>` |
| `href` som absolut URI | ✅ (och som relativ path, 18.0.1.0.13) |
| `getcontenttype` på collections | borttaget — ingen effekt |
| `getlastmodified` på collections | tillagt — ingen effekt |
| `backup_dir` → `lost+found` bort | `lost+found` försvann, mounten fallerar ändå |
| Depth:1 endast direkta barn | ✅ rclone-bugg fixad, mounten fallerar ändå |

Samma endpoint fungerar med `rclone` (`rclone lsd dms:` listar storage:n
utan fel). Felet ligger alltså i davfs2:s tolkning av svaret, inte i
servern.

### Använd rclone istället

```bash
rclone config create dms webdav \
    url https://<odoo-host>/webdav/ \
    vendor other \
    user <odoo-login> \
    pass $(rclone obscure '<lösenord>')

rclone lsd dms:              # lista storage:n
rclone ls  dms:              # lista filer rekursivt
rclone mount dms: /mnt/dms   # montera som filsystem (FUSE, userland)
```

`rclone mount` ger samma filsystemsupplevelse som davfs2 utan att gå via
davfs2:s katalogcache.
