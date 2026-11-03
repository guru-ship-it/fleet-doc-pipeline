"""What the driver reads on WhatsApp, in English, Hindi or Telugu. The Hindi and Telugu lines need a native
speaker's check before real drivers see them."""
LABELS = {
    "service_invoice": ("service bill", "सर्विस बिल", "సర్వీస్ బిల్లు"),
    "job_card": ("job card", "जॉब कार्ड", "జాబ్ కార్డ్"),
    "spares_bill": ("parts bill", "पार्ट्स बिल", "విడిభాగాల బిల్లు"),
    "cash_memo": ("cash memo", "कैश मेमो", "క్యాష్ మెమో"),
    "payment_receipt": ("payment receipt", "भुगतान रसीद", "చెల్లింపు రసీదు"),
    "insurance": ("insurance", "बीमा", "ఇన్సూరెన్స్"),
    "puc": ("PUC certificate", "PUC प्रमाणपत्र", "PUC సర్టిఫికెట్"),
    "rc": ("RC", "RC", "RC"),
    "permit": ("permit", "परमिट", "పర్మిట్"),
    "fitness": ("fitness certificate", "फिटनेस प्रमाणपत्र", "ఫిట్‌నెస్ సర్టిఫికెట్"),
    "road_tax": ("road tax receipt", "रोड टैक्स रसीद", "రోడ్ ట్యాక్స్ రసీదు"),
    "medical_certificate": ("medical certificate", "मेडिकल सर्टिफ़िकेट", "మెడికల్ సర్టిఫికెట్"),
    "police_verification": ("police verification certificate", "पुलिस सत्यापन प्रमाणपत्र", "పోలీస్ వెరిఫికేషన్ సర్టిఫికెట్"),
    "other": ("document", "दस्तावेज़", "డాక్యుమెంట్"),
}
SAFETY_LABELS = {
    "tyres": ("tyres", "टायर", "టైర్లు"),
    "brakes": ("brakes", "ब्रेक", "బ్రేకులు"),
    "clutch": ("clutch", "क्लच", "క్లచ్"),
    "steering": ("steering", "स्टीयरिंग", "స్టీరింగ్"),
    "suspension": ("suspension", "सस्पेंशन", "సస్పెన్షన్"),
    "fuel_system": ("fuel tank or pipe", "फ्यूल टैंक या पाइप", "ఫ్యూయల్ ట్యాంక్ లేదా పైప్"),
}
LANG_INDEX = {"en": 0, "hi": 1, "te": 2}

