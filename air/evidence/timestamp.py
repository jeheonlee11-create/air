"""RFC 3161 trusted timestamping (optional, graceful).

Requests a timestamp token for the Merkle root from a public TSA (FreeTSA).
The token proves the record existed at a point in time attested by a third
party — the vendor cannot backdate its own evidence.

Network failures degrade gracefully: the bundle records that timestamping was
attempted and unavailable, which is itself honest evidence state. Production
deployments should use a contracted TSA/QTSP and archive the TSA cert chain.
"""

from __future__ import annotations

import hashlib

FREETSA_URL = "https://freetsa.org/tsr"


def request_timestamp(data: bytes, timeout_s: float = 10.0) -> dict:
    """Returns {"status": "ok", "tsr_der_b64": ...} or {"status": "unavailable", ...}."""
    digest = hashlib.sha256(data).digest()
    try:
        from rfc3161_client import TimestampRequestBuilder, decode_timestamp_response
        import base64
        import httpx

        req = TimestampRequestBuilder().data(data).build()
        resp = httpx.post(
            FREETSA_URL,
            content=req.as_bytes(),
            headers={"Content-Type": "application/timestamp-query"},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        tsr = decode_timestamp_response(resp.content)
        return {
            "status": "ok",
            "tsa": FREETSA_URL,
            "message_imprint_sha256": digest.hex(),
            "gen_time": str(tsr.tst_info.gen_time),
            "tsr_der_b64": base64.b64encode(resp.content).decode(),
            "note": "RFC 3161 token from FreeTSA (development TSA); production should use a "
                    "contracted TSA/QTSP with archived certificate chain.",
        }
    except Exception as e:  # noqa: BLE001 — any failure degrades to honest 'unavailable'
        return {
            "status": "unavailable",
            "tsa": FREETSA_URL,
            "message_imprint_sha256": digest.hex(),
            "error": f"{type(e).__name__}: {e}",
            "note": "Timestamping attempted and unavailable; record integrity still verifiable "
                    "via Merkle root + signature, but time attestation is vendor-asserted only.",
        }
