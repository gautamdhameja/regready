"""The corpus record in code. Keep it in sync with corpus.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Act:
    key: str  # used in citations and file names, such as "ai_act"
    name: str  # used in chunk headers, such as "AI Act"
    number: str  # as other acts cite it: "Regulation (EU) 2024/1689"
    stem: str  # file name of the PDF in corpus/, without ".pdf"
    version_date: str
    consolidated: bool  # consolidated texts have no recitals or drafting formulas


ACTS = [
    Act("ai_act", "AI Act", "2024/1689", "CELEX_02024R1689-20260727_EN_TXT", "2026-07-27", True),
    Act("gdpr", "GDPR", "2016/679", "CELEX_02016R0679-20160504_EN_TXT", "2016-05-04", True),
    Act("dora", "DORA", "2022/2554", "CELEX_32022R2554_EN_TXT", "2022-12-27", False),
    Act("nis2", "NIS2", "2022/2555", "CELEX_32022L2555_EN_TXT", "2022-12-27", False),
    Act("data_act", "Data Act", "2023/2854", "OJ_L_202302854_EN_TXT", "2023-12-22", False),
]

KEY_BY_NUMBER = {act.number: act.key for act in ACTS}
NAME_BY_KEY = {act.key: act.name for act in ACTS}
