"""Unit tests for file classifier module."""

from pathlib import Path
import pytest

from smart_organizer.classifier import (
    FileClassifier,
    classify_file,
    is_temporary_download,
)


@pytest.mark.parametrize(
    "filename, expected_category",
    [
        # Images
        ("photo.jpg", "Images"),
        ("image.jpeg", "Images"),
        ("graphic.png", "Images"),
        ("animation.gif", "Images"),
        ("vector.svg", "Images"),
        ("photo.webp", "Images"),
        ("camera.heic", "Images"),
        ("design.psd", "Images"),
        # Videos
        ("movie.mp4", "Videos"),
        ("clip.mkv", "Videos"),
        ("film.avi", "Videos"),
        ("recording.mov", "Videos"),
        ("stream.webm", "Videos"),
        ("tv.mpeg", "Videos"),
        # Audio
        ("song.mp3", "Audio"),
        ("podcast.wav", "Audio"),
        ("soundtrack.flac", "Audio"),
        ("track.aac", "Audio"),
        ("music.ogg", "Audio"),
        ("voice.opus", "Audio"),
        # PDFs
        ("document.pdf", "PDFs"),
        ("contract.PDF", "PDFs"),
        # Documents
        ("resume.docx", "Documents"),
        ("notes.doc", "Documents"),
        ("article.odt", "Documents"),
        ("readme.txt", "Documents"),
        ("spec.md", "Documents"),
        ("paper.tex", "Documents"),
        # Spreadsheets
        ("data.xlsx", "Spreadsheets"),
        ("budget.xls", "Spreadsheets"),
        ("table.csv", "Spreadsheets"),
        ("report.ods", "Spreadsheets"),
        ("values.tsv", "Spreadsheets"),
        # Presentations
        ("slides.pptx", "Presentations"),
        ("pitch.ppt", "Presentations"),
        ("talk.odp", "Presentations"),
        # Archives
        ("archive.zip", "Archives"),
        ("bundle.tar.gz", "Archives"),
        ("backup.7z", "Archives"),
        ("package.rar", "Archives"),
        ("source.tar", "Archives"),
        ("compressed.xz", "Archives"),
        # Code
        ("script.py", "Code"),
        ("app.js", "Code"),
        ("index.ts", "Code"),
        ("main.rs", "Code"),
        ("program.c", "Code"),
        ("header.hpp", "Code"),
        ("Program.cs", "Code"),
        ("backend.go", "Code"),
        ("service.java", "Code"),
        ("config.json", "Code"),
        ("settings.toml", "Code"),
        ("style.css", "Code"),
        ("deploy.sh", "Code"),
        # Applications
        ("installer.deb", "Applications"),
        ("setup.exe", "Applications"),
        ("package.rpm", "Applications"),
        ("portable.appimage", "Applications"),
        ("installer.msi", "Applications"),
        ("app.dmg", "Applications"),
        ("package.pkg", "Applications"),
        # Fallback
        ("unknown.xyz", "Others"),
        ("no_extension", "Others"),
        ("file.weird_ext_123", "Others"),
    ],
)
def test_classifier_standard_categories(filename: str, expected_category: str):
    assert classify_file(filename) == expected_category


@pytest.mark.parametrize(
    "filename, expected_category",
    [
        ("PHOTO.JPG", "Images"),
        ("IMAGE.PNG", "Images"),
        ("MOVIE.MP4", "Videos"),
        ("SONG.MP3", "Audio"),
        ("DOCUMENT.PDF", "PDFs"),
        ("NOTES.DOCX", "Documents"),
        ("SHEET.XLSX", "Spreadsheets"),
        ("SLIDES.PPTX", "Presentations"),
        ("ARCHIVE.ZIP", "Archives"),
        ("SCRIPT.PY", "Code"),
        ("SETUP.EXE", "Applications"),
    ],
)
def test_classifier_case_insensitivity(filename: str, expected_category: str):
    assert classify_file(filename) == expected_category


@pytest.mark.parametrize(
    "temp_filename",
    [
        "download.crdownload",
        "movie.mp4.crdownload",
        "file.part",
        "document.partial",
        "archive.tmp",
        "setup.download",
        "browser.crswap",
    ],
)
def test_temporary_download_detection(temp_filename: str):
    assert is_temporary_download(temp_filename) is True
    assert is_temporary_download(Path(f"/downloads/{temp_filename}")) is True


def test_custom_categories_override():
    custom = {
        "Books": [".epub", ".mobi", ".pdf"],
        "3DModels": [".obj", ".stl", ".blend"],
    }
    classifier = FileClassifier(custom_categories=custom)

    assert classifier.classify_file("novel.epub") == "Books"
    assert classifier.classify_file("paper.pdf") == "Books"
    assert classifier.classify_file("figure.stl") == "3DModels"

    # Built-ins still work
    assert classifier.classify_file("photo.png") == "Images"
    assert classifier.classify_file("song.mp3") == "Audio"
