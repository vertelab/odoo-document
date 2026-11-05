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
| GNOME Files / Nautilus | ⚠️ protokollet klart, klienten ej körd | `davs://<odoo-host>/webdav/` (davs = WebDAV över TLS) |
| KDE Dolphin | ⚠️ ej testad | `webdavs://<odoo-host>/webdav/` |
| Windows Explorer | ⚠️ ej testad | `https://<odoo-host>/webdav/` |
| macOS Finder (Cmd+K) | ⚠️ ej testad | `https://<odoo-host>/webdav/` |
| **davfs2** (`mount.davfs`) | ❌ **fungerar inte** | se avsnitt 7 |

**rclone är den enda klient vi verifierat end-to-end** mot en körande Odoo 18:
lista, skriva, läsa, kopiera, flytta och radera fungerar.

**Om Nautilus/davs:** själva GVFS-klienten har vi inte kört här (servern är
headless — ingen Nautilus installerad). Däremot är numera *alla* HTTP-anrop
GVFS gör verifierade med curl mot den körande instansen: `PROPFIND` Depth 0/1
med GVFS:s exakta egenskapslista, `GET` med `Range` (206), `PUT`, `MKCOL`,
`MOVE`/`COPY` med `Overwrite`, `DELETE`. Det som återstår är att GNOME:s egen
implementation också beter sig som dokumenterat — det kan bara avgöras på en
arbetsstation med skrivbord.

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
| PROPFIND | ✅ | `Depth: 0/1/infinity`; `allprop`/`propname`/`prop` respekteras, se §4.1 |
| GET / HEAD | ✅ | |
| PUT | ✅ | hela filen eller `Content-Range`-chunks, se §4.2 |
| DELETE | ✅ | mapp måste vara tom (409 annars) |
| MKCOL | ✅ | |
| MOVE / COPY | ✅ | `Destination`-header krävs; procentkodning hanteras; `Overwrite: F` → 412 |
| LOCK / UNLOCK | ⚠️ | se nedan |

### 4.1 PROPFIND — egenskaper (properties)

Servern svarar på den egenskapsfråga klienten faktiskt ställer:

| Kropp | Läge | Svar |
|---|---|---|
| ingen / otydbar | `allprop` | alla egenskaper servern har |
| `<D:propname/>` | `propname` | alla namn, tomma värden |
| `<D:prop>…</D:prop>` | `prop` | endast de efterfrågade |

Egenskaper som lämnas ut:

| Egenskap | Källa | Gäller |
|---|---|---|
| `displayname` | fil-/mappnamn | båda |
| `resourcetype` | `<D:collection/>` för mappar, tom för filer | båda |
| `getcontenttype` | `mimetype`, annars `application/octet-stream` | båda |
| `getcontentlength` | `size` | båda |
| `getetag` | `checksum` (sha1 av innehållet) | **endast filer** |
| `getlastmodified` | `write_date` | båda |
| `creationdate` | `create_date` | båda |
| `supportedlock` | `<D:exclusive/>` fil, `<D:shared/>` mapp | båda |

RFC 4918 §9.1 kräver att en egenskap servern inte kan leverera hamnar i en
**egen `propstat` med `404 Not Found`** — inte att den utelämnas tyst. Så här
ser det ut när en klient frågar efter `quota-available-bytes` (som vi inte har):

```xml
<D:propstat>
  <D:prop><D:getetag>"ab26…"</D:getetag></D:prop>
  <D:status>HTTP/1.1 200 OK</D:status>
</D:propstat>
<D:propstat>
  <D:prop><D:quota-available-bytes/></D:prop>
  <D:status>HTTP/1.1 404 Not Found</D:status>
</D:propstat>
```

`getetag` är en **stark** validator: den är sha1 av bytesen, så den ändras
exakt när innehållet ändras. Mappar har ingen `checksum` och får därför
`getetag` i 404-blocket — det är korrekt, inte ett fel.

**Varför detta spelar roll:** GNOME/gvfs (Nautilus) cachar kataloglistningar
och använder `getetag` + `getlastmodified` för att avgöra om en fil ändrats.
Utan dem visar Nautilus inaktuella filstorlekar och upptäcker inte att någon
annan skrivit i filen — den öppnar då en gammal version i Inkscape/GIMP och
skriver över nyare data vid spara.

### LOCK — varning

LOCK svarar med ett lock-token men **token valideras inte** vid PUT/DELETE.
Låset sätts som `locked_by` på `dms.file` och kan därför fastna om klienten
kraschar innan UNLOCK. Kontrollera/rensa i Odoo: fältet *Locked* på filen.

### Chunked PUT

Office-program (Word, Excel, LibreOffice) och rclone kan skicka stora filer
som `Content-Range`-chunks. Det stöds: servern buffrar chunkarna i
`/tmp/dms_webdav_chunks/` och skriver filen när sista chunken anlänt.
Mellansvar är **308** med `Range: bytes=0-<end>`; sista chunken ger **201**.

```
PUT /webdav/.../stor.xcf   Content-Range: bytes 0-4194303/12582912  -> 308
PUT /webdav/.../stor.xcf   Content-Range: bytes 4194304-12582911/12582912 -> 201
```

Skicka alltid `Content-Type: application/octet-stream` — se §4.3.

### 4.3 `Content-Type` styr om bodyn överlever

