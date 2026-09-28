"""Plain-text word counts for the Sci Rep limits (abstract <=200, main text <=4500)."""
import re, sys
def plain(s):
    s = s.replace(r"\noindent", " ")
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = s.replace("~", " ").replace("--", "-")
    s = re.sub(r"\$\\times10\^\{-3\}\$", "x10-3", s)
    s = re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[\\{}^_]", "", m.group(1)), s)
    s = re.sub(r"\\(cite|ref|label)\{[^}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", s)
    s = s.replace("{", " ").replace("}", " ").replace("\\%", "%").replace("\\", " ")
    return s
def count(s): return len(plain(s).split())
if __name__ == "__main__":
    t = open(sys.argv[1]).read()
    ab = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", t, re.S).group(1)
    print("abstract words", count(ab))
