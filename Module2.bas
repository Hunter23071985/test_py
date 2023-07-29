Attribute VB_Name = "Module2"
Option Explicit

Dim resCache As New Dictionary
Dim nextRecalcTime As Variant
Const ReCalcInterval = "00:00:10"

Sub ClearDictionary()
  Set resCache = New Dictionary
End Sub

Function TimedRecalc()
  If DateDiff("s", nextRecalcTime, Now()) > ReCalcInterval Then
    Application.Calculate
    nextRecalcTime = 0
  End If
End Function

Function ParseData3(url As String, siteType As String, xPath As String)
  Const remotePythonAddress = "http://localhost:8000"
  
  Application.Volatile (True)
  Dim oXMLHTTP As New XMLHTTP
  Dim oXML As New DOMDocument
  Dim oURL As IXMLDOMElement, oRes As IXMLDOMElement
  If resCache.Exists(url & siteType & xPath) Then
    ParseData3 = resCache.item(url & siteType & xPath)
    Exit Function
  End If
  oXML.LoadXML ("<root/>")
  Set oURL = cNode(oXML.DocumentElement, "url", url)
  oURL.setAttribute "sitetype", siteType
  cNode oURL, "xpath", xPath
  
  oXMLHTTP.Open "POST", remotePythonAddress, False
  oXMLHTTP.setRequestHeader "Content-Type", "text/xml"
  oXMLHTTP.send oXML.XML

  oXML.LoadXML oXMLHTTP.responseText
  For Each oURL In oXML.SelectNodes("//url")
    If oURL.getAttribute("status") <> 4 Then
      ParseData3 = "N/A"
      If nextRecalcTime = 0 Then
        nextRecalcTime = Now + TimeValue(ReCalcInterval)
        Application.OnTime nextRecalcTime, "TimedRecalc"
        Debug.Print nextRecalcTime
      End If
    Else
      For Each oRes In oURL.SelectNodes(".//result")
        ParseData3 = " " & oRes.text
      Next
      If InStr(ParseData3, "Site error") > 0 Then
        oXMLHTTP.Open "Get", url
        oXMLHTTP.send
        cNode oURL, "data", oXMLHTTP.responseText
        oXMLHTTP.Open "POST", remotePythonAddress, False
        oXMLHTTP.setRequestHeader "Content-Type", "text/xml"
        oXMLHTTP.send oXML.XML
      Else
        resCache.Add url & siteType & xPath, Trim(ParseData3)
      End If
    End If
  Next
  ParseData3 = Trim(ParseData3)
End Function

Function cNode(parent As IXMLDOMElement, name As String, text As String)
  Set cNode = parent.OwnerDocument.createElement(name)
  cNode.text = text
  parent.appendChild (cNode)
End Function
