# -*- coding: utf-8 -*-

# The fault subcode “mss:402” indicates that the user's Mobile ID PIN is blocked.
# Solution hint: “A new activation is required. Please visit the Mobile ID Portal of your Mobile Network
# Operator and follow the PIN forgotten link (#Faultcode user assistance URL#)”

# https://www.mobileid.ch/fr/login
import base64
import codecs
import hashlib
import shutil
import subprocess
import tempfile
import PyPDF2
import requests
import json
import base64, sys, hashlib
from time import sleep
import codecs
from pkg_resources import resource_filename
from bottle import route, request, run

class PDF(object):
    """A container for a PDF file to be signed and the signed version."""

    def __init__(self, in_filename, prepared=False):
        self.in_filename = in_filename
        """Filename of the PDF to be treated."""

        _out_fp, _out_filename = tempfile.mkstemp(suffix=".pdf")
        self.out_filename = _out_filename
        """Filename of the output, signed PDF."""

        shutil.copy(self.in_filename, self.out_filename)

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
        subprocess.check_call(
            cls._java_command() +
            [pdf.out_filename for pdf in pdfs_to_prepare]
        )
        for pdf in pdfs_to_prepare:
            pdf.prepared = True

    def prepare(self):
        """Add an empty signature to self.out_filename."""
        if not self.prepared:
            subprocess.check_call(
                self._java_command() + [self.out_filename],
            )
            self.prepared = True

    def digest(self):
        reader = PyPDF2.PdfFileReader(self.out_filename)
        sig_obj = None

        for generation, idnums in reader.xref.items():
            for idnum in idnums:
                if idnum == 0:
                    break
                pdf_obj = PyPDF2.generic.IndirectObject(idnum, generation,
                                                        reader).getObject()
                if (
                    isinstance(pdf_obj, PyPDF2.generic.DictionaryObject) and
                    pdf_obj.get('/Type') == '/Sig'
                ):
                    sig_obj = pdf_obj
                    break

        self.byte_range = sig_obj['/ByteRange']

        h = hashlib.sha256()
        with open(self.out_filename, 'rb') as fp:
            for start, length in (self.byte_range[:2], self.byte_range[2:]):
                fp.seek(start)
                h.update(fp.read(length))

        result = base64.b64encode(h.digest())
        return result

    def write_signature(self, signature):
        with open(self.out_filename, "rb+") as fp:
            fp.seek(self.byte_range[1] + 1)
            fp.write(codecs.encode(signature, 'hex'))



@route('/sign', method='POST')
def sign():
    name = request.forms.name
    data = request.files.file
    phone = request.forms.phone
    given = request.forms.given
    surname = request.forms.surname
    email = request.forms.email
    if not phone or phone[0:3] != "+41":
        return "error"
    if not name or not data or not data.file:
        return "error"
    if not given or not surname or not email:
        return "error"
    pdfname = name
    data.save(pdfname)
    f = open(pdfname, "rb")
    data = f.read()
    f.close()
    pdf = PDF(pdfname)
    pdf.prepare()
    dig = pdf.digest().decode()
    payload = 	{
    	"SignRequest":{
    		"@RequestID":"ais.smartco.ch",
    		"@Profile":"http://ais.swisscom.ch/1.1",
    		"OptionalInputs":{
    			"ClaimedIdentity":{
    				"Name":"ais-90days-trial-withRAservice:OnDemand-Advanced"
    			},
    			"SignatureType":"urn:ietf:rfc:3369",
                "AddTimestamp": {"@Type": "urn:ietf:rfc:3161"},
    			"AdditionalProfile":[
    				"http://ais.swisscom.ch/1.0/profiles/ondemandcertificate",
    				"urn:oasis:names:tc:dss:1.0:profiles:asynchronousprocessing"
    			],
    			"sc.CertificateRequest":{
    				"sc.DistinguishedName":f"cn=TEST smartco, givenname={given}, surname={surname}, c=CH, emailaddress={email}",
    				"sc.StepUpAuthorisation":{
    					"sc.Phone":{
    						"sc.MSISDN": phone[1:],
    						"sc.Message": f"Voulez vous signer {name} ?",
    						"sc.Language":"FR"
    					}
    				}
    			}
    		},
    		"InputDocuments":{
    			"DocumentHash":{
    				"@ID": pdfname,
    				"dsig.DigestMethod":{
    					"@Algorithm":"http://www.w3.org/2001/04/xmlenc#sha256"
    				},
    				"dsig.DigestValue": dig
    			}
    		}
    	}
    }

    r = requests.post('https://ais.swisscom.com/AIS-Server/rs/v1.0/sign',
                       cert=('./back/src/secret/smartco.crt', './back/src/secret/smartco.key'),
                       data=json.dumps(payload),
                       headers= {
                        'Accept': 'application/json, text/plain, */*',
                        'Content-Type': 'application/json;charset=utf-8'
                       })
    if r.status_code != 200:
        return "error"
    sign = json.loads(r.text)['SignResponse']['OptionalOutputs']['async.ResponseID']
    sleep(5)
    while True:
        sleep(1)
        r = requests.post('https://ais.swisscom.com/AIS-Server/rs/v1.0/pending',
                           cert=('./back/src/secret/smartco.crt', './back/src/secret/smartco.key'),
                           data=json.dumps({
                                "async.PendingRequest": {
                                    "@RequestID": "async.PendingRequest",
                                     "@Profile": "http://ais.swisscom.ch/1.1",
                                     "OptionalInputs": {
                                         "ClaimedIdentity": {
                                             "Name": "ais-90days-trial-withRAservice:OnDemand-Advanced"
                                         },
                                         "async.ResponseID": sign
                                         }
                                     }
                            }),
                           headers= {
                            'Accept': 'application/json, text/plain, */*',
                            'Content-Type': 'application/json;charset=utf-8'
                           })
        r = json.loads(r.text)

        if r["SignResponse"]["Result"]["ResultMajor"] == "urn:oasis:names:tc:dss:1.0:resultmajor:Success":
            signature = base64.b64decode(r["SignResponse"]['SignatureObject']['Base64Signature']['$'])
            pdf.write_signature(signature)
            f = open(pdf.out_filename, "rb")
            data = f.read()
            f.close()
            return base64.b64encode(data).decode()
        elif "Error" in r["SignResponse"]["Result"]["ResultMajor"]:
            return str(r)

@route('/')
def health():
    return ""

if __name__ == '__main__':
    run(host='0.0.0.0', port=8080)