T = {
    "not_registered": (
        "This number is not registered for the fleet document service. Please contact your supervisor.",
        "यह नंबर फ्लीट दस्तावेज़ सेवा के लिए पंजीकृत नहीं है। कृपया अपने सुपरवाइज़र से संपर्क करें।",
        "ఈ నంబర్ ఫ్లీట్ డాక్యుమెంట్ సేవకు నమోదు కాలేదు. దయచేసి మీ సూపర్‌వైజర్‌ను సంప్రదించండి."),
    "consent_request": (
        "Before you send documents: the photos and PDFs you send here (service bills, insurance, PUC and similar "
        "papers for your cab) are stored securely and read by our system to update your cab's compliance record "
        "for {client}. Reply YES to agree. You can withdraw at any time by replying STOP.",
        "दस्तावेज़ भेजने से पहले: आप यहाँ जो फ़ोटो और PDF भेजेंगे (आपकी कैब के सर्विस बिल, बीमा, PUC जैसे कागज़), वे "
        "सुरक्षित रखे जाएँगे और {client} के लिए आपकी कैब का रिकॉर्ड अपडेट करने के लिए हमारी प्रणाली उन्हें पढ़ेगी। "
        "सहमति के लिए YES लिखकर भेजें। अपनी सहमति कभी भी वापस लेने के लिए STOP लिखकर भेजें।",
        "డాక్యుమెంట్లు పంపే ముందు: మీరు ఇక్కడ పంపే ఫోటోలు, PDFలు (మీ క్యాబ్ సర్వీస్ బిల్లులు, ఇన్సూరెన్స్, PUC వంటి "
        "పత్రాలు) సురక్షితంగా భద్రపరుస్తాం, {client} కోసం మీ క్యాబ్ రికార్డును అప్‌డేట్ చేయడానికి మా సిస్టమ్ వాటిని "
        "చదువుతుంది. అంగీకరిస్తే YES అని పంపండి. మీ అంగీకారాన్ని ఎప్పుడైనా వెనక్కి తీసుకోవాలంటే STOP అని పంపండి."),
    "consent_withdrawn": (
        "Your consent is withdrawn. From now on, nothing you send here will be stored or read. Reply YES if you want "
        "to start again.",
        "आपकी सहमति वापस ले ली गई है। अब से आप यहाँ जो भी भेजेंगे, वह न रखा जाएगा और न पढ़ा जाएगा। फिर से शुरू करना हो "
        "तो YES लिखकर भेजें।",
        "మీ అంగీకారం రద్దయింది. ఇకపై మీరు ఇక్కడ పంపే వాటిని మేము భద్రపరచము, చదవము. మళ్ళీ మొదలుపెట్టాలంటే YES అని "
        "పంపండి."),
    "consent_thanks": (
        "Thank you. You can now send photos or PDFs of your cab's documents here.",
        "धन्यवाद। अब आप अपनी कैब के दस्तावेज़ों की फ़ोटो या PDF यहाँ भेज सकते हैं।",
        "ధన్యవాదాలు. ఇప్పుడు మీ క్యాబ్ డాక్యుమెంట్ల ఫోటోలు లేదా PDFలు ఇక్కడ పంపవచ్చు."),
    "how_to": (
        "Send a photo or PDF of your cab's document here. For a medical certificate, write MEDICAL with it.",
        "अपनी कैब के दस्तावेज़ की फ़ोटो या PDF यहाँ भेजें। मेडिकल सर्टिफ़िकेट के साथ MEDICAL लिखें।",
        "మీ క్యాబ్ డాక్యుమెంట్ ఫోటో లేదా PDF ఇక్కడ పంపండి. మెడికల్ సర్టిఫికెట్ అయితే దానితో MEDICAL అని రాయండి."),
    "unsupported": (
        "Please send a photo or a PDF. Other kinds of messages cannot be read here.",
        "कृपया फ़ोटो या PDF भेजें। यहाँ दूसरे तरह के संदेश नहीं पढ़े जा सकते।",
        "దయచేసి ఫోటో లేదా PDF పంపండి. ఇతర రకాల మెసేజ్‌లు ఇక్కడ చదవలేము."),
    "received_checking": (
        "Received. Checking it now.",
        "मिल गया। जाँच हो रही है।",
        "అందింది. ఇప్పుడు చెక్ చేస్తున్నాం."),
    "received_validity": (
        "Received {doc_label} for {vehicle}, valid till {valid_till}. Thank you.",
        "{vehicle} का {doc_label} मिल गया, {valid_till} तक मान्य। धन्यवाद।",
        "{vehicle} {doc_label} అందింది, {valid_till} వరకు చెల్లుతుంది. ధన్యవాదాలు."),
    "received_service": (
        "Received the {doc_label} for {vehicle}. Thank you.",
        "{vehicle} का {doc_label} मिल गया। धन्यवाद।",
        "{vehicle} {doc_label} అందింది. ధన్యవాదాలు."),
    "received_with_advisory": (
        "Received the {doc_label} for {vehicle}. The workshop has noted: {advisories}. Please send the bill once it is fixed.",
        "{vehicle} का {doc_label} मिल गया। वर्कशॉप ने यह बताया है: {advisories}। ठीक होने के बाद कृपया उसका बिल भेजें।",
        "{vehicle} {doc_label} అందింది. వర్క్‌షాప్ ఇలా సూచించింది: {advisories}. సరిచేసిన తర్వాత దాని బిల్లు పంపండి."),
    "already_received": (
        "This document was already received for {vehicle}. Thank you.",
        "यह दस्तावेज़ {vehicle} के लिए पहले ही मिल चुका है। धन्यवाद।",
        "ఈ డాక్యుమెంట్ {vehicle} కోసం ఇప్పటికే అందింది. ధన్యవాదాలు."),
    "vehicle_mismatch": (
        "This document shows a different vehicle number ({other_vehicle}). Please resend the document for {vehicle}.",
        "इस दस्तावेज़ पर दूसरा वाहन नंबर ({other_vehicle}) है। कृपया {vehicle} का दस्तावेज़ फिर से भेजें।",
        "ఈ డాక్యుమెంట్‌పై వేరే వాహన నంబర్ ({other_vehicle}) ఉంది. దయచేసి {vehicle} డాక్యుమెంట్ మళ్ళీ పంపండి."),
    "duplicate_file": (
        "This document was already received for {other_vehicle}. Please send the document for your own cab, {vehicle}.",
        "यह दस्तावेज़ पहले ही {other_vehicle} के लिए मिल चुका है। कृपया अपनी कैब {vehicle} का दस्तावेज़ भेजें।",
        "ఈ డాక్యుమెంట్ ఇప్పటికే {other_vehicle} కోసం అందింది. దయచేసి మీ క్యాబ్ {vehicle} డాక్యుమెంట్ పంపండి."),
    "duplicate_invoice": (
        "This invoice was already received for {other_vehicle}. Please send the invoice for {vehicle}.",
        "यह बिल पहले ही {other_vehicle} के लिए मिल चुका है। कृपया {vehicle} का बिल भेजें।",
        "ఈ బిల్లు ఇప్పటికే {other_vehicle} కోసం అందింది. దయచేసి {vehicle} బిల్లు పంపండి."),
    "future_date": (
        "The date on this bill is after today. Please send the workshop's GST invoice for {vehicle}.",
        "इस बिल की तारीख़ आज के बाद की है। कृपया {vehicle} के लिए वर्कशॉप का GST बिल भेजें।",
        "ఈ బిల్లుపై తేదీ ఈరోజు తర్వాతది. దయచేసి {vehicle} కోసం వర్క్‌షాప్ GST బిల్లు పంపండి."),
    "no_gstin": (
        "This bill has no GST number, so it cannot be accepted. Please send the workshop's GST invoice for {vehicle}.",
        "इस बिल पर GST नंबर नहीं है, इसलिए इसे स्वीकार नहीं किया जा सकता। कृपया {vehicle} के लिए वर्कशॉप का GST बिल भेजें।",
        "ఈ బిల్లుపై GST నంబర్ లేదు, కాబట్టి దీన్ని అంగీకరించలేము. దయచేసి {vehicle} కోసం వర్క్‌షాప్ GST బిల్లు పంపండి."),
    "unreadable": (
        "We could not read this clearly. Please send a clearer photo of the full page.",
        "यह साफ़ नहीं पढ़ा जा सका। कृपया पूरे पन्ने की साफ़ फ़ोटो भेजें।",
        "ఇది స్పష్టంగా చదవలేకపోయాం. దయచేసి పూర్తి పేజీ స్పష్టమైన ఫోటో పంపండి."),
    "billed_to_third_party": (
        "This bill is in another party's name and does not show your cab number. Please send the workshop's job card or invoice for {vehicle}.",
        "यह बिल किसी और के नाम पर है और इस पर आपका कैब नंबर नहीं है। कृपया {vehicle} के लिए वर्कशॉप का जॉब कार्ड या बिल भेजें।",
        "ఈ బిల్లు వేరొకరి పేరు మీద ఉంది, దానిపై మీ క్యాబ్ నంబర్ లేదు. దయచేసి {vehicle} కోసం వర్క్‌షాప్ జాబ్ కార్డ్ లేదా బిల్లు పంపండి."),
    "no_vehicle_no": (
        "Your cab number is not on this document. Please send one that shows {vehicle}.",
        "इस दस्तावेज़ पर आपका कैब नंबर नहीं है। कृपया ऐसा दस्तावेज़ भेजें जिस पर {vehicle} लिखा हो।",
        "ఈ డాక్యుమెంట్‌పై మీ క్యాబ్ నంబర్ లేదు. దయచేసి {vehicle} ఉన్న డాక్యుమెంట్ పంపండి."),
    "proof_incomplete": (
        "Received. This is a parts bill, receipt or estimate, so please also send the workshop's job card or final invoice for {vehicle}.",
        "मिल गया। यह पार्ट्स बिल, रसीद या अनुमान है, इसलिए कृपया {vehicle} के लिए वर्कशॉप का जॉब कार्ड या फ़ाइनल बिल भी भेजें।",
        "అందింది. ఇది విడిభాగాల బిల్లు, రసీదు లేదా అంచనా మాత్రమే, కాబట్టి దయచేసి {vehicle} కోసం వర్క్‌షాప్ జాబ్ కార్డ్ లేదా ఫైనల్ బిల్లు కూడా పంపండి."),
    "expired": (
        "This {doc_label} expired on {valid_till}. Please send the current one for {vehicle}.",
        "यह {doc_label} {valid_till} को समाप्त हो चुका है। कृपया {vehicle} का मौजूदा दस्तावेज़ भेजें।",
        "ఈ {doc_label} గడువు {valid_till}న ముగిసింది. దయచేసి {vehicle} ప్రస్తుత డాక్యుమెంట్ పంపండి."),
    "no_validity": (
        "We could not read the validity date on this {doc_label}. Please send a clearer photo.",
        "इस {doc_label} पर वैधता की तारीख़ नहीं पढ़ी जा सकी। कृपया साफ़ फ़ोटो भेजें।",
        "ఈ {doc_label}పై గడువు తేదీ చదవలేకపోయాం. దయచేసి స్పష్టమైన ఫోటో పంపండి."),
    "medical_received": (
        "Received your medical certificate. It is stored privately and will be reviewed. Thank you.",
        "आपका मेडिकल सर्टिफ़िकेट मिल गया। इसे सुरक्षित रखा गया है और इसकी जाँच की जाएगी। धन्यवाद।",
        "మీ మెడికల్ సర్టిఫికెట్ అందింది. దీన్ని గోప్యంగా భద్రపరిచాం, త్వరలో పరిశీలిస్తాం. ధన్యవాదాలు."),
    "processing_failed": (
        "We received your document but could not check it just now. Our team will look at it.",
        "आपका दस्तावेज़ मिल गया, लेकिन अभी उसकी जाँच नहीं हो सकी। हमारी टीम इसे देखेगी।",
        "మీ డాక్యుమెంట్ అందింది, కానీ ఇప్పుడు చెక్ చేయలేకపోయాం. మా టీమ్ దాన్ని చూస్తుంది."),
    "training_line": (   # appended to an accepting reply when the driver has a module link
        "Your short module on {training_title}, in your language: {training_url}",
        "आपके लिए एक छोटा मॉड्यूल, {training_title}: {training_url}",
        "మీ కోసం ఒక చిన్న మాడ్యూల్, {training_title}: {training_url}"),
}


class _Params(dict):
    def __missing__(self, name):
        from . import logs
        logs.event("REPLY_PARAM_MISSING", "warning", param=name)
        return ""


def render(key: str, lang: str = "en", **params) -> str:
    i = LANG_INDEX.get(lang, 0)
    p = _Params(params)
    if "doc_type" in p:
        p.setdefault("doc_label", LABELS.get(p["doc_type"], LABELS["other"])[i])
    if isinstance(p.get("advisories"), (list, tuple)):
        p["advisories"] = ", ".join(SAFETY_LABELS.get(c, (c, c, c))[i] for c in p["advisories"])
    p.setdefault("client", "the fleet")
    text = T[key][i].format_map(p)
    if p.get("training_url"):
        text += "\n\n" + T["training_line"][i].format_map(p)
    return text
