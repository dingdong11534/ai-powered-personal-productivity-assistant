"""External integrations package.

All outbound HTTP requests from this application must flow through
app.external.client.ExternalHttpClient. Direct use of urllib/requests/httpx
anywhere else in the codebase is prohibited — that client is the single
enforcement point for SSRF protection, domain allowlisting, timeout, and
response-size limits.
"""
