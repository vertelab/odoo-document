# -*- coding: utf-8 -*-
{
    'name': 'Document: AI',
    'version': '18.0.1.0.0',
    'summary': 'OKF-indexering av dms.file och dms.directory',
    'category': 'Hidden',
    'author': 'Vertel AB',
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
    ],
    'demo': [],
    'application': False,
    'installable': True,
    'auto_install': False,
}
