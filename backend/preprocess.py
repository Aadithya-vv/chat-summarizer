import re

def clean_chat(text: str) -> str:
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()
        if len(line) < 3:
            continue
        if re.fullmatch(r"[👍😂🔥❤️]+", line):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)
