# -*- coding: utf-8 -*-
{
    'name': 'Document: AI',
    'version': '18.0.1.1.0',
    'summary': 'OKF-indexering av dms.file och dms.directory + förlage-markering',
    'category': 'Hidden',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'description': """
        Bryggmodul för OKF-indexering av dokumenthanteringen.

        Lägger `ai.okf.mixin` på dms.file och dms.directory så att
        dokumenten och mapparna blir OKF-koncept.

        VARFÖR: ett dokument ÄR kunskap — det är hela poängen med att
        spara det. Ändå ligger det i en Binary-kolumn som varken BM25
        eller embeddings ser. Indexeringen gör NAMNET, mappen och
        taggarna sökbara; filens innehåll kräver utvinning, vilket är
        en separat uppgift.

        FÖRLAGA (office-document-agent): en förlaga är ett DMS-dokument
        som AI-agenten utgår från för stil och generiska sidor. Den
        markeras med en tagg och får `is_forlaga`, plus hjälparna
        `_ai_find_forlagor` / `_ai_check_editable`. Detta bor här och
        inte i kärnan — `ai_agent_core` får aldrig nämna `dms`.

        BEROENDE: `dms` är OCA:s modul (github.com/OCA/dms), inte vår.
        Den här bryggan ligger i vårt repo och beroende på deras — vi
        rör inte deras kod.

        Modellerna äger sina KÄLLOR; mixinen i ai_agent_core äger fälten
        och flaggan. Ingen domän nämns i kärnan.
    """,
    'depends': [
        'ai_agent_core',
        'dms',
    ],
    'data': [
        'data/okf_artifact_types_dms.xml',
        'data/dms_forlaga_tag.xml',
        'data/okf_debug_actions.xml',
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': False,
}
