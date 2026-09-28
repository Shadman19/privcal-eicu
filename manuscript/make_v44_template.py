"""v44 = v43 + authors' ethics and funding statements (verified eICU de-identification facts)."""
from pathlib import Path
t = Path("PrivCal_SciRep_v43.template.tex").read_text()
def rep(o, n):
    global t
    assert t.count(o) == 1, o[:70]; t = t.replace(o, n)
rep("% INTERNAL DRAFT v43", "% INTERNAL DRAFT v44")
rep(r"This study used de-identified data from the eICU Collaborative Research Database, accessed under the PhysioNet credentialed data use agreement\cite{r1}; the database was approved for research use with a waiver of informed consent as described by its creators\cite{r2}. [TO CONFIRM WITH AUTHORS: Old Dominion University's institutional determination for this secondary analysis, or a statement that none was sought and why.]",
    r"This retrospective study used only de-identified data from the eICU Collaborative Research Database, accessed under the PhysioNet credentialed data use agreement after the required human-research training\cite{r1}. All tables in the database are de-identified to meet the safe harbor provision of the US Health Insurance Portability and Accountability Act, and the re-identification risk was certified by an independent privacy firm (Privacert, Cambridge, MA; HIPAA certification no. 1031219-2)\cite{r2}. Because only de-identified data were analysed, review by the Old Dominion University institutional review board was not sought, and individual informed consent was not required for this secondary analysis. All methods were carried out in accordance with relevant guidelines and regulations, including the PhysioNet data use agreement.")
rep(r"[TO CONFIRM WITH AUTHORS: funding sources and funder role, or ``This research received no specific funding.'']",
    r"This research received no specific grant from any funding agency in the public, commercial or not-for-profit sectors.")
rep(r"Reporting follows TRIPOD+AI, with TRIPOD-Cluster items for the hospital structure\cite{r9,r19}; completed checklists are provided as Supplementary Information.",
    r"Reporting follows TRIPOD+AI, with TRIPOD-Cluster considerations for the hospital structure\cite{r9,r19}; the completed TRIPOD+AI checklist is Supplementary Table S1.")
assert "TO CONFIRM" not in t
Path("PrivCal_SciRep_v44.template.tex").write_text(t); print("ok")
