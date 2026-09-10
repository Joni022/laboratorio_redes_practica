import json
import math
import re
from difflib import SequenceMatcher

import pdfplumber


PDF_PATH = r"C:\Users\jonat\Downloads\FORMS B81 actualizado.pdf"
OUTPUT_PATH = r"C:\Users\jonat\Desktop\UTN\FORMS\tmp\pdfs\parsed_updated.json"
PAGE_STEP = 1000
GREEN = (0.0706, 0.5373, 0.2157)
RED = (0.8588, 0.2157, 0.1765)
CHECK_GREEN = (0.1176, 0.5569, 0.2431)


def close_color(value, expected, tolerance=0.025):
    if not isinstance(value, tuple) or len(value) != 3:
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(value, expected))


def normalize(value):
    value = value.lower().replace("�", "")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def words_to_text(words):
    if not words:
        return ""
    lines = []
    for word in sorted(words, key=lambda item: (item["global_top"], item["x0"])):
        if not lines or abs(word["global_top"] - lines[-1][0]["global_top"]) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return " ".join(" ".join(item["text"] for item in sorted(line, key=lambda item: item["x0"])) for line in lines).strip()


document_words = []
controls = []
right_checks = []

with pdfplumber.open(PDF_PATH) as pdf:
    for page_index, page in enumerate(pdf.pages):
        for word in page.extract_words(extra_attrs=["non_stroking_color", "size"]):
            word = dict(word)
            word["page"] = page_index + 1
            word["global_top"] = page_index * PAGE_STEP + word["top"]
            word["global_bottom"] = page_index * PAGE_STEP + word["bottom"]
            document_words.append(word)

        for curve in page.curves:
            width = curve["x1"] - curve["x0"]
            height = curve["bottom"] - curve["top"]
            item = dict(curve)
            item["page"] = page_index + 1
            item["global_top"] = page_index * PAGE_STEP + curve["top"]
            item["global_bottom"] = page_index * PAGE_STEP + curve["bottom"]
            if 82 <= curve["x0"] <= 85 and 13 <= width <= 16 and 13 <= height <= 16:
                controls.append(item)
            if curve["x0"] > 480 and 9 <= width <= 18 and 7 <= height <= 14 and close_color(curve.get("stroking_color"), CHECK_GREEN):
                right_checks.append(item)


colored_words = [
    word for word in document_words
    if close_color(word.get("non_stroking_color"), GREEN) or close_color(word.get("non_stroking_color"), RED)
]

question_runs = []
for word in sorted(colored_words, key=lambda item: (item["global_top"], item["x0"])):
    if not question_runs or word["global_top"] - question_runs[-1][-1]["global_bottom"] > 28:
        question_runs.append([word])
    else:
        question_runs[-1].append(word)

questions = []
for index, run in enumerate(question_runs):
    start = min(word["global_top"] for word in run)
    end = min(word["global_top"] for word in question_runs[index + 1]) if index + 1 < len(question_runs) else 10**9
    title = words_to_text(run)
    if not title:
        continue

    segment_words = [word for word in document_words if start <= word["global_top"] < end]
    segment_controls = sorted(
        [control for control in controls if start <= control["global_top"] < end],
        key=lambda item: item["global_top"],
    )
    segment_checks = sorted(
        [check for check in right_checks if start <= check["global_top"] < end],
        key=lambda item: item["global_top"],
    )

    response_label_words = [
        word for word in segment_words
        if word["text"] in {"Respuesta", "correcta"} and word["x0"] < 180
    ]
    response_label_top = None
    for word in response_label_words:
        nearby = [other for other in response_label_words if abs(other["global_top"] - word["global_top"]) < 3]
        if {other["text"] for other in nearby} == {"Respuesta", "correcta"}:
            response_label_top = word["global_top"]
            break

    original_controls = [control for control in segment_controls if response_label_top is None or control["global_top"] < response_label_top]
    repeated_controls = [control for control in segment_controls if response_label_top is not None and control["global_top"] > response_label_top]

    def option_texts(option_controls, limit):
        results = []
        centers = [
            (control["global_top"] + control["global_bottom"]) / 2
            for control in option_controls
        ]
        for option_index, control in enumerate(option_controls):
            option_start = (
                (centers[option_index - 1] + centers[option_index]) / 2
                if option_index > 0
                else control["global_top"] - 6
            )
            next_control = (
                (centers[option_index] + centers[option_index + 1]) / 2
                if option_index + 1 < len(option_controls)
                else limit
            )
            candidates = [
                word for word in segment_words
                if option_start <= word["global_top"] < next_control
                and word["x0"] >= 105
                and word.get("non_stroking_color") != (0.0, 0.0, 0.0)
                and not close_color(word.get("non_stroking_color"), GREEN)
                and not close_color(word.get("non_stroking_color"), RED)
                and not re.fullmatch(r"[01]/1", word["text"])
            ]
            results.append(words_to_text(candidates))
        return results

    original_limit = response_label_top if response_label_top is not None else end
    options = option_texts(original_controls, original_limit)
    repeated = option_texts(repeated_controls, end)

    correct_indexes = set()
    for check in segment_checks:
        check_center = (check["global_top"] + check["global_bottom"]) / 2
        if original_controls:
            nearest = min(
                range(len(original_controls)),
                key=lambda candidate: abs(((original_controls[candidate]["global_top"] + original_controls[candidate]["global_bottom"]) / 2) - check_center),
            )
            distance = abs(((original_controls[nearest]["global_top"] + original_controls[nearest]["global_bottom"]) / 2) - check_center)
            if distance <= 18:
                correct_indexes.add(nearest)

    for repeated_text in repeated:
        if not repeated_text or not options:
            continue
        scores = [SequenceMatcher(None, normalize(repeated_text), normalize(option)).ratio() for option in options]
        nearest = max(range(len(scores)), key=scores.__getitem__)
        if scores[nearest] >= 0.72:
            correct_indexes.add(nearest)

    questions.append({
        "sourceIndex": len(questions) + 1,
        "page": run[0]["page"],
        "text": title,
        "options": options,
        "correctIndexes": sorted(correct_indexes),
        "isMulti": any((control["x1"] - control["x0"]) >= 14.5 for control in original_controls),
        "wasIncorrect": close_color(run[0].get("non_stroking_color"), RED),
        "responseCorrectText": repeated,
    })

with open(OUTPUT_PATH, "w", encoding="utf-8") as stream:
    json.dump(questions, stream, ensure_ascii=False, indent=2)

print(json.dumps({
    "questions": len(questions),
    "single": sum(not question["isMulti"] for question in questions),
    "multiple": sum(question["isMulti"] for question in questions),
    "without_options": sum(not question["options"] for question in questions),
    "without_answers": sum(not question["correctIndexes"] for question in questions),
    "incorrect_source_responses": sum(question["wasIncorrect"] for question in questions),
}, ensure_ascii=False))
