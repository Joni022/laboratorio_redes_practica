import json
import re
import unicodedata
from difflib import SequenceMatcher


ROOT = r"C:\Users\jonat\Desktop\UTN\FORMS"


def normalize(value):
    value = value.replace("�", "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"\b(seleccione|seleccionar|marque|indique)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


with open(ROOT + r"\index.html", encoding="utf-8") as stream:
    html = stream.read()
current = json.loads(re.search(r"const QUESTIONS = (\[.*?\]);\s*const BLOCK_SIZE", html, re.S).group(1))
with open(ROOT + r"\tmp\pdfs\parsed_updated.json", encoding="utf-8") as stream:
    updated = json.load(stream)

rows = []
used_current = set()
for new in updated:
    scores = [SequenceMatcher(None, normalize(new["text"]), normalize(old["text"])).ratio() for old in current]
    best_index = max(range(len(scores)), key=scores.__getitem__)
    score = scores[best_index]
    if score >= 0.72:
        used_current.add(best_index)
    rows.append((new, current[best_index], score))

unmatched_new = [
    {"new": new["sourceIndex"], "page": new["page"], "score": round(score, 3), "text": new["text"], "best_old": old["sourceIndex"], "best_old_text": old["text"]}
    for new, old, score in rows if score < 0.82
]
unmatched_old = [
    {"old": old["sourceIndex"], "text": old["text"]}
    for index, old in enumerate(current) if index not in used_current
]

answer_diffs = []
option_diffs = []
for new, old, score in rows:
    if score < 0.82:
        continue
    option_map = {}
    weak = []
    for new_index, new_option in enumerate(new["options"]):
        scores = [SequenceMatcher(None, normalize(new_option), normalize(old_option["text"])).ratio() for old_option in old["options"]]
        old_index = max(range(len(scores)), key=scores.__getitem__)
        option_map[new_index] = old_index
        if scores[old_index] < 0.78:
            weak.append({"new_index": new_index, "new": new_option, "best_old": old["options"][old_index]["text"], "score": round(scores[old_index], 3)})
    mapped_correct = sorted({option_map[index] for index in new["correctIndexes"] if index in option_map})
    old_correct = sorted(index for index, option in enumerate(old["options"]) if option["id"] in old["correctIds"])
    if mapped_correct != old_correct:
        answer_diffs.append({
            "new": new["sourceIndex"], "old": old["sourceIndex"], "score": round(score, 3), "text": new["text"],
            "new_correct": [new["options"][index] for index in new["correctIndexes"]],
            "old_correct": [old["options"][index]["text"] for index in old_correct],
            "weak_option_matches": weak,
        })
    if weak or len(new["options"]) != len(old["options"]):
        option_diffs.append({
            "new": new["sourceIndex"], "old": old["sourceIndex"], "score": round(score, 3), "text": new["text"],
            "new_count": len(new["options"]), "old_count": len(old["options"]), "weak": weak,
        })

report = {
    "counts": {
        "current": len(current), "updated": len(updated),
        "matched_082": sum(score >= 0.82 for _, _, score in rows),
        "unmatched_new": len(unmatched_new), "unmatched_old": len(unmatched_old),
        "answer_diffs": len(answer_diffs), "option_diffs": len(option_diffs),
    },
    "unmatched_new": unmatched_new,
    "unmatched_old": unmatched_old,
    "answer_diffs": answer_diffs,
    "option_diffs": option_diffs,
    "without_answers": [question for question in updated if not question["correctIndexes"]],
}

with open(ROOT + r"\tmp\pdfs\comparison.json", "w", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report["counts"], ensure_ascii=False))
