"""URL helper utilities."""

from typing import Mapping, Optional

from requests import PreparedRequest


def merge_query_params(url: str, params: Mapping[str, Optional[str]]) -> str:
    """Merge query parameters into the provided URL."""
    clean_params = {k: v for k, v in params.items() if v is not None}
    if not clean_params:
        return url
    req = PreparedRequest()
    req.prepare_url(url, clean_params)
    return req.url  # type: ignore[return-value]
