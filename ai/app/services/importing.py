import csv
import io
import stat
import zipfile
from pathlib import PurePosixPath

from pydantic import ValidationError

from app.config import Settings
from app.domain import DatasetCreate, DomainError
from app.services.documents import decode_text


def import_archive(raw: bytes, settings: Settings, questions_override=None) -> DatasetCreate:
    if len(raw) > settings.max_package_bytes:
        raise DomainError("archive_too_large", "Archive exceeds the upload limit", 413)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise DomainError("invalid_archive", "Expected a ZIP archive", 422) from None
    packages = {}
    questions = questions_override
    questions_seen = False
    total = 0
    try:
        infos = archive.infolist()
        if len(infos) > 2000:
            raise DomainError("archive_too_large", "Too many entries in archive", 413)
        for info in infos:
            path = PurePosixPath(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in info.filename
                or stat.S_ISLNK(info.external_attr >> 16)
            ):
                raise DomainError(
                    "unsafe_archive_path", "Archive contains unsafe paths or links", 422
                )
            total += info.file_size
            if total > settings.max_package_bytes * 4 or info.file_size > settings.max_upload_bytes:
                raise DomainError("archive_too_large", "Expanded archive exceeds size limits", 413)
            if info.is_dir():
                continue
            if path.name == "questions.csv":
                if questions_seen:
                    raise DomainError(
                        "ambiguous_dataset", "Archive contains multiple questions.csv files", 422
                    )
                text, _ = decode_text(archive.read(info))
                reader = csv.DictReader(io.StringIO(text), delimiter=";")
                if reader.fieldnames != ["id", "package", "question"]:
                    raise DomainError(
                        "invalid_questions", "Expected CSV columns id;package;question", 422
                    )
                parsed_questions = list(reader)
                if questions_override is not None and parsed_questions != questions_override:
                    raise DomainError(
                        "questions_mismatch",
                        "ZIP questions differ from uploaded questions.csv",
                        422,
                    )
                questions = parsed_questions
                questions_seen = True
            # Never load check.py or answers_public.json into the model's package data.
            elif (
                len(path.parts) >= 3
                and path.parts[-3] == "packages"
                and path.suffix.lower() in {".txt", ".md"}
            ):
                text, _ = decode_text(archive.read(info))
                code = path.parts[-2]
                packages.setdefault(code, []).append({"name": path.name, "text": text})
            elif (
                len(path.parts) >= 3
                and path.parts[-3] == "packages"
                and path.name not in {"answers_public.json", "check.py", ".DS_Store"}
            ):
                raise DomainError(
                    "unsupported_archive_document",
                    "ZIP procurement documents must be TXT/MD; other formats are not silently skipped. Upload original formats as flat files for one procurement.",
                    422,
                )
    except (zipfile.BadZipFile, RuntimeError):
        raise DomainError("invalid_archive", "Archive cannot be read", 422) from None
    finally:
        archive.close()
    if not packages or questions is None:
        raise DomainError(
            "invalid_dataset", "Expected packages/<code>/*.txt and questions.csv", 422
        )
    try:
        return DatasetCreate(
            name="Imported dataset",
            packages=[
                {"code": code, "name": code, "documents": docs}
                for code, docs in sorted(packages.items())
            ],
            questions=questions,
        )
    except ValidationError:
        raise DomainError(
            "invalid_dataset",
            "Dataset has invalid IDs, duplicate files, or question references",
            422,
        ) from None
