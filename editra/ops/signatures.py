"""Firme digitali: verifica (PDF firmati e file .p7m), firma con certificato, ID digitale.

La verifica controlla tre cose, come i programmi professionali:
- integrità: il documento non è stato alterato dopo la firma;
- validità crittografica della firma;
- attendibilità del certificato, rispetto ai certificati radice di Windows
  e a quelli che l'utente ha scelto di considerare attendibili.
La revoca online (OCSP/CRL) non viene interrogata: la verifica resta locale.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import os
from dataclasses import dataclass, field
from ..i18n import T


@dataclass
class SigInfo:
    field: str
    signer: str = "—"
    email: str = ""
    issuer: str = ""
    time: str = ""
    reason: str = ""
    location: str = ""
    intact: bool = False
    valid: bool = False
    trusted: bool = False
    covers_all: bool = False
    modified_after: str = ""
    cert_valid_from: str = ""
    cert_valid_to: str = ""
    serial: str = ""
    summary: str = ""
    details: str = ""
    page: int | None = None
    rect: tuple | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.intact or not self.valid:
            return "non_valida"
        if not self.trusted:
            return "sconosciuta"
        if not self.covers_all:
            return "modificata"
        return "valida"


def _fmt_dt(d) -> str:
    if not d:
        return ""
    try:
        return d.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(d)


def _name(cert) -> tuple[str, str, str]:
    subj = cert.subject.native
    cn = subj.get("common_name") or subj.get("organization_name") or cert.subject.human_friendly
    email = subj.get("email_address", "")
    issuer = cert.issuer.native.get("common_name") or cert.issuer.human_friendly
    return str(cn), str(email), str(issuer)


# ---------------------------------------------------------- attendibilità
def _trust_dir() -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EditraPDFStudio", "certificati_attendibili")
    os.makedirs(base, exist_ok=True)
    return base


def trusted_user_certs():
    from asn1crypto import pem, x509
    out = []
    for fn in os.listdir(_trust_dir()):
        try:
            data = open(os.path.join(_trust_dir(), fn), "rb").read()
            if pem.detect(data):
                _, _, data = pem.unarmor(data)
            out.append(x509.Certificate.load(data))
        except Exception:
            continue
    return out


def add_trusted_cert(cert_der: bytes, name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in " _-")[:50] or "certificato"
    p = os.path.join(_trust_dir(), safe + ".cer")
    with open(p, "wb") as f:
        f.write(cert_der)
    return p


def _windows_roots():
    from asn1crypto import x509
    out = []
    try:
        import ssl
        for store in (T('ROOT'), "CA"):
            for der, enc, trust in ssl.enum_certificates(store):
                if enc == "x509_asn":
                    try:
                        out.append(x509.Certificate.load(der))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


_ROOTS = None


def validation_context():
    global _ROOTS
    from pyhanko_certvalidator import ValidationContext
    if _ROOTS is None:
        _ROOTS = _windows_roots()
    roots = list(_ROOTS) + trusted_user_certs()
    return ValidationContext(trust_roots=roots, allow_fetching=False, revocation_mode="soft-fail")


# --------------------------------------------------------------- verifica
def verify_pdf(data: bytes) -> list[SigInfo]:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    out = []
    r = PdfFileReader(io.BytesIO(data), strict=False)
    sigs = list(r.embedded_signatures)
    for sig in sigs:
        info = SigInfo(field=sig.field_name or T('Firma'))
        try:
            sd = sig.sig_object
            info.reason = str(sd.get("/Reason", "") or "")
            info.location = str(sd.get("/Location", "") or "")
        except Exception:
            pass
        try:
            cert = sig.signer_cert
            info.signer, info.email, info.issuer = _name(cert)
            info.cert_valid_from = _fmt_dt(cert["tbs_certificate"]["validity"]["not_before"].native)
            info.cert_valid_to = _fmt_dt(cert["tbs_certificate"]["validity"]["not_after"].native)
            info.serial = f"{cert.serial_number:X}"
        except Exception as e:
            info.errors.append(T('Certificato non leggibile: {}').format(e))
        try:
            st = validate_pdf_signature(sig, validation_context())
            info.intact = bool(st.intact)
            info.valid = bool(st.valid)
            info.trusted = bool(st.trusted)
            info.time = _fmt_dt(st.signer_reported_dt or (st.timestamp_validity.timestamp if st.timestamp_validity else None))
            cov = str(getattr(st, "coverage", ""))
            info.covers_all = "ENTIRE_FILE" in cov
            if not info.covers_all and "ENTIRE_REVISION" in cov:
                ml = str(getattr(st, "modification_level", ""))
                if "NONE" in ml:
                    info.covers_all = True
                elif "FORM_FILLING" in ml or "LTA_UPDATES" in ml:
                    info.covers_all = True
                    info.modified_after = T('Dopo la firma sono stati compilati campi o aggiunte firme (consentito)')
                elif "ANNOTATIONS" in ml:
                    info.modified_after = T('Dopo la firma sono state aggiunte annotazioni')
                else:
                    info.modified_after = T('Il documento è stato modificato dopo la firma')
            try:
                info.details = st.pretty_print_details()
            except Exception:
                info.details = ""
        except Exception as e:
            info.errors.append(str(e))
        info.summary = _summary(info)
        out.append(info)
    return out


def _summary(i: SigInfo) -> str:
    if i.errors and not i.valid:
        return T('Impossibile verificare la firma: ') + "; ".join(i.errors)
    if not i.intact:
        return T('Firma NON valida: il documento è stato alterato dopo la firma.')
    if not i.valid:
        return T('Firma NON valida: la firma crittografica non corrisponde.')
    parts = [T('Integrità verificata: il contenuto firmato non è stato modificato.')]
    if i.trusted:
        parts.append(T('Il certificato del firmatario è attendibile.'))
    else:
        parts.append(T('Il certificato del firmatario non è tra quelli attendibili (identità non verificata).'))
    if i.modified_after:
        parts.append(i.modified_after + ".")
    return " ".join(parts)


def locate_signature_fields(doc) -> dict[str, tuple[int, tuple]]:
    import pymupdf
    out = {}
    for pno, page in enumerate(doc):
        for w in page.widgets():
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                out[w.field_name] = (pno, tuple(w.rect))
    return out


# --------------------------------------------------------------- file .p7m
def parse_p7m(data: bytes) -> tuple[bytes, list[SigInfo]]:
    """Estrae il documento contenuto in una busta CAdES (.p7m) e verifica le firme."""
    from asn1crypto import cms, pem
    import base64

    raw = data
    if pem.detect(raw):
        _, _, raw = pem.unarmor(raw)
    else:
        try:
            if raw[:1] != b"\x30":
                raw = base64.b64decode(raw, validate=False)
        except Exception:
            pass
    content = raw
    infos: list[SigInfo] = []
    # le buste possono essere annidate (firme multiple .p7m.p7m)
    for _ in range(5):
        ci = cms.ContentInfo.load(content)
        if ci["content_type"].native != "signed_data":
            break
        sd = ci["content"]
        inner = sd["encap_content_info"]["content"]
        payload = inner.native if inner is not None else b""
        certs = [c.chosen for c in sd["certificates"]] if sd["certificates"] else []
        for si in sd["signer_infos"]:
            infos.append(_verify_signer_info(si, certs, payload))
        content = payload
        if not content or content[:1] != b"\x30":
            break
    return content, infos


def _verify_signer_info(si, certs, payload: bytes) -> SigInfo:
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    info = SigInfo(field=T('Firma CAdES'))
    sid = si["sid"]
    cert = None
    for c in certs:
        try:
            if sid.name == "issuer_and_serial_number":
                if c.serial_number == sid.chosen["serial_number"].native and c.issuer == sid.chosen["issuer"]:
                    cert = c
            elif c.key_identifier == sid.chosen.native:
                cert = c
        except Exception:
            continue
    if cert is None and certs:
        cert = certs[0]
    if cert is None:
        info.errors.append(T('Certificato del firmatario assente'))
        info.summary = _summary(info)
        return info
    info.signer, info.email, info.issuer = _name(cert)
    info.serial = f"{cert.serial_number:X}"
    info.cert_valid_from = _fmt_dt(cert["tbs_certificate"]["validity"]["not_before"].native)
    info.cert_valid_to = _fmt_dt(cert["tbs_certificate"]["validity"]["not_after"].native)
    algo = si["digest_algorithm"]["algorithm"].native
    h = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha384": hashlib.sha384, "sha512": hashlib.sha512}.get(algo, hashlib.sha256)
    hcls = {"sha1": hashes.SHA1, "sha256": hashes.SHA256, "sha384": hashes.SHA384, "sha512": hashes.SHA512}.get(algo, hashes.SHA256)
    signed_attrs = si["signed_attrs"]
    try:
        if signed_attrs:
            md = None
            for a in signed_attrs:
                t = a["type"].native
                if t == "message_digest":
                    md = a["values"][0].native
                elif t == "signing_time":
                    info.time = _fmt_dt(a["values"][0].native)
            info.intact = md == h(payload).digest()
            to_verify = signed_attrs.untag().dump() if hasattr(signed_attrs, "untag") else signed_attrs.dump()
            # gli attributi firmati si verificano con il tag SET (0x31)
            to_verify = b"\x31" + to_verify[1:]
        else:
            info.intact = True
            to_verify = payload
        pub = cx509.load_der_x509_certificate(cert.dump()).public_key()
        sig = si["signature"].native
        sa = si["signature_algorithm"]["algorithm"].native
        if isinstance(pub, rsa.RSAPublicKey):
            pad = padding.PSS(mgf=padding.MGF1(hcls()), salt_length=padding.PSS.AUTO) if "pss" in sa else padding.PKCS1v15()
            pub.verify(sig, to_verify, pad, hcls())
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(sig, to_verify, ec.ECDSA(hcls()))
        info.valid = True
    except Exception as e:
        info.valid = False
        info.errors.append(T('Verifica crittografica fallita ({})').format(type(e).__name__))
    info.trusted = _chain_trusted(cert, certs)
    info.covers_all = info.intact
    info.summary = _summary(info)
    return info


def _chain_trusted(cert, certs) -> bool:
    try:
        from pyhanko_certvalidator import CertificateValidator
        vc = validation_context()
        import asyncio
        v = CertificateValidator(cert, intermediate_certs=[c for c in certs if c != cert], validation_context=vc)
        asyncio.run(v.async_validate_usage(set()))
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ firma
@dataclass
class SignRequest:
    pfx_path: str
    password: str
    field_name: str = "Firma1"
    page: int = 0
    rect: tuple | None = None          # coordinate PDF (origine in alto a sinistra), None = invisibile
    reason: str = ""
    location: str = ""
    contact: str = ""
    show_text: bool = True
    image_path: str | None = None


def load_signer(pfx_path: str, password: str):
    from pyhanko.sign import signers
    s = signers.SimpleSigner.load_pkcs12(pfx_path, passphrase=password.encode("utf-8") if password else None)
    if s is None:
        raise ValueError(T('Impossibile aprire il certificato: password errata o file non valido'))
    return s


def sign_pdf(data: bytes, req: SignRequest, page_height: float, existing_field: bool = False) -> bytes:
    """Firma il PDF (salvataggio incrementale, le firme precedenti restano valide)."""
    from pyhanko import stamp
    from pyhanko.pdf_utils import images
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    signer = load_signer(req.pfx_path, req.password)
    w = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
    meta = signers.PdfSignatureMetadata(field_name=req.field_name, reason=req.reason or None,
                                        location=req.location or None, contact_info=req.contact or None,
                                        md_algorithm="sha256")
    new_field = None
    if not existing_field:
        box = None
        if req.rect:
            x0, y0, x1, y1 = req.rect
            box = (int(x0), int(page_height - y1), int(x1), int(page_height - y0))
        new_field = fields.SigFieldSpec(sig_field_name=req.field_name, on_page=req.page, box=box)
    style = None
    if req.rect:
        cn = _name(signer.signing_cert)[0]
        lines = []
        if req.show_text:
            lines = [T('Firmato digitalmente da: {}').format(cn), "Data: %(ts)s"]
            if req.reason:
                lines.append(T('Motivo: {}').format(req.reason))
            if req.location:
                lines.append(T('Luogo: {}').format(req.location))
        bg = images.PdfImage(req.image_path) if req.image_path else None
        style = stamp.TextStampStyle(stamp_text="\n".join(lines) or " ", background=bg,
                                     background_opacity=0.9 if bg else 0.6,
                                     timestamp_format="%d/%m/%Y %H:%M:%S")
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style, new_field_spec=new_field)
    out = io.BytesIO()
    pdf_signer.sign_pdf(w, output=out)
    return out.getvalue()


def create_self_signed_id(path: str, password: str, name: str, email: str = "", org: str = "",
                          country: str = "IT", years: int = 5) -> None:
    """Crea un ID digitale autofirmato (.pfx), utile per firme interne o di prova."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
    if org:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    if country:
        attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, country[:2].upper()))
    subject = x509.Name(attrs)
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=365 * years))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION,
                                                  ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    data = pkcs12.serialize_key_and_certificates(
        name.encode("utf-8"), key, cert, None,
        serialization.BestAvailableEncryption(password.encode("utf-8")) if password else serialization.NoEncryption())
    with open(path, "wb") as f:
        f.write(data)
    # l'ID creato dall'utente è attendibile per l'utente stesso
    add_trusted_cert(cert.public_bytes(serialization.Encoding.DER), name)


def cert_der_from_signature(data: bytes, field_name: str) -> bytes | None:
    from pyhanko.pdf_utils.reader import PdfFileReader
    r = PdfFileReader(io.BytesIO(data), strict=False)
    for sig in r.embedded_signatures:
        if sig.field_name == field_name:
            return sig.signer_cert.dump()
    return None
