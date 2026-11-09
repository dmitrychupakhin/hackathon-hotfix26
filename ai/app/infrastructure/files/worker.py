"""Killable parser process with bounded memory, CPU, file output and wall time."""

import math
import multiprocessing
import os
import signal
import time

from app.domain import DomainError
from app.infrastructure.files.models import ParsedFile


def _worker(connection, raw, name, media_type, file_id, limits):
    try:
        if os.name != "posix":
            raise DomainError(
                "extractor_unavailable", "Bounded parser workers require a POSIX platform", 503
            )
        import resource

        os.setsid()
        memory = limits.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        cpu = math.ceil(limits.timeout_seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (limits.max_archive_bytes, limits.max_archive_bytes)
        )
        from app.infrastructure.files.extractors import extract

        result = extract(raw, name, media_type, file_id, limits)
        connection.send(("ok", result.model_dump()))
    except DomainError as exc:
        connection.send(("error", exc.code, exc.message, exc.status))
    except MemoryError:
        connection.send(("error", "extraction_resource_limit", "Parser memory limit exceeded", 413))
    except ImportError:
        connection.send(
            ("error", "extractor_unavailable", "A required extraction dependency is missing", 503)
        )
    except Exception:
        # Parser errors can contain file contents. Never expose them to logs or HTTP clients.
        connection.send(
            ("error", "invalid_document", "Document is corrupt or cannot be safely extracted", 422)
        )
    finally:
        connection.close()


def _stop(process):
    if process.pid:
        try:
            # Includes Tesseract/Poppler children. Child may not yet have called setsid.
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            if process.is_alive():
                process.kill()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()


def parse_isolated(raw, name, media_type, file_id, limits):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, raw, name, media_type, file_id, limits))
    started = False
    try:
        process.start()
        started = True
        child.close()
        deadline = time.monotonic() + limits.timeout_seconds
        while time.monotonic() < deadline:
            if parent.poll(min(0.1, max(0, deadline - time.monotonic()))):
                try:
                    response = parent.recv()
                except EOFError:
                    break
                if response[0] == "ok":
                    return ParsedFile.model_validate(response[1])
                raise DomainError(response[1], response[2], response[3])
            if not process.is_alive():
                break
        if process.is_alive():
            raise DomainError(
                "extraction_timeout", "Document extraction exceeded its deadline", 422
            )
        raise DomainError(
            "extraction_resource_limit",
            "Parser exited without a result; resource limit or invalid document",
            422,
        )
    finally:
        if started:
            _stop(process)
            process.close()
        parent.close()
        child.close()
