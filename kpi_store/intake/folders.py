"""Sets up the shared folder a team keeps its intake files in, for a team that works offline.

    py -m kpi_store.intake folders <place>

It makes one folder named KPI-intake in the place you name, with four folders in it, and copies the two forms and
the guide into the first:

    KPI-intake/
      the-form/             the HTML form, the Excel form and the guide "How to use the form"
      1-in-progress/        answers files that are still being filled
      2-ready-for-check/    answers files the Business analyst has finished
      3-checked/            complete answers files, each with the check's report beside it
      READ-ME.txt           what each folder is for

Run it again after a rebuild of the pack: it replaces the three files in the-form with the newer ones. It never
changes or removes a file in the three numbered folders. kpi-intake/how-to-use-the-form.html explains the folders
to the people who use them. Standard library only.
"""
import shutil
from pathlib import Path

TOP = "KPI-intake"
FORM_FOLDER = "the-form"
FOLDERS = (
    (FORM_FOLDER, "The form itself: kpi-intake-form.html, kpi-intake-form.xlsx and the guide how-to-use-the-form.html. Open the form from here. Save nothing here."),
    ("1-in-progress", "Answers files that are still being filled. The Business analyst moves each saved file here from the Downloads folder."),
    ("2-ready-for-check", "Answers files the Business analyst has finished. The Architect checks each file here."),
    ("3-checked", "Complete answers files, each with the check's report beside it. The Architect moves a file here when the check says it is complete and signed."),
)
COPIED = ("kpi-intake-form.html", "kpi-intake-form.xlsx", "how-to-use-the-form.html")
READ_ME = "READ-ME.txt"


class FoldersError(Exception):
    """The folders cannot be made here. The message says why."""


def read_me():
    lines = ["KPI intake: the shared folder", "",
             "One answers file holds one KPI. Keep the name the form gives it: <kpi-name>.kpi-intake.json", ""]
    for name, about in FOLDERS:
        lines += [name, "  " + about, ""]
    lines += ["Open the-form/how-to-use-the-form.html for the steps.", ""]
    return "\n".join(lines)


def create(place, pack):
    """Makes the folders under `place` and copies the forms and the guide from the pack folder. Returns the top
    folder and what was done, as lines."""
    place, pack = Path(place), Path(pack)
    if not place.is_dir():
        raise FoldersError(f"{place} is not a folder. Name a folder that exists, such as your team's shared drive.")
    missing = [name for name in COPIED if not (pack / name).is_file()]
    if missing:
        raise FoldersError(f"the pack folder {pack} has no {', '.join(missing)}. Build the pack first: py -m kpi_store.intake build")
    top = place / TOP
    done = []
    for name, _ in FOLDERS:
        folder = top / name
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise FoldersError(f"{folder} exists and is not a plain folder. Remove it and run the command again.")
        if not folder.is_dir():
            folder.mkdir(parents=True)
            done.append(f"made {TOP}/{name}")
    for name in COPIED:
        target = top / FORM_FOLDER / name
        fresh = (pack / name).read_bytes()
        if target.is_symlink():
            raise FoldersError(f"{target} is a link. Remove it and run the command again.")
        if not target.is_file() or target.read_bytes() != fresh:
            verb = "replaced" if target.is_file() else "copied"
            shutil.copyfile(pack / name, target)
            done.append(f"{verb} {TOP}/{FORM_FOLDER}/{name}")
    note = top / READ_ME
    if not note.is_file() or note.read_text(encoding="utf-8") != read_me():
        with note.open("w", encoding="utf-8", newline="\n") as f:
            f.write(read_me())
        done.append(f"wrote {TOP}/{READ_ME}")
    return top, done
