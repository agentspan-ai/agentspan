"""Is each ingress actually served, and with which certificate?

"Domain is down" is often not the network: an ingress whose class no controller
owns (disabled by hand), a Certificate that never renewed, or nginx falling back to
its fake default certificate all look like an outage from outside. These are read
from the ingress spec and from the certificate the host really serves.
"""
from __future__ import annotations

import socket
import ssl

FAKE_CERT_CN = "Kubernetes Ingress Controller Fake Certificate"


def _rows(text: str) -> list[list[str]]:
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return [l.split() for l in lines[1:]]


def served_certificate(host: str, timeout: float = 8.0) -> dict:
    """The certificate ``host`` serves on 443, fetched without trusting it."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        subject = dict(x[0] for x in cert.get("subject", ()))
        issuer = dict(x[0] for x in cert.get("issuer", ()))
        return {"trusted": True, "subject": subject.get("commonName"),
                "issuer": issuer.get("organizationName") or issuer.get("commonName"),
                "notAfter": cert.get("notAfter")}
    except ssl.SSLCertVerificationError as exc:
        out = {"trusted": False, "error": exc.verify_message}
    except OSError as exc:
        return {"trusted": False, "error": f"no TLS connection: {exc}"}
    # Untrusted: read the cert anyway to name it (fake default, expired, wrong host).
    raw_ctx = ssl.create_default_context()
    raw_ctx.check_hostname = False
    raw_ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with raw_ctx.wrap_socket(sock, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
        out["fakeDefaultCertificate"] = FAKE_CERT_CN.encode() in der
    except OSError:
        pass
    return out


def check_ingresses(ingress_text: str, class_text: str, cert_text: str,
                    served: dict[str, dict]) -> dict:
    """Flag ingresses nothing serves, Certificates not Ready, and bad served certs.

    Args:
        ingress_text: ``get ingress -A -o custom-columns=NS,NAME,CLASS,HOSTS,TLS,ADDR`` output.
        class_text: ``get ingressclass -o custom-columns=NAME`` output.
        cert_text: ``get certificate -A -o custom-columns=NS,NAME,READY,MESSAGE`` output
            (empty when cert-manager is not installed).
        served: host -> ``served_certificate(host)``.
    """
    classes = {r[0] for r in _rows(class_text) if r}
    problems, ingresses = [], []
    for r in _rows(ingress_text):
        if len(r) < 4:
            continue
        name, klass, hosts = r[1], r[2], r[3].split(",")
        ing = {"namespace": r[0], "name": name, "class": klass, "hosts": hosts,
               "tls": r[4] if len(r) > 4 else None, "address": r[5] if len(r) > 5 else None}
        ingresses.append(ing)
        if name.startswith("cm-acme-http-solver"):
            continue
        if klass != "<none>" and classes and klass not in classes:
            problems.append(f"ingress {name} uses class '{klass}', which no IngressClass defines "
                            f"(have {sorted(classes)}): NO controller serves {', '.join(hosts)}")
        for host in hosts:
            s = served.get(host) or {}
            if s.get("fakeDefaultCertificate"):
                problems.append(f"{host} serves the ingress controller's FAKE default certificate: "
                                "no ingress with a valid TLS secret is serving this host")
            elif s and str(s.get("error", "")).startswith("no TLS connection"):
                problems.append(f"{host} is not reachable from the agent ({s['error']}) — "
                                "internal-only load balancer, or the host is down")
            elif s and not s.get("trusted"):
                problems.append(f"{host} serves an untrusted certificate: {s.get('error')}")
    for r in _rows(cert_text):
        if len(r) >= 3 and r[2] != "True":
            problems.append(f"Certificate {r[0]}/{r[1]} is not Ready: {' '.join(r[3:])}")
    if not classes:
        problems.append("IngressClass list could not be read (empty or Forbidden) — "
                        "whether a controller serves each ingress is UNKNOWN, not established")
    return {"healthy": not problems, "problems": problems, "ingresses": ingresses,
            "ingressClasses": sorted(classes), "servedCertificates": served}
