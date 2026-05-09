import logging

from backend.data.schemas import NormalizedOHLCV
from backend.data.validators import ValidationResult, validate_ohlcv_series

logger = logging.getLogger(__name__)


class NormalizationError(Exception):
    """
    Raised when the normalization pipeline rejects a dataset.

    Callers should inspect `errors` for the specific validation failures.
    """

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


class DataNormalizer:
    """
    Orchestrates the normalization pipeline for OHLCV datasets.

    Expected usage:
        adapter = CSVAdapter(config)
        records = adapter.load(file_path)
        normalizer = DataNormalizer()
        validated = normalizer.normalize(records)

    Runtime systems and strategies must consume output from this pipeline.
    Raw or un-normalized records must never reach the strategy layer.
    """

    def normalize(self, records: list[NormalizedOHLCV]) -> list[NormalizedOHLCV]:
        """
        Validate and return a normalized OHLCV series.

        Raises NormalizationError if any validation rule is violated.
        Returns the original records unchanged if validation passes
        (records are immutable; no mutation occurs here).
        """
        result: ValidationResult = validate_ohlcv_series(records)

        if result.warnings:
            for w in result.warnings:
                logger.warning("DataNormalizer: %s", w)

        if not result.valid:
            error_summary = "; ".join(result.errors[:5])
            if len(result.errors) > 5:
                error_summary += f" ... (+{len(result.errors) - 5} more)"
            raise NormalizationError(
                f"Normalization failed: {error_summary}",
                result.errors,
            )

        logger.debug("DataNormalizer: %d records passed validation", len(records))
        return records
