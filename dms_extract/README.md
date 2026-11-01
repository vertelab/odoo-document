# dms_extract — textutvinning för dokumenthanteringen

Gör texten **inuti** ett dokument sökbar. `dms_ai` gör varje `dms.file` till
ett OKF-koncept, men kroppen är filnamnet, mappen och taggarna — inte filen.
Den som laddar upp `Avtal-2026.pdf` kan söka `avtal` och inget annat. Den här
modulen utvinner texten och matar den till den sökning som redan finns.

**Den ändrar inte sökningen.** `ai.okf.concept._okf_search`, den svenska
BM25-kolumnen och embedding-vägen är orörda. Vi fyller `okf_body` med mer
material, och båda signalerna breddas automatiskt.

## Systemberoenden

```
apt-get install python3-pymupdf tesseract-ocr tesseract-ocr-swe tesseract-ocr-eng
```

| Paket | Varför |
|---|---|
| `python3-pymupdf` | PDF (textyta + OCR-rendering) |
| `tesseract-ocr` | OCR-motorn |
| `tesseract-ocr-swe` | Svensk språkdata — `swe+eng` krävs |
| `tesseract-ocr-eng` | Engelsk språkdata (tekniska termer i svensk korpus) |

`post_init_hook` **vägrar installera** om något saknas och namnger paketet.
Det är avsiktligt: OCR är en utlovad förmåga, och en tyst textyta-bara-läge
skulle se ut som fungerande OCR tills någon faktiskt behöver den.

## De två trösklarna

| Parameter | Default | Vad den gör |
|---|---|---|
| `dms_extract.ocr_threshold` | `100` | OCR körs bara när textytan är **kortare** än så många tecken |
| `dms_extract.max_chars` | `200000` | Taket för lagrad text (~60 sidor svensk prosa) |

**Varför en tröskel och inte "alltid OCR":** OCR är ungefär två
tio-potenser dyrare per sida. På en digitalt född PDF tillför den ingenting.

**Varför 100 och inte 0:** en skannad sida ger ibland några tecken från en
stämpel. Att behandla det som "har textyta" ger en body på tre ord och ett
dokument som fortfarande inte går att hitta.

## OCR-kostnaden

Mätt på den här installationen 2026-11-01, samma PDF två gånger — en gång med
OCR tillåten, en gång med tröskeln satt till 0:

| Fall | Tid | Tecken |
|---|---|---|
| Textyta läses (ingen OCR) | 0,003 s | 0 |
| OCR krävs (`swe+eng`, 150 dpi) | 1,240 s | 13 |

**426× dyrare per sida.** Det är siffran som gör OCR till ett fallback och
inte en default — och den är mätt, inte gissad.

### Dränering av arkivet

Hela arkivet (238 filer, varav 86 med läsbart innehåll) dränerades på
**5 tick om 20 filer, 15 sekunder totalt** (~2,4 s per batch). Med
`min`-kadensen är det under 25 minuter från tom kö till tomt arkiv.

Hade alla 86 krävt OCR hade samma arkiv tagit ~1,8 minuter per batch och
~9 minuter för hela — fortfarande hanterbart, men 426× mer arbete för
dokument som redan hade en textyta.

## Kön

Utvinning körs **aldrig** på skrivvägen. `_inverse_content` är den enda
skrivvägen för fem protokoll (formulär, WebDAV, SFTP, API, PWA), och en
långsam utvinnare där hade saktat ner varje uppladdning på varje protokoll.

I stället: en `cron.task` (`technical_name='dms_extract'`, kadens `min`).

| Parameter | Default | Vad den gör |
|---|---|---|
| `dms_extract.batch_size` | `20` | Filer per tick |

Kön är **idempotent**: en fil vars `checksum` matchar `extract_hash` rörs
inte. Att köra cronen på ett färdigt arkiv kostar ett indexerat sök och noll
skrivningar.

## Fält

