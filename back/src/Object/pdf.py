# -*- coding: utf-8 -*-

# The fault subcode “mss:402” indicates that the user's Mobile ID PIN is blocked.
# Solution hint: “A new activation is required. Please visit the Mobile ID Portal of your Mobile Network
# Operator and follow the PIN forgotten link (#Faultcode user assistance URL#)”

# https://www.mobileid.ch/fr/login
from base64 import b64encode
from codecs import encode
from hashlib import sha256
from shutil import copy
from subprocess import check_call
from tempfile import mkstemp
from PyPDF2 import PdfFileReader
from PyPDF2.generic import IndirectObject, DictionaryObject
from pkg_resources import resource_filename

class PDF(object):
    """A container for a PDF file to be signed and the signed version."""

    def __init__(self, in_filename, prepared=False):
        self.in_filename = in_filename
        """Filename of the PDF to be treated."""

        _out_fp, _out_filename = mkstemp(suffix=".pdf")
        self.out_filename = _out_filename
        """Filename of the output, signed PDF."""

        copy(self.in_filename, self.out_filename)

        self.prepared = prepared
        """Is the PDF prepared with an empty signature?"""

    @staticmethod
    def _java_command():
        java_dir = resource_filename(__name__, 'empty_signer')
        return [
            'java',
            '-cp', '.:vendor/itextpdf-5.5.9.jar',
            '-Duser.dir={}'.format(java_dir),
            'EmptySigner',
        ]

    @classmethod
    def prepare_batch(cls, pdfs):
        """Add an empty signature to each of pdfs with only one java call."""
        pdfs_to_prepare = filter(lambda p: not p.prepared, pdfs)
        check_call(
            cls._java_command() +
            [pdf.out_filename for pdf in pdfs_to_prepare]
        )
        for pdf in pdfs_to_prepare:
            pdf.prepared = True

    def prepare(self):
        """Add an empty signature to self.out_filename."""
        if not self.prepared:
            check_call(
                self._java_command() + [self.out_filename],
            )
            self.prepared = True

    def digest(self):
        reader = PdfFileReader(self.out_filename)
        sig_obj = None

        for generation, idnums in reader.xref.items():
            for idnum in idnums:
                if idnum == 0:
                    break
                pdf_obj = IndirectObject(idnum, generation,
                                                        reader).getObject()
                if (
                    isinstance(pdf_obj, DictionaryObject) and
                    pdf_obj.get('/Type') == '/Sig'
                ):
                    sig_obj = pdf_obj
                    break

        self.byte_range = sig_obj['/ByteRange']

        h = sha256()
        with open(self.out_filename, 'rb') as fp:
            for start, length in (self.byte_range[:2], self.byte_range[2:]):
                fp.seek(start)
                h.update(fp.read(length))

        result = b64encode(h.digest())
        return result

    def write_signature(self, signature):
        with open(self.out_filename, "rb+") as fp:
            fp.seek(self.byte_range[1] + 1)
            fp.write(encode(signature, 'hex'))