**Sätt `Content-Type: application/octet-stream` på PUT.** Skickas kroppen som
`application/x-www-form-urlencoded` eller `multipart/form-data` parsar Odoo
den som ett formulär *innan* kontrollern körs, och då kan den inte längre
läsas som rådata.

Det här är inte teoretiskt. `curl --data-binary` sätter
`application/x-www-form-urlencoded` som default, och den kombinationen
nollställde en 397 923-byte SVG till 0 byte med status **200 OK** — klienten
såg alltså en lyckad uppladdning.

Modulen försvarar sig på tre nivåer (`models/ir_http_dispatch.py` och
`_reject_form_urlencoded()`):

| Skydd | Verkan |
|---|---|
| Body cachas före formulärparsningen | `Content-Type` spelar ingen roll — rätt bytes lagras |
| Enskilt formfält återvinns | kropp som redan parsats räddas om den är entydig |
| `Content-Length` > 0 men 0 lästa byte | **400** i stället för tyst nollning |
| Tom body mot befintlig icke-tom fil | **409** — filen röres inte |

Den sista raden betyder att en legitim tömning av en fil **inte** kan göras
med en tom PUT. Radera filen och skapa en ny, eller skriv ett tecken.

```bash
# rätt
curl -u user:pass -T fil.xcf -H "Content-Type: application/octet-stream" https://host/webdav/.../fil.xcf

# fel — kroppen kan parsas bort
curl -u user:pass --data-binary @fil.xcf https://host/webdav/.../fil.xcf
```

RFC 4918 säger att servern ska behandla PUT-kroppen som ogenomskinlig
oberoende av `Content-Type`. Att Odoo:s formulärparsning ändå rör den är en
avvikelse från det, som modulen nu kompenserar för i stället för att lita på
att varje klient sätter rätt header.

## 5. Felsökning

| Symptom | Orsak |
|---|---|
| 404 på `/webdav` | snedstrecket saknas — använd `/webdav/` |
| 404 på `/webdav/` | modulen `dms_webdav` är inte installerad i den databas Odoo kör |
| 401 trots rätt lösenord | användaren finns i en DB utanför `list_db`, eller 2FA är på |
| 409 vid uppladdning | föräldramappen finns inte, eller filen ligger direkt under en storage |
| 409 vid tom PUT mot befintlig fil | avsiktligt skydd mot dataförlust, se §4.3 |
| 400 vid uppladdning | `Content-Length` utlovade byte som aldrig kom fram, se §4.3 |
| 412 vid MOVE/COPY | destinationen finns och `Overwrite: F`, se §4 |
| Filen blev 0 byte | åtgärdat i 18.0.1.6.0; uppgradera modulen, se §4.3 |
| Filen "låst" i Odoo | LOCK utan efterföljande UNLOCK — rensa *Locked* |
| Tom katalog i davfs2 | känt fel i davfs2, se avsnitt 7 — använd rclone |
| Nautilus visar fel storlek / upptäcker inte ändringar | saknade `getetag`/`getlastmodified` — åtgärdat i 18.0.1.9.0, se §4.1 |
| Klienten visar "0 objekt" men curl listar allt | `PROPFIND` gav inte de egenskaper klienten frågade efter — åtgärdat i 18.0.1.9.0 |
| Filnamn med `&` eller `<` ger trasig lista | XML eskapers numera, se §4.1 |

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

### Varför begränsningen dokumenteras här

Servern har inget att rätta: den svarar enligt RFC 4918 och rclone läser
svaret korrekt. Att forma om svaret för att blidka davfs2:s katalogcache
skulle göra endpointen felaktig för de klienter som fungerar. Begränsningen
står därför hos den klient som inte fungerar, i stället för att döljas i en
"kända fel"-lista utan ägare.

### Vad som testas — och vad som inte testas

`dms_webdav/tests/test_webdav_http.py` och `test_webdav_path.py` testar
**serverns** svar: statuskoder, autentisering, `Content-Range`,
well-known-redirect, path-uppslagning och egenskapsutlämningen i §4.1.
Ingen av dem går genom en monterad klient, och ingen av dem kan fånga en
klientbugg som davfs2:s. Den enda klient som verifierats end-to-end är
`rclone` — därför är den fortsatt den rekommenderade vägen när något måste
fungera utan överraskningar. Nautilus/gvfs är protokollmässigt förberedd men
oskodd i praktiken.

### Kör testerna rätt — `--single-mode` hoppar tyst över HTTP-testerna

`checkmodule --single-mode` startar Odoo med `--no-http`. Då finns ingen
HTTP-server, och varje `HttpCase.setUpClass()` kastar
`AttributeError: 'PreforkServer' object has no attribute 'httpd'`. Klassen
markeras som fel och **körs aldrig** — ett grönt testresultat betyder alltså
inte att HTTP-testerna har gått.

Kör dem med en konfiguration som har `workers = 0` (Odoo varnar själv:
"Unit testing in workers mode could fail; use --workers 0"):

```bash
sudo -n su odoo -c "ODOO_SERVER_CONF=/var/tmp/picm/odoo.conf \
  /usr/local/bin/checkmodule -d dms -m dms_webdav -t --test-tags /dms_webdav"
```

Sätt `workers = 0` i den kopian, inte i `/etc/odoo/odoo.conf`. Rena
hjälpfunktionstester hör hemma i en `BaseCase` (som `TestWebdavProps`) så att
de körs även i `--single-mode`.