| Fält | Typ | Betydelse |
|---|---|---|
| `extract_state` | Selection | `pending` / `done` / `skipped` / `failed` |
| `extract_hash` | Char | `sha1` av innehållet vid senaste lyckade utvinning |
| `extract_date` | Datetime | När senaste försöket kördes |
| `extract_error` | Text | Varför det misslyckades (terminalt tills filen ändras) |
| `extracted_chars` | Integer | Längden på den **lagrade** texten (0 = ingen textyta) |
| `_extracted_text` | Text | Själva texten |
| `dms.directory.extract_enabled` | Boolean | `False` = mappen utvinns aldrig |

`extract_hash` använder **sha1**, samma algoritm som OCA:s `checksum`. Det är
inte en signatur utan en jämförelsenyckel — algoritmen måste vara den som
redan finns på fältet, annars kan de aldrig matcha.

## Undantagna mappar — läs det här

`dms.directory.extract_enabled = False` stänger av utvinning för en mapp och
allt under den.

**Sätt den på mappar med begränsat innehåll.** Den generiska OKF-källan
vägrar indexera fält med `groups`, men utvunnen text är inte ett fält med
`groups` — det finns ingen sådan spärr. En mapp vars innehåll bara vissa får
läsa måste stängas av explicit, annars blir texten sökbar för alla som ser
konceptet.

Samma sak gäller krypterade mappar (Vaultwarden): de innehåller chiffertext,
och att utvinna ur chiffertext indexerar brus.

Undantaget är en **egenskap på mappen**, inte en heuristik på byten. Att
försöka dekryptera och gissa skulle tyst indexera en trasig PDF som om den
vore krypterad.

## Format

| Format | Metod |
|---|---|
| PDF | PyMuPDF textyta; OCR (`swe+eng`) under tröskeln |
| DOCX, XLSX, PPTX | XML-parsning av `word/document.xml` m.fl. |
| ODT, ODS, ODP | XML-parsning av `content.xml` |
| TXT, CSV, MD, JSON, XML | Direkt avkodning (UTF-8, sedan latin-1) |
| HTML, XHTML | Taggrensning |
| EML | Ämne + `text/plain`-delar |
| RTF | Avkodning som text |
| **Bilder, ljud, video, teckensnitt** | **Ingen utvinning — tom text** |
| **OLE2** (`.doc`, `.xls`, `.ppt`) | **Ingen utvinning — tom text** |

De två sista raderna är med flit. En JPEG avkodad som latin-1 blir 145 000
tecken binärskräp som *ser ut som* innehåll i en sökträff, och en `.xls` blir
15 000 tecken som börjar med `ÐÏà¡±á>þÿ`. Det är värre än ingen text: träffen
ser ut som en träff. Att läsa OLE2 kräver `olefile`/`antiword` — tills dess är
tom text det ärliga svaret.

## Felsökning

**Allt blir `failed`** — PyMuPDF eller Tesseract saknas. Kör
`tesseract --list-langs` och kontrollera att `swe` och `eng` finns.

**Kön rör sig inte** — kontrollera att `cron_task`-posten är `active`. En
`cron.task` skapas inaktiv om `active` inte sätts explicit i XML:en.

**En fil står kvar som `pending`** — den saknar innehåll på disk (filestore
rensad). Den ska bli `skipped` vid nästa tick; om den inte blir det, se
`extract_error`.

**Texten är tom trots att filen har innehåll** — kontrollera `mimetype`. Är
den `application/octet-stream` faller filen i binärgrinden. Mimetype är
`compute`+`store` och beräknas från filnamnet.

## Tester

```
checkmodule -d <db> -m dms_extract -t --test-tags '*/dms_extract' --multi-user --port 8899
```

16 tester. Två skippas ärligt när miljön inte kan bevisa påståendet:
`TestDmsExtractVersionRestore` (kräver att `dms_version` faktiskt skapar
versioner) och `TestDmsExtractClamavOrder` (kräver en levande `clamd` —
fail-open-läget gör ordningen omöjlig att mäta).
