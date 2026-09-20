"""Test per app/logger.py: ogni metodo di AppLogger produce il log atteso, al livello giusto."""

import logging

from app.logger import AppLogger


def test_job_created_logga_a_livello_info(caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        AppLogger().job_created("job-1", "https://example.com")

    assert "job-1" in caplog.text
    assert "https://example.com" in caplog.text
    assert caplog.records[0].levelname == "INFO"


def test_job_unreachable_logga_a_livello_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        AppLogger().job_unreachable("job-1", "https://esempio-morto.com")

    assert caplog.records[0].levelname == "WARNING"


def test_job_done_logga_a_livello_info(caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        AppLogger().job_done("job-1", "screenshot_example_com.png")

    assert "screenshot_example_com.png" in caplog.text


def test_job_failed_logga_a_livello_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        AppLogger().job_failed("job-1", "Playwright è esploso")

    assert caplog.records[0].levelname == "ERROR"


def test_job_not_found_logga_a_livello_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        AppLogger().job_not_found("id-inesistente")

    assert caplog.records[0].levelname == "ERROR"


def test_job_retried_logga_a_livello_info(caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        AppLogger().job_retried("job-1")

    assert caplog.records[0].levelname == "INFO"


def test_ssrf_blocked_logga_a_livello_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        AppLogger().ssrf_blocked("http://169.254.169.254/")

    assert caplog.records[0].levelname == "WARNING"


def test_redirect_blocked_logga_a_livello_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        AppLogger().redirect_blocked("http://localhost/")

    assert caplog.records[0].levelname == "WARNING"


def test_auth_failed_logga_a_livello_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app"):
        AppLogger().auth_failed("/screenshot")

    assert "/screenshot" in caplog.text
    assert caplog.records[0].levelname == "WARNING"
