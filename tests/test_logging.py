import structlog
from structlog.contextvars import merge_contextvars
from structlog.testing import LogCapture

from autocontent.shared.logging import bind_log_context, clear_log_context


def test_job_id_logging_smoke() -> None:
    capture = LogCapture()
    structlog.configure(
        processors=[merge_contextvars, capture],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id="job-1")
    logger.info("job_started", project_id=1)
    clear_log_context()

    assert capture.entries
    assert capture.entries[0]["job_id"] == "job-1"
    assert capture.entries[0]["project_id"] == 1
