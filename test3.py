threadsCount=8
textMaxLen=1024*32-1
timeAging=1800

#WARC IO
#from warcio.capture_http import capture_http  # requests *must* be imported after capture_http
#from warcio import WARCWriter

#system modules
import threading, traceback, os, textwrap, io, codecs, time
from queue import Queue
from datetime import datetime
from html import unescape
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, parse_qsl, urlparse
from cgi import parse_header, parse_multipart
import ssl, urllib3 ; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import re 

#XML Parsing
import lxml.etree as lt
from elementpath import select, XPath1Parser, XPath2Parser
from elementpath.xpath3 import  XPath30Parser, XPath31Parser

# Regexp 
#import regexp as re

#http request things
import requests,cloudscraper
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from chardet.universaldetector import UniversalDetector ; detector = UniversalDetector()


cs = cloudscraper.CloudScraper(ssl_context=ssl._create_unverified_context())
sem = threading.Semaphore(threadsCount)
lock = threading.Lock()

#warcFH = open(f'data{int(datetime.now().timestamp())}.warc.gz', 'wb')
#warcFS = WARCWriter(warcFH)

def detectEncoding(req):
  cdict = requests.utils._parse_content_type_header(req.headers.get("Content-Type",""))
  for enc in set(["encoding","charset"])&set(cdict[1]):
    try:codecs.lookup(cdict[1][enc]); return cdict[1][enc]
    except: pass
  body = req.content
  rex = re.compile (b"(?:charset|encoding)\s*=\s*\x22?([^\s\x22<>]+)")
  for enc in rex.findall(body):
    try: codecs.lookup(enc); return enc
    except: pass
  st = 0 
  detector.reset()
  with io.BytesIO(body) as bb: 
    while (not detector.done) and bb.tell()<len(body): detector.feed(bb.read(1024))
  detector.close()
  try: codecs.lookup(detector.result["encoding"]); return detector.result["encoding"]
  except: return "utf-8"


def parseSite(url,sitetype,exp):
  sem.acquire(True)
  try:
#    with capture_http(warcFS):
#      req = cs.get(url=url, timeout = 15)
    req = cs.get(url=url, timeout = 15)
    resp = req.content
  except Exception as e:
    return f"Site {url} error {e}"
  finally:
    sem.release()
  with open("lastresp.txt","wb") as f:
    f.write(req.content)
  enc = detectEncoding(req)

  if sitetype in ["HTM", "DIN"]:
    try: ht = lt.fromstring(resp, parser=lt.HTMLParser(encoding=enc))
    except:
      try: ht = lt.fromstring(resp.decode(enc), parser=lt.HTMLParser())
      except Exception as e:
        return f"Site parsing {url} error {e}"
    se = []
#    with open("lastresp.xml", 'wb') as f:
#     f.write(lt.tostring(ht, pretty_print = True))
    try: se = select (ht,exp,parser=XPath31Parser)
    except:
      try: se = select (ht,exp,parser=XPath30Parser)
      except:
        try: se = select (ht,exp,parser=XPath2Parser)
        except:
          try: se = select (ht,exp,parser=XPath1Parser)
          except:
            try: se = ht.xpath(exp)
            except : return f"XPATH failed {exp} ({url})"
    return textwrap.shorten(" ".join([el.xpath("normalize-space(string())") if (type(el)!=str and type(el)!=bytes) else el.strip(' \t\r\n') for el in se]).strip(),width=textMaxLen)
  elif sitetype in ["TXT", "APK"]:
    try:
      rex = re.compile(exp,re.M)
    except:
      return f"Regexp failed {exp} ({url})"
    return textwrap.shorten(' '.join([m if type(m)==str else ''.join(m) for m in rex.findall(resp.decode(enc,errors='replace'))]).strip(),width=textMaxLen)
  else:
    return f"Unknown site type {sitetype} ({url})"

results = {}
q = Queue()
t = []
hostLock = set()

def producer():
  while True:
    d = q.get()
    hostURL = urlparse(d["url"]).netloc
    if hostURL in hostLock: q.put(d); q.task_done(); time.sleep(1); continue
    hostLock.add(hostURL)
    dataKey = d["url"]+d["sitetype"]+d["exp"]
    try:
      if (datetime.now()-results[dataKey]["time"]).total_seconds() >timeAging:raise
    except:results[dataKey]={d["exp"]:parseSite(d["url"],d["sitetype"],d["exp"]),"time":datetime.now()}; print (d["url"], results[dataKey])
      
    finally:q.task_done(); hostLock.discard(hostURL)

for i in range(1,threadsCount):
  th = threading.Thread(target=producer, daemon=True)
  t.append(th)
  th.start()

class ReqHandle(BaseHTTPRequestHandler):
    def parseRequest(self):
      try:
        tmpXML = lt.fromstring(self.rfile.read(int(self.headers['content-length'])))
        for oUrl in tmpXML.xpath("//url"):
          url = oUrl.text
          for oExp in oUrl.xpath("regex|xpath"):
            try:
              dataKey = url+oUrl.attrib["sitetype"]+oExp.text
              oUrl.attrib["status"] = "1"
              results[dataKey]
              oUrl.attrib["status"] = "2"
              if (datetime.now()-results[dataKey]["time"]).total_seconds() >timeAging: raise
              oUrl.attrib["status"] = "4" 
            except:
              q.put({"url":oUrl.text,"sitetype":oUrl.attrib["sitetype"],"exp":oExp.text})
            if dataKey in results:
              lt.SubElement(oExp,"result").text = results[dataKey].get(oExp.text)
        self.send_response(200)
        self.send_header("Content-type", "text/xml")
        self.end_headers()
        self.wfile.write(lt.tostring(tmpXML))
      except Exception as e:
        print (str(e))
        traceback.print_exc()
        self.send_response(500)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(traceback.print_exc())
  

    def do_POST(self):
        self.parseRequest()


print ('localhost',8000)
httpd = ThreadingHTTPServer(('localhost',8000), ReqHandle)
httpd.serve_forever()
