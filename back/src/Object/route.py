from time import mktime, sleep
from datetime import datetime
from os import listdir, remove
from os.path import isfile, join, getmtime
from bottle import request, response
from phonenumbers import format_number, parse
from phonenumbers import PhoneNumberFormat
from phonenumbers.phonenumberutil import NumberParseException
from uuid import uuid4
from tempfile import NamedTemporaryFile
from requests import post
from json import loads, dumps
from base64 import b64decode, b64encode
import fitz
from .pdf import PDF

def setuproute(app):
    @app.route('/sign/<>', method='OPTIONS')
    def sign():
        return ""

    @app.route('/sign/graphic', method='POST')
    def graphic_sign():
        ret = {"err": None, "data": None}
        body = request.json
        data = body.get('b64file')
        sign = body.get('sign')
        if not isinstance(sign, list) or not all(isinstance(i, dict) for i in sign):
            response.status = 400
            ret["err"] = "Invalid param"
            return ret
        if not all(i in i2 for i in ["b64sign", "x", "y", "h", "w", "page"] for i2 in sign):
            response.status = 400
            ret["err"] = "Invalid data in sign"
            return ret
        pdfname = str(uuid4())
        with open("/files/" + pdfname, "wb") as fp:
            fp.write(b64decode(data))
            fp.close()
        handle = fitz.open("/files/" + pdfname)
        for i in sign:
            try:
                page = handle[int(i["page"])]
            except:
                response.status = 400
                ret["err"] = "Invalid page number in sign"
                return ret
            if True:
                page.cleanContents()
                image_rectangle = fitz.Rect(i["x"], i["y"], i["x"] + i["h"], i["y"] + i["h"])
                with NamedTemporaryFile(suffix='.png', delete=True) as tmp:
                    tmp.write(b64decode(i["b64sign"]))
                    page.insertImage(image_rectangle, tmp.name)
                    tmp.close()
            else:
                response.status = 400
                ret["err"] = "Invalid b64"
                return ret
        c = 0
        for i in handle:
            handle[c].cleanContents()
            c += 1
        handle.save("/files/" + pdfname + "out", deflate=True)
        handle.close()
        with open("/files/" + pdfname + "out", "rb") as fp:
            ret["data"] = str(b64encode(fp.read()))[2:-1]
            fp.close()
        remove("/files/" + pdfname)
        remove("/files/" + pdfname + "out")
        return ret

    @app.route('/sign/qualified', method='POST')
    def sign():
        ret = {"err": None, "data": None}
        body = request.json
        data = body.get('b64file')
        name = body.get('name')
        phone = body.get('phone')
        if phone is None or phone[0:3] != "+41":
            response.status = 400
            ret["err"] = "Phone isn't valid"
            return ret
        if name is None:
            response.status = 400
            ret["err"] = "Can't find proper name"
            return ret
        if data is None:
            response.status = 400
            ret["err"] = "Invalid b64"
            return ret
        try:
            phone = format_number(parse(phone, 'CH'), PhoneNumberFormat.INTERNATIONAL)
            phone = phone.replace(" ", "")
            if len(phone) != 12:
                response.status = 400
                ret["err"] = "Invalid phone number"
                return ret
        except NumberParseException:
            response.status = 400
            ret["err"] = "Invalid phone number"
            return ret
        pdfname = str(uuid4())
        with open("/files/" + pdfname, "wb") as fp:
            fp.write(b64decode(data))
        f = open("/files/" + pdfname, "rb")
        data = f.read()
        f.close()
        pdf = PDF("/files/" + pdfname)
        try:
            pdf.prepare()
        except:
            response.status = 400
            ret["err"] = "Invalid pdf file"
            return ret
        dig = pdf.digest().decode()
        payload = 	{
        	"SignRequest":{
        		"@RequestID":"ais.smartco.ch",
        		"@Profile":"http://ais.swisscom.ch/1.1",
        		"OptionalInputs":{
        			"ClaimedIdentity":{
        				"Name":"SmartCo.SA:OnDemand-Advanced"
        			},
        			"SignatureType":"urn:ietf:rfc:3369",
                    "AddTimestamp": {"@Type": "urn:ietf:rfc:3161"},
        			"AdditionalProfile":[
        				"http://ais.swisscom.ch/1.0/profiles/ondemandcertificate",
        				"urn:oasis:names:tc:dss:1.0:profiles:asynchronousprocessing"
        			],
        			"sc.CertificateRequest":{
        				"sc.DistinguishedName":"template:pseudonym",
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
        return ret
        r = post('https://ais.swisscom.com/AIS-Server/rs/v1.0/sign',
                           cert=('./back/src/secret/smartco.crt', './back/src/secret/smartco.key'),
                           data=dumps(payload),
                           headers= {
                            'Accept': 'application/json, text/plain, */*',
                            'Content-Type': 'application/json;charset=utf-8'
                           })
        if r.status_code != 200:
            response.status = 500
            ret["err"] = "Internal error"
            return ret
        sleep(2)
        sign = loads(r.text)['Signresponse']['OptionalOutputs']['async.responseID']
        while True:
            r = post('https://ais.swisscom.com/AIS-Server/rs/v1.0/pending',
                               cert=('./back/src/secret/smartco.crt', './back/src/secret/smartco.key'),
                               data=dumps({
                                    "async.PendingRequest": {
                                        "@RequestID": "async.PendingRequest",
                                         "@Profile": "http://ais.swisscom.ch/1.1",
                                         "OptionalInputs": {
                                             "ClaimedIdentity": {
                                                 "Name": "SmartCo.SA:OnDemand-Advanced"
                                             },
                                             "async.responseID": sign
                                             }
                                         }
                                }),
                               headers= {
                                'Accept': 'application/json, text/plain, */*',
                                'Content-Type': 'application/json;charset=utf-8'
                               })
            r = loads(r.text)
            if r["Signresponse"]["Result"]["ResultMajor"] == "urn:oasis:names:tc:dss:1.0:resultmajor:Success":
                signature = b64decode(r["Signresponse"]['SignatureObject']['Base64Signature']['$'])
                pdf.write_signature(signature)
                f = open(pdf.out_filename, "rb")
                data = f.read()
                f.close()
                response.status = 200
                ret["data"] =  b64encode(data).decode()
                return ret
            elif "Error" in r["Signresponse"]["Result"]["ResultMajor"]:
                response.status = 405
                if "$" in r["Signresponse"]["Result"]["ResultMessage"]:
                    ret["err"] =  str(r["Signresponse"]["Result"]["ResultMessage"]["$"])
                else:
                    ret["err"] =  "Client refused to sign"
                return ret
            sleep(1)
        response.status = 500
        return ret
    @app.route('/')
    def health():
        now = mktime(datetime.now().timetuple())
        files = [f for f in listdir('/files') if isfile(join('/files', f))]
        for i in files:
            t = getmtime(i)
            if now - t > 30:
                remove(i)
        return ""
