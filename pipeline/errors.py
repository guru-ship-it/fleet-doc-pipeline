"""Typed failures. Every external call raises one of these instead of returning a soft success, and no message
carries a phone number or document text."""


class PipelineError(Exception):
    """Base class for pipeline failures."""


class WebhookAuthError(PipelineError):
    """The webhook signature or verify token did not match."""


class MediaDownloadError(PipelineError):
    """WhatsApp media could not be fetched."""


class ModelCallError(PipelineError):
    """The document model failed or returned an answer that does not fit the schema."""


class StorageError(PipelineError):
    """S3, SQS or DynamoDB rejected a read or write."""


class SendError(PipelineError):
    """WhatsApp did not accept an outgoing message."""


class ResidencyError(PipelineError):
    """A real (non-synthetic) document was about to be sent to a model hosted outside India."""
